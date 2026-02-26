from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import logging
import uuid

import boto3
from botocore.exceptions import ClientError

from sparkpilot.config import get_settings
from sparkpilot.models import Environment, Job, Run

logger = logging.getLogger(__name__)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def assume_role_session(role_arn: str, region: str) -> boto3.Session:
    sts = boto3.client("sts", region_name=region)
    response = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName=f"sparkpilot-{uuid.uuid4().hex[:8]}",
    )
    creds = response["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=region,
    )


@dataclass(slots=True)
class EmrDispatchResult:
    emr_job_run_id: str
    log_group: str
    log_stream_prefix: str
    driver_log_uri: str | None
    spark_ui_uri: str | None
    aws_request_id: str | None = None


class EmrEksClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _eks_cluster_name_from_arn(cluster_arn: str) -> str:
        marker = "cluster/"
        if marker not in cluster_arn:
            raise ValueError("Invalid EKS cluster ARN.")
        return cluster_arn.split(marker, maxsplit=1)[1]

    def create_virtual_cluster(self, environment: Environment) -> str:
        if not environment.eks_cluster_arn:
            raise ValueError("Missing EKS cluster ARN.")
        if not environment.eks_namespace:
            raise ValueError("Missing EKS namespace.")
        if self.settings.dry_run_mode:
            return f"vc-{uuid.uuid4().hex[:10]}"

        cluster_name = self._eks_cluster_name_from_arn(environment.eks_cluster_arn)
        session = assume_role_session(environment.customer_role_arn, environment.region)
        client = session.client("emr-containers", region_name=environment.region)
        result = client.create_virtual_cluster(
            name=f"sparkpilot-{environment.id[:8]}",
            containerProvider={
                "id": cluster_name,
                "type": "EKS",
                "info": {
                    "eksInfo": {
                        "namespace": environment.eks_namespace,
                    }
                },
            },
            tags={"sparkpilot:managed": "true"},
        )
        return result["id"]

    def start_job_run(self, environment: Environment, job: Job, run: Run) -> EmrDispatchResult:
        log_group = f"{self.settings.log_group_prefix}/{environment.id}"
        stream_prefix = f"{run.id}/attempt-{run.attempt}"

        if self.settings.dry_run_mode:
            emr_job_run_id = f"jr-{uuid.uuid4().hex[:12]}"
            return EmrDispatchResult(
                emr_job_run_id=emr_job_run_id,
                log_group=log_group,
                log_stream_prefix=stream_prefix,
                driver_log_uri=f"cloudwatch://{log_group}/{stream_prefix}/driver",
                spark_ui_uri=f"https://sparkhistory.local/{run.id}",
            )

        session = assume_role_session(environment.customer_role_arn, environment.region)
        client = session.client("emr-containers", region_name=environment.region)
        result = client.start_job_run(
            virtualClusterId=environment.emr_virtual_cluster_id,
            name=f"{job.name}-{run.id}",
            executionRoleArn=self.settings.emr_execution_role_arn,
            releaseLabel=self.settings.emr_release_label,
            jobDriver={
                "sparkSubmitJobDriver": {
                    "entryPoint": job.artifact_uri,
                    "entryPointArguments": run.args_overrides_json or job.args_json,
                    "sparkSubmitParameters": " ".join(
                        f"--conf {k}={v}" for k, v in {**job.spark_conf_json, **run.spark_conf_overrides_json}.items()
                    ),
                }
            },
            configurationOverrides={
                "monitoringConfiguration": {
                    "cloudWatchMonitoringConfiguration": {
                        "logGroupName": log_group,
                        "logStreamNamePrefix": stream_prefix,
                    }
                }
            },
            retryPolicyConfiguration={"maxAttempts": job.retry_max_attempts},
        )
        metadata = result.get("ResponseMetadata", {})
        return EmrDispatchResult(
            emr_job_run_id=result["id"],
            log_group=log_group,
            log_stream_prefix=stream_prefix,
            driver_log_uri=f"cloudwatch://{log_group}/{stream_prefix}/driver",
            spark_ui_uri=None,
            aws_request_id=metadata.get("RequestId"),
        )

    def describe_job_run(self, environment: Environment, run: Run) -> tuple[str, str | None]:
        if run.cancellation_requested:
            return "CANCELLED", None
        if self.settings.dry_run_mode:
            if not run.started_at:
                return "PENDING", None
            elapsed = (datetime.now(UTC) - _as_utc(run.started_at)).total_seconds()
            if elapsed < 10:
                return "SUBMITTED", None
            if elapsed < 40:
                return "RUNNING", None
            return "COMPLETED", None

        if not run.emr_job_run_id:
            return "FAILED", "Missing EMR job id."
        session = assume_role_session(environment.customer_role_arn, environment.region)
        client = session.client("emr-containers", region_name=environment.region)
        try:
            result = client.describe_job_run(
                virtualClusterId=environment.emr_virtual_cluster_id,
                id=run.emr_job_run_id,
            )
        except ClientError as exc:
            return "FAILED", str(exc)
        job_run = result.get("jobRun", {})
        state = job_run.get("state", "FAILED")
        failure = job_run.get("failureReason")
        return state, failure

    def cancel_job_run(self, environment: Environment, run: Run) -> str | None:
        if self.settings.dry_run_mode:
            return None
        if not run.emr_job_run_id:
            return None
        session = assume_role_session(environment.customer_role_arn, environment.region)
        client = session.client("emr-containers", region_name=environment.region)
        result = client.cancel_job_run(
            virtualClusterId=environment.emr_virtual_cluster_id,
            id=run.emr_job_run_id,
        )
        metadata = result.get("ResponseMetadata", {})
        return metadata.get("RequestId")


class CloudWatchLogsProxy:
    def __init__(self) -> None:
        self.settings = get_settings()

    def fetch_lines(
        self,
        *,
        role_arn: str,
        region: str,
        log_group: str | None,
        log_stream_prefix: str | None,
        limit: int = 200,
    ) -> list[str]:
        if not log_group:
            return []
        if self.settings.dry_run_mode:
            run_hint = log_stream_prefix or "unknown-run"
            return [
                f"[{run_hint}] Spark application started",
                f"[{run_hint}] Executors requested",
                f"[{run_hint}] Job completed successfully",
            ]

        try:
            session = assume_role_session(role_arn, region)
            client = session.client("logs", region_name=region)
            kwargs: dict[str, Any] = {"logGroupName": log_group, "limit": limit}
            if log_stream_prefix:
                kwargs["logStreamNamePrefix"] = log_stream_prefix
            response = client.filter_log_events(**kwargs)
            events = response.get("events", [])
            return [event.get("message", "") for event in events]
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code == "ResourceNotFoundException":
                return []
            logger.warning(
                "CloudWatch log fetch failed for group=%s prefix=%s region=%s role=%s error_code=%s",
                log_group,
                log_stream_prefix,
                region,
                role_arn,
                error_code,
            )
            raise
