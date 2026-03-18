"""Scheduler worker: dispatches queued runs to EMR on EKS."""

import logging
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from sparkpilot.audit import write_audit_event
from sparkpilot.aws_clients import EmrEc2Client, EmrEksClient, EmrServerlessClient
from sparkpilot.models import Environment, Run
from sparkpilot.services._helpers import _now
from sparkpilot.services.preflight import _build_preflight_cached, _preflight_summary
from sparkpilot.services.workers_common import (
    _claim_runs,
    _is_transient_dispatch_error,
    _release_run_claim,
)

logger = logging.getLogger(__name__)


def _log_dispatch_failure(run: Run, env: Environment, exc: Exception) -> None:
    if isinstance(exc, (ClientError, BotoCoreError)):
        logger.exception(
            "AWS dispatch error for run_id=%s environment_id=%s attempt=%s error_type=%s",
            run.id,
            env.id,
            run.attempt,
            type(exc).__name__,
        )
        return
    logger.exception(
        "Unexpected dispatch error for run_id=%s environment_id=%s attempt=%s error_type=%s",
        run.id,
        env.id,
        run.attempt,
        type(exc).__name__,
    )


def _handle_dispatch_failure(
    db: Session,
    *,
    actor: str,
    run: Run,
    env: Environment,
    job: Any,
    exc: Exception,
) -> None:
    _log_dispatch_failure(run, env, exc)
    transient = _is_transient_dispatch_error(exc)
    if transient and run.attempt < job.retry_max_attempts:
        previous_attempt = run.attempt
        run.attempt += 1
        run.state = "queued"
        run.error_message = (
            f"Transient dispatch failure on attempt {previous_attempt} of {job.retry_max_attempts}: {exc}. "
            f"Retry scheduled as attempt {run.attempt}."
        )
        write_audit_event(
            db,
            actor=actor,
            action="run.dispatch_retry_scheduled",
            entity_type="run",
            entity_id=run.id,
            tenant_id=env.tenant_id,
            details={
                "error": str(exc),
                "error_type": type(exc).__name__,
                "attempt": run.attempt,
                "max_attempts": job.retry_max_attempts,
            },
        )
        return

    run.state = "failed"
    run.error_message = str(exc) if isinstance(exc, (ClientError, BotoCoreError)) else f"[{type(exc).__name__}] {exc}"
    run.ended_at = _now()
    write_audit_event(
        db,
        actor=actor,
        action="run.dispatch_failed",
        entity_type="run",
        entity_id=run.id,
        tenant_id=env.tenant_id,
        details={"error": str(exc), "error_type": type(exc).__name__, "transient": transient},
    )


def _dispatch_run(env: Environment, job: Any, run: Run) -> Any:
    """Route dispatch to the correct backend based on env.engine.

    Returns the dispatch result dataclass produced by the chosen client.
    """
    engine = env.engine
    if engine == "emr_on_eks":
        return EmrEksClient().start_job_run(env, job, run)
    if engine == "emr_serverless":
        return EmrServerlessClient().start_job_run(env, job, run)
    if engine == "emr_on_ec2":
        return EmrEc2Client().start_job_run(env, job, run)
    if engine == "databricks":
        from sparkpilot.databricks_client import DatabricksClient
        from sparkpilot.config import get_settings
        settings = get_settings()
        db_token = settings.databricks_token
        db_client = DatabricksClient(
            workspace_url=env.databricks_workspace_url,
            token=db_token,
        )
        result = db_client.submit_run(
            job_artifact_uri=job.artifact_uri,
            entrypoint=job.entrypoint,
            args=[*(job.args_json or []), *(run.args_overrides_json or [])],
            spark_conf={**(job.spark_conf_json or {}), **(run.spark_conf_overrides_json or {})},
            cluster_policy_id=env.databricks_cluster_policy_id,
            instance_pool_id=env.databricks_instance_pool_id,
            run_name=f"sparkpilot-{run.id[:12]}",
            idempotency_token=run.idempotency_key,
        )
        run.backend_job_run_id = str(result.databricks_run_id)
        run.spark_ui_uri = result.run_page_url
        return result
    raise ValueError(f"Unsupported engine: {engine}")


def _apply_dispatch_result(run: Run, env: Environment, dispatch: Any) -> None:
    """Write common dispatch fields onto the run model from any dispatch result type."""
    run.state = "accepted"
    run.started_at = _now()
    run.last_heartbeat_at = run.started_at

    engine = env.engine
    if engine == "databricks":
        # DatabricksDispatchResult does not carry EMR log fields; spark_ui_uri and
        # backend_job_run_id are already written by _dispatch_run before returning.
        return

    run.log_group = dispatch.log_group
    run.log_stream_prefix = dispatch.log_stream_prefix
    run.driver_log_uri = dispatch.driver_log_uri
    run.spark_ui_uri = dispatch.spark_ui_uri

    if engine == "emr_on_eks":
        run.emr_job_run_id = dispatch.emr_job_run_id
        run.backend_job_run_id = dispatch.emr_job_run_id
    elif engine == "emr_serverless":
        run.backend_job_run_id = dispatch.job_run_id
    elif engine == "emr_on_ec2":
        run.backend_job_run_id = dispatch.step_id


def process_scheduler_once(db: Session, *, actor: str = "worker:scheduler", limit: int = 20) -> int:
    queued_runs = _claim_runs(
        db,
        actor=actor,
        states=["queued"],
        limit=limit,
        order_by_column=Run.created_at,
    )
    processed = 0
    for run in queued_runs:
        job = run.job
        env = run.environment
        try:
            spark_conf = {**(job.spark_conf_json or {}), **(run.spark_conf_overrides_json or {})}
            if run.cancellation_requested:
                run.state = "cancelled"
                run.ended_at = _now()
                continue

            preflight = _build_preflight_cached(env, run_id=run.id, spark_conf=spark_conf, db=db)
            if not preflight["ready"]:
                run.state = "failed"
                run.error_message = f"Preflight failed: {_preflight_summary(preflight['checks'])}"
                run.ended_at = _now()
                write_audit_event(
                    db,
                    actor=actor,
                    action="run.preflight_failed",
                    entity_type="run",
                    entity_id=run.id,
                    tenant_id=env.tenant_id,
                    details={
                        "ready": False,
                        "summary": _preflight_summary(preflight["checks"], include_warnings=True),
                        "environment_id": env.id,
                        "checks": preflight["checks"],
                    },
                )
                continue

            write_audit_event(
                db,
                actor=actor,
                action="run.preflight_passed",
                entity_type="run",
                entity_id=run.id,
                tenant_id=env.tenant_id,
                details={
                    "ready": True,
                    "summary": _preflight_summary(preflight["checks"], include_warnings=True),
                    "environment_id": env.id,
                    "checks": preflight["checks"],
                },
            )

            run.state = "dispatching"
            dispatch = _dispatch_run(env, job, run)
            _apply_dispatch_result(run, env, dispatch)
            write_audit_event(
                db,
                actor=actor,
                action="run.dispatched",
                entity_type="run",
                entity_id=run.id,
                tenant_id=env.tenant_id,
                aws_request_id=dispatch.aws_request_id,
                details={"backend_job_run_id": run.backend_job_run_id, "engine": env.engine},
            )
        except Exception as exc:  # noqa: BLE001 — scheduler must handle all errors per-run, not crash the batch
            _handle_dispatch_failure(
                db,
                actor=actor,
                run=run,
                env=env,
                job=job,
                exc=exc,
            )
        finally:
            _release_run_claim(run)
            processed += 1
    if processed:
        db.commit()
    return processed
