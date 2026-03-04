from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import json
import logging
import re
import uuid

import boto3
from botocore.exceptions import ClientError

from sparkpilot.config import get_settings, validate_runtime_settings
from sparkpilot.models import Environment, Job, Run
from sparkpilot.time_utils import _as_utc

logger = logging.getLogger(__name__)
ROLE_ARN_PATTERN = re.compile(r"^arn:aws[a-zA-Z-]*:iam::\d{12}:role/(.+)$")
TRUST_POLICY_REQUIRED_ACTIONS = [
    "eks:DescribeCluster",
    "iam:GetRole",
    "iam:UpdateAssumeRolePolicy",
]
OIDC_DETECTION_REQUIRED_ACTIONS = [
    "eks:DescribeCluster",
    "iam:GetOpenIDConnectProvider",
]
DISPATCH_SIMULATION_ACTIONS = [
    "emr-containers:StartJobRun",
    "emr-containers:DescribeJobRun",
    "emr-containers:CancelJobRun",
]
SPOT_VALIDATION_REQUIRED_ACTIONS = [
    "eks:ListNodegroups",
    "eks:DescribeNodegroup",
]


_BASE36_CHARS = "0123456789abcdefghijklmnopqrstuvwxyz"


def _base36_encode_name(name: str) -> str:
    n = int.from_bytes(name.encode("utf-8"), "big")
    if n == 0:
        return "0"
    result = ""
    while n > 0:
        n, remainder = divmod(n, 36)
        result = _BASE36_CHARS[remainder] + result
    return result


def _emr_sa_pattern(namespace: str, account_id: str, role_name: str) -> str:
    encoded = _base36_encode_name(role_name)
    return f"system:serviceaccount:{namespace}:emr-containers-sa-*-*-{account_id}-{encoded}"


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


@dataclass(slots=True, frozen=True)
class _TrustPolicyTarget:
    cluster_name: str
    namespace: str
    role_name: str
    account_id: str
    region: str


class EmrEksClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _eks_cluster_name_from_arn(cluster_arn: str) -> str:
        marker = "cluster/"
        if marker not in cluster_arn:
            raise ValueError("Invalid EKS cluster ARN.")
        return cluster_arn.split(marker, maxsplit=1)[1]

    @staticmethod
    def _role_name_from_arn(role_arn: str) -> str:
        match = ROLE_ARN_PATTERN.match(role_arn)
        if not match:
            raise ValueError("Invalid IAM role ARN.")
        role_path = match.group(1)
        return role_path.split("/")[-1]

    @staticmethod
    def _account_id_from_arn(arn: str) -> str:
        parts = arn.split(":")
        if len(parts) < 6:
            raise ValueError("Invalid ARN.")
        return parts[4]

    def _build_trust_policy_target(self, environment: Environment) -> _TrustPolicyTarget:
        if not environment.eks_cluster_arn:
            raise ValueError("Missing EKS cluster ARN.")
        if not environment.eks_namespace:
            raise ValueError("Missing EKS namespace.")

        validate_runtime_settings(self.settings)
        return _TrustPolicyTarget(
            cluster_name=self._eks_cluster_name_from_arn(environment.eks_cluster_arn),
            namespace=environment.eks_namespace,
            role_name=self._role_name_from_arn(self.settings.emr_execution_role_arn),
            account_id=self._account_id_from_arn(environment.eks_cluster_arn),
            region=environment.region,
        )

    @staticmethod
    def _is_access_denied_error(code: str) -> bool:
        return code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}

    def _describe_cluster_oidc(
        self,
        *,
        session: boto3.Session,
        target: _TrustPolicyTarget,
        denied_message: str,
        missing_oidc_message: str,
    ) -> tuple[str, str]:
        eks_client = session.client("eks", region_name=target.region)
        try:
            cluster = eks_client.describe_cluster(name=target.cluster_name).get("cluster", {})
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if self._is_access_denied_error(code):
                raise ValueError(denied_message) from None
            raise

        issuer = cluster.get("identity", {}).get("oidc", {}).get("issuer", "")
        if not issuer:
            raise ValueError(missing_oidc_message)
        provider_path = issuer.removeprefix("https://")
        provider_arn = f"arn:aws:iam::{target.account_id}:oidc-provider/{provider_path}"
        return provider_path, provider_arn

    def _load_execution_role_trust_policy(
        self,
        *,
        iam_client: Any,
        target: _TrustPolicyTarget,
        missing_role_message: str,
        denied_message: str,
    ) -> dict[str, Any]:
        try:
            role_data = iam_client.get_role(RoleName=target.role_name)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "NoSuchEntity":
                raise ValueError(missing_role_message) from None
            if self._is_access_denied_error(code):
                raise ValueError(denied_message) from None
            raise

        trust_policy = role_data["Role"]["AssumeRolePolicyDocument"]
        if isinstance(trust_policy, str):
            trust_policy = json.loads(trust_policy)
        return trust_policy

    def _matches_web_identity_statement(
        self,
        statement: dict[str, Any],
        *,
        provider_arn: str,
        provider_path: str,
        sa_pattern: str,
    ) -> bool:
        actions = self._action_values(statement.get("Action"))
        if "sts:AssumeRoleWithWebIdentity" not in actions:
            return False
        principal_value = self._federated_value(statement.get("Principal"))
        if principal_value != provider_arn:
            return False
        condition = statement.get("Condition", {})
        if not isinstance(condition, dict):
            return False
        string_like = condition.get("StringLike", {})
        if not isinstance(string_like, dict):
            return False
        return string_like.get(f"{provider_path}:sub") == sa_pattern

    def _ensure_web_identity_statement(
        self,
        *,
        trust_policy: dict[str, Any],
        provider_arn: str,
        provider_path: str,
        sa_pattern: str,
    ) -> bool:
        statements = trust_policy.get("Statement", [])
        if not isinstance(statements, list):
            statements = []
        already_present = any(
            isinstance(statement, dict)
            and self._matches_web_identity_statement(
                statement,
                provider_arn=provider_arn,
                provider_path=provider_path,
                sa_pattern=sa_pattern,
            )
            for statement in statements
        )
        if already_present:
            return True

        statements.append(
            {
                "Effect": "Allow",
                "Principal": {"Federated": provider_arn},
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringLike": {f"{provider_path}:sub": sa_pattern}
                },
            }
        )
        trust_policy["Statement"] = statements
        return False

    def _update_execution_role_policy(
        self,
        *,
        iam_client: Any,
        target: _TrustPolicyTarget,
        trust_policy: dict[str, Any],
        denied_message: str,
        malformed_policy_message: str,
    ) -> None:
        try:
            iam_client.update_assume_role_policy(
                RoleName=target.role_name,
                PolicyDocument=json.dumps(trust_policy),
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            message = exc.response.get("Error", {}).get("Message", "")
            if self._is_access_denied_error(code):
                raise ValueError(denied_message) from None
            if code == "MalformedPolicyDocument":
                raise ValueError(
                    f"Trust policy update failed: {message}. {malformed_policy_message}"
                ) from None
            raise

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
        try:
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
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "")
            message = error.get("Message", "")
            lowered = message.lower()
            if code == "ValidationException" and "already exists in the given namespace" in lowered:
                raise ValueError(
                    "Namespace collision detected while creating EMR virtual cluster. "
                    "Use a unique namespace or delete the existing virtual cluster in that namespace."
                ) from None
            if code in {"AccessDeniedException", "UnauthorizedOperation"}:
                raise ValueError(
                    "Access denied while creating EMR virtual cluster. "
                    "Grant customer_role_arn emr-containers:CreateVirtualCluster and eks:DescribeCluster."
                ) from None
            raise
        return result["id"]

    def check_oidc_provider_association(self, environment: Environment) -> dict[str, str | bool | None]:
        if not environment.eks_cluster_arn:
            raise ValueError("Missing EKS cluster ARN.")
        cluster_name = self._eks_cluster_name_from_arn(environment.eks_cluster_arn)
        account_id = self._account_id_from_arn(environment.eks_cluster_arn)

        if self.settings.dry_run_mode:
            return {
                "associated": True,
                "mode": "dry_run",
                "cluster_name": cluster_name,
                "oidc_issuer": None,
                "oidc_provider_arn": None,
            }

        session = assume_role_session(environment.customer_role_arn, environment.region)
        eks_client = session.client("eks", region_name=environment.region)
        try:
            cluster = eks_client.describe_cluster(name=cluster_name).get("cluster", {})
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "")
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                required = ", ".join(OIDC_DETECTION_REQUIRED_ACTIONS)
                raise ValueError(
                    "Access denied while checking EKS OIDC association. "
                    f"Required permissions: {required}. "
                    "Remediation: grant permissions above to customer_role_arn or run "
                    f"`aws eks describe-cluster --name {cluster_name} --region {environment.region}` "
                    "with an admin role."
                ) from None
            raise

        issuer = cluster.get("identity", {}).get("oidc", {}).get("issuer")
        if not issuer:
            raise ValueError(
                "EKS cluster does not report an OIDC issuer. "
                "Remediation: associate the IAM OIDC provider for this cluster with "
                f"`eksctl utils associate-iam-oidc-provider --cluster {cluster_name} "
                f"--region {environment.region} --approve`, then retry provisioning."
            )

        provider_path = issuer.removeprefix("https://")
        provider_arn = f"arn:aws:iam::{account_id}:oidc-provider/{provider_path}"
        iam_client = session.client("iam")
        try:
            iam_client.get_open_id_connect_provider(OpenIDConnectProviderArn=provider_arn)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "")
            if code in {"NoSuchEntity", "InvalidInput"}:
                return {
                    "associated": False,
                    "cluster_name": cluster_name,
                    "oidc_issuer": issuer,
                    "oidc_provider_arn": provider_arn,
                }
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                required = ", ".join(OIDC_DETECTION_REQUIRED_ACTIONS)
                raise ValueError(
                    "Access denied while checking IAM OIDC provider. "
                    f"Required permissions: {required}. "
                    "Remediation: grant permissions above to customer_role_arn or run "
                    f"`aws iam get-open-id-connect-provider --open-id-connect-provider-arn {provider_arn}` "
                    "with an admin role."
                ) from None
            raise

        return {
            "associated": True,
            "cluster_name": cluster_name,
            "oidc_issuer": issuer,
            "oidc_provider_arn": provider_arn,
        }

    def update_execution_role_trust_policy(self, environment: Environment) -> dict[str, str | bool | None]:
        if not environment.eks_cluster_arn:
            raise ValueError("Missing EKS cluster ARN.")
        if not environment.eks_namespace:
            raise ValueError("Missing EKS namespace.")
        cluster_name = self._eks_cluster_name_from_arn(environment.eks_cluster_arn)

        if self.settings.dry_run_mode:
            return {
                "updated": True,
                "mode": "dry_run",
                "cluster_name": cluster_name,
                "namespace": environment.eks_namespace,
                "role_name": "dry-run",
                "aws_request_id": None,
            }

        target = self._build_trust_policy_target(environment)
        session = assume_role_session(environment.customer_role_arn, environment.region)
        required = ", ".join(TRUST_POLICY_REQUIRED_ACTIONS)
        remediation_cmd = (
            "aws emr-containers update-role-trust-policy "
            f"--cluster-name {target.cluster_name} "
            f"--namespace {target.namespace} "
            f"--role-name {target.role_name} "
            f"--region {target.region}"
        )

        provider_path, provider_arn = self._describe_cluster_oidc(
            session=session,
            target=target,
            denied_message=(
                "Access denied while describing EKS cluster for trust policy update. "
                f"Required permissions: {required}. "
                f"Remediation: run `{remediation_cmd}` with an admin role, "
                "or grant the permissions above to customer_role_arn."
            ),
            missing_oidc_message=(
                f"EKS cluster '{target.cluster_name}' does not have an OIDC issuer. "
                "Remediation: associate the IAM OIDC provider first with "
                f"`eksctl utils associate-iam-oidc-provider --cluster {target.cluster_name} "
                f"--region {target.region} --approve`."
            ),
        )

        iam_client = session.client("iam")
        trust_policy = self._load_execution_role_trust_policy(
            iam_client=iam_client,
            target=target,
            missing_role_message=(
                f"Execution role '{target.role_name}' not found in account {target.account_id}. "
                "Remediation: verify SPARKPILOT_EMR_EXECUTION_ROLE_ARN is correct."
            ),
            denied_message=(
                "Access denied while reading execution role trust policy. "
                f"Required permissions: {required}. "
                "Remediation: grant iam:GetRole to customer_role_arn, or run "
                f"`{remediation_cmd}` with an admin role."
            ),
        )

        sa_pattern = _emr_sa_pattern(target.namespace, target.account_id, target.role_name)
        already_present = self._ensure_web_identity_statement(
            trust_policy=trust_policy,
            provider_arn=provider_arn,
            provider_path=provider_path,
            sa_pattern=sa_pattern,
        )

        self._update_execution_role_policy(
            iam_client=iam_client,
            target=target,
            trust_policy=trust_policy,
            denied_message=(
                "Access denied while updating execution role trust policy. "
                f"Required permissions: {required}. "
                f"Remediation: run `{remediation_cmd}` with an admin role, "
                "or grant the permissions above to customer_role_arn."
            ),
            malformed_policy_message=(
                "Remediation: verify execution role ARN and EKS cluster name, then run "
                f"`{remediation_cmd}`."
            ),
        )

        return {
            "updated": True,
            "already_present": already_present,
            "cluster_name": target.cluster_name,
            "namespace": target.namespace,
            "role_name": target.role_name,
            "provider_arn": provider_arn,
            "sa_pattern": sa_pattern,
        }

    def find_namespace_virtual_cluster_collision(self, environment: Environment) -> dict[str, str | None] | None:
        if not environment.eks_cluster_arn:
            raise ValueError("Missing EKS cluster ARN.")
        if not environment.eks_namespace:
            raise ValueError("Missing EKS namespace.")
        if self.settings.dry_run_mode:
            return None

        cluster_name = self._eks_cluster_name_from_arn(environment.eks_cluster_arn)
        session = assume_role_session(environment.customer_role_arn, environment.region)
        client = session.client("emr-containers", region_name=environment.region)
        try:
            paginator = client.get_paginator("list_virtual_clusters")
            for page in paginator.paginate(containerProviderId=cluster_name, containerProviderType="EKS"):
                for item in page.get("virtualClusters", []):
                    provider = item.get("containerProvider", {})
                    namespace = provider.get("info", {}).get("eksInfo", {}).get("namespace")
                    state = item.get("state")
                    if namespace == environment.eks_namespace and state != "TERMINATED":
                        return {
                            "id": item.get("id"),
                            "name": item.get("name"),
                            "state": state,
                        }
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "")
            if code in {"AccessDeniedException", "UnauthorizedOperation"}:
                raise ValueError(
                    "Unable to evaluate BYOC-Lite namespace collisions. "
                    "Grant customer_role_arn emr-containers:ListVirtualClusters."
                ) from None
            raise
        return None

    def describe_nodegroups(self, environment: Environment) -> list[dict[str, Any]]:
        if not environment.eks_cluster_arn:
            raise ValueError("Missing EKS cluster ARN.")

        cluster_name = self._eks_cluster_name_from_arn(environment.eks_cluster_arn)
        if self.settings.dry_run_mode:
            return [
                {
                    "name": "dry-run-spot",
                    "capacity_type": "SPOT",
                    "instance_types": ["m7g.xlarge", "m7i.xlarge", "r7g.xlarge"],
                    "desired_size": 2,
                }
            ]

        session = assume_role_session(environment.customer_role_arn, environment.region)
        eks_client = session.client("eks", region_name=environment.region)

        try:
            nodegroup_names = eks_client.list_nodegroups(clusterName=cluster_name).get("nodegroups", [])
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                required = ", ".join(SPOT_VALIDATION_REQUIRED_ACTIONS)
                raise ValueError(
                    "Access denied while listing EKS node groups for Spot validation. "
                    f"Required permissions: {required}. "
                    "Remediation: grant permissions above to customer_role_arn and retry preflight."
                ) from None
            raise

        results: list[dict[str, Any]] = []
        for nodegroup_name in nodegroup_names:
            try:
                detail = eks_client.describe_nodegroup(
                    clusterName=cluster_name,
                    nodegroupName=nodegroup_name,
                ).get("nodegroup", {})
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                    required = ", ".join(SPOT_VALIDATION_REQUIRED_ACTIONS)
                    raise ValueError(
                        "Access denied while describing EKS node groups for Spot validation. "
                        f"Required permissions: {required}. "
                        "Remediation: grant permissions above to customer_role_arn and retry preflight."
                    ) from None
                raise
            scaling = detail.get("scalingConfig", {})
            results.append(
                {
                    "name": nodegroup_name,
                    "capacity_type": str(detail.get("capacityType") or "ON_DEMAND"),
                    "instance_types": list(detail.get("instanceTypes") or []),
                    "desired_size": int(scaling.get("desiredSize") or 0),
                }
            )

        return results

    @staticmethod
    def _collect_release_labels(
        *,
        client: Any,
        list_method: str,
        labels_field: str,
        token_field: str,
    ) -> list[str]:
        labels: list[str] = []
        next_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {}
            if next_token:
                kwargs[token_field] = next_token
            result = getattr(client, list_method)(**kwargs)
            for item in result.get(labels_field, []):
                if isinstance(item, str):
                    labels.append(item)
            next_token = result.get(token_field)
            if not next_token:
                return labels

    def list_release_labels(self, region: str) -> list[str]:
        if self.settings.dry_run_mode:
            return [
                "emr-7.10.0-latest",
                "emr-7.9.0-latest",
                "emr-7.8.0-latest",
                "emr-7.7.0-latest",
                "emr-6.15.0-latest",
            ]

        containers_client = boto3.client("emr-containers", region_name=region)
        if hasattr(containers_client, "list_release_labels"):
            return self._collect_release_labels(
                client=containers_client,
                list_method="list_release_labels",
                labels_field="releaseLabels",
                token_field="nextToken",
            )

        emr_client = boto3.client("emr", region_name=region)
        return self._collect_release_labels(
            client=emr_client,
            list_method="list_release_labels",
            labels_field="ReleaseLabels",
            token_field="NextToken",
        )

    @staticmethod
    def _action_values(value: str | list[str] | None) -> list[str]:
        if not value:
            return []
        if isinstance(value, str):
            return [value]
        return [item for item in value if isinstance(item, str)]

    @staticmethod
    def _federated_value(principal: dict[str, Any] | str | None) -> str | None:
        if isinstance(principal, str):
            return principal
        if isinstance(principal, dict):
            candidate = principal.get("Federated")
            if isinstance(candidate, str):
                return candidate
        return None

    def check_execution_role_trust_policy(self, environment: Environment) -> dict[str, str | bool]:
        if not environment.eks_cluster_arn:
            raise ValueError("Missing EKS cluster ARN.")
        if not environment.eks_namespace:
            raise ValueError("Missing EKS namespace.")
        if self.settings.dry_run_mode:
            return {
                "valid": True,
                "mode": "dry_run",
                "provider_arn": "",
                "service_account_pattern": "",
                "role_name": "dry-run",
            }

        target = self._build_trust_policy_target(environment)
        session = assume_role_session(environment.customer_role_arn, environment.region)
        remediation_cmd = (
            "aws emr-containers update-role-trust-policy "
            f"--cluster-name {target.cluster_name} "
            f"--namespace {target.namespace} "
            f"--role-name {target.role_name} "
            f"--region {target.region}"
        )
        provider_path, provider_arn = self._describe_cluster_oidc(
            session=session,
            target=target,
            denied_message=(
                "Access denied while validating execution role trust policy. "
                "Remediation: grant customer_role_arn eks:DescribeCluster and iam:GetRole."
            ),
            missing_oidc_message=(
                f"EKS cluster '{target.cluster_name}' does not expose an OIDC issuer. "
                "Remediation: associate OIDC provider and retry."
            ),
        )
        sa_pattern = _emr_sa_pattern(target.namespace, target.account_id, target.role_name)

        iam_client = session.client("iam")
        trust_policy = self._load_execution_role_trust_policy(
            iam_client=iam_client,
            target=target,
            missing_role_message=(
                f"Execution role '{target.role_name}' not found. "
                "Remediation: verify SPARKPILOT_EMR_EXECUTION_ROLE_ARN."
            ),
            denied_message=(
                "Access denied while reading execution role trust policy. "
                "Remediation: grant customer_role_arn iam:GetRole."
            ),
        )
        statements = trust_policy.get("Statement", [])
        if not isinstance(statements, list):
            statements = []
        matches = any(
            isinstance(statement, dict)
            and self._matches_web_identity_statement(
                statement,
                provider_arn=provider_arn,
                provider_path=provider_path,
                sa_pattern=sa_pattern,
            )
            for statement in statements
        )
        if not matches:
            raise ValueError(
                "Execution role trust policy is missing required EMR on EKS web-identity statement. "
                f"Remediation: run `{remediation_cmd}` and retry."
            )

        return {
            "valid": True,
            "provider_arn": provider_arn,
            "service_account_pattern": sa_pattern,
            "role_name": target.role_name,
        }

    def check_customer_role_dispatch_permissions(self, environment: Environment) -> dict[str, str | bool]:
        if self.settings.dry_run_mode:
            return {
                "dispatch_actions_allowed": True,
                "pass_role_allowed": True,
                "mode": "dry_run",
            }

        validate_runtime_settings(self.settings)
        session = assume_role_session(environment.customer_role_arn, environment.region)
        iam_client = session.client("iam")

        try:
            dispatch_eval = iam_client.simulate_principal_policy(
                PolicySourceArn=environment.customer_role_arn,
                ActionNames=DISPATCH_SIMULATION_ACTIONS,
                ResourceArns=["*"],
            )
            pass_role_eval = iam_client.simulate_principal_policy(
                PolicySourceArn=environment.customer_role_arn,
                ActionNames=["iam:PassRole"],
                ResourceArns=[self.settings.emr_execution_role_arn],
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                raise ValueError(
                    "Unable to validate customer role dispatch permissions via IAM simulation. "
                    "Remediation: grant customer_role_arn iam:SimulatePrincipalPolicy, or "
                    "validate emr-containers:*JobRun and iam:PassRole permissions manually."
                ) from None
            raise

        denied_dispatch: list[str] = []
        for result in dispatch_eval.get("EvaluationResults", []):
            action_name = result.get("EvalActionName", "")
            decision = result.get("EvalDecision", "")
            if decision != "allowed":
                denied_dispatch.append(action_name)
        pass_role_result = next(iter(pass_role_eval.get("EvaluationResults", [])), {})
        pass_role_allowed = pass_role_result.get("EvalDecision", "") == "allowed"

        return {
            "dispatch_actions_allowed": len(denied_dispatch) == 0,
            "pass_role_allowed": pass_role_allowed,
            "denied_dispatch_actions": ", ".join(sorted(denied_dispatch)),
            "execution_role_arn": self.settings.emr_execution_role_arn,
        }

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

        validate_runtime_settings(self.settings)
        session = assume_role_session(environment.customer_role_arn, environment.region)
        client = session.client("emr-containers", region_name=environment.region)
        spark_conf = {**(job.spark_conf_json or {}), **(run.spark_conf_overrides_json or {})}
        spark_submit_driver: dict[str, Any] = {
            "entryPoint": job.artifact_uri,
            "entryPointArguments": run.args_overrides_json or job.args_json,
        }
        if spark_conf:
            spark_submit_driver["sparkSubmitParameters"] = " ".join(
                f"--conf {k}={v}" for k, v in spark_conf.items()
            )

        def _safe_tag_value(value: str | None) -> str:
            return str(value or "")[:256]

        result = client.start_job_run(
            virtualClusterId=environment.emr_virtual_cluster_id,
            name=f"{job.name}-{run.id}",
            executionRoleArn=self.settings.emr_execution_role_arn,
            releaseLabel=self.settings.emr_release_label,
            jobDriver={
                "sparkSubmitJobDriver": spark_submit_driver,
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
            tags={
                "sparkpilot:run_id": _safe_tag_value(run.id),
                "sparkpilot:environment_id": _safe_tag_value(environment.id),
                "sparkpilot:team": _safe_tag_value(environment.tenant_id),
                "sparkpilot:namespace": _safe_tag_value(environment.eks_namespace),
                "sparkpilot:virtual_cluster_id": _safe_tag_value(environment.emr_virtual_cluster_id),
            },
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
        state = "FAILED"
        failure: str | None = None

        if run.cancellation_requested:
            state = "CANCELLED"
        elif self.settings.dry_run_mode:
            if not run.started_at:
                state = "PENDING"
            else:
                elapsed = (datetime.now(UTC) - _as_utc(run.started_at)).total_seconds()
                if elapsed < 10:
                    state = "SUBMITTED"
                elif elapsed < 40:
                    state = "RUNNING"
                else:
                    state = "COMPLETED"
        elif not run.emr_job_run_id:
            failure = "Missing EMR job id."
        else:
            session = assume_role_session(environment.customer_role_arn, environment.region)
            client = session.client("emr-containers", region_name=environment.region)
            try:
                result = client.describe_job_run(
                    virtualClusterId=environment.emr_virtual_cluster_id,
                    id=run.emr_job_run_id,
                )
            except ClientError as exc:
                failure = str(exc)
            else:
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
