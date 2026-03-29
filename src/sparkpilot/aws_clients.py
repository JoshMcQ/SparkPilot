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
from sparkpilot.cost_center import resolve_cost_center_for_environment
from sparkpilot.models import Environment, Job, Run

logger = logging.getLogger(__name__)
ROLE_ARN_PATTERN = re.compile(r"^arn:aws[a-zA-Z-]*:iam::\d{12}:role/(.+)$")
ROLE_ACCOUNT_ARN_PATTERN = re.compile(r"^arn:aws[a-zA-Z-]*:iam::(\d{12}):role/.+$")
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
VIRTUAL_CLUSTER_REFERENCE_REQUIRED_ACTIONS = [
    "emr-containers:DescribeVirtualCluster",
    "eks:DescribeCluster",
]
SPOT_VALIDATION_REQUIRED_ACTIONS = [
    "eks:ListNodegroups",
    "eks:DescribeNodegroup",
]


_BASE36_CHARS = "0123456789abcdefghijklmnopqrstuvwxyz"
_EMR_JOB_NAME_ALLOWED_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_EMR_JOB_NAME_MAX_LENGTH = 64
_EMR_JOB_NAME_RUN_ID_CHARS = 12
_K8S_LABEL_VALUE_DISALLOWED_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
_K8S_LABEL_VALUE_MAX_LENGTH = 63


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


def parse_role_name_from_arn(role_arn: str | None, *, raise_on_invalid: bool = False) -> str | None:
    if not role_arn:
        if raise_on_invalid:
            raise ValueError("Invalid IAM role ARN.")
        return None

    match = ROLE_ARN_PATTERN.match(role_arn)
    if not match:
        if raise_on_invalid:
            raise ValueError("Invalid IAM role ARN.")
        return None

    role_path = match.group(1)
    role_name = role_path.split("/")[-1].strip()
    if role_name:
        return role_name
    if raise_on_invalid:
        raise ValueError("Invalid IAM role ARN.")
    return None


def parse_role_account_id_from_arn(role_arn: str | None) -> str | None:
    if not role_arn:
        return None
    match = ROLE_ACCOUNT_ARN_PATTERN.match(role_arn.strip())
    if not match:
        return None
    return match.group(1)


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _statement_has_action(statement: dict[str, Any], action: str) -> bool:
    return any(candidate == action for candidate in _as_str_list(statement.get("Action")))


def _statement_has_federated_principal(statement: dict[str, Any], provider_arn: str) -> bool:
    principal = statement.get("Principal")
    if isinstance(principal, str):
        return principal == provider_arn
    if not isinstance(principal, dict):
        return False
    federated_values = _as_str_list(principal.get("Federated"))
    return provider_arn in federated_values


def _statement_sub_patterns(statement: dict[str, Any], provider_path: str) -> list[str]:
    condition = statement.get("Condition")
    if not isinstance(condition, dict):
        return []
    key = f"{provider_path}:sub"
    values: list[str] = []
    for operator in ("StringLike", "StringEquals"):
        block = condition.get(operator)
        if not isinstance(block, dict):
            continue
        values.extend(_as_str_list(block.get(key)))
    return values


def _dedupe_trust_statements(statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for statement in statements:
        key = json.dumps(statement, sort_keys=True, separators=(",", ":"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(statement)
    return deduped


def _is_sparkpilot_emr_web_identity_statement(statement: dict[str, Any]) -> bool:
    """Return True if *statement* is a SparkPilot-managed EMR web-identity trust entry.

    Identified by ``sts:AssumeRoleWithWebIdentity`` action with a ``:sub``
    condition whose value contains the ``emr-containers-sa-`` service-account
    prefix that ``_emr_sa_pattern`` generates.
    """
    if not _statement_has_action(statement, "sts:AssumeRoleWithWebIdentity"):
        return False
    condition = statement.get("Condition")
    if not isinstance(condition, dict):
        return False
    for operator in ("StringLike", "StringEquals"):
        block = condition.get(operator)
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if str(key).endswith(":sub"):
                for val in _as_str_list(value):
                    if "emr-containers-sa-" in val:
                        return True
    return False


def _provider_arn_from_trust_statement(statement: dict[str, Any]) -> str | None:
    principal = statement.get("Principal", {})
    if isinstance(principal, dict):
        federated = _as_str_list(principal.get("Federated"))
        return federated[0] if federated else None
    if isinstance(principal, str):
        return principal
    return None


def _sub_patterns_from_trust_statement(statement: dict[str, Any]) -> tuple[str | None, list[str]]:
    condition = statement.get("Condition", {})
    if not isinstance(condition, dict):
        return None, []

    sub_key: str | None = None
    patterns: list[str] = []
    for operator in ("StringLike", "StringEquals"):
        block = condition.get(operator)
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if not str(key).endswith(":sub"):
                continue
            if sub_key is None:
                sub_key = str(key)
            patterns.extend(_as_str_list(value))
    return sub_key, patterns


def _consolidated_web_identity_statement(
    *,
    provider_arn: str,
    sub_key: str,
    patterns: list[str],
) -> dict[str, Any]:
    sub_value: str | list[str] = patterns[0] if len(patterns) == 1 else patterns
    return {
        "Effect": "Allow",
        "Principal": {"Federated": provider_arn},
        "Action": "sts:AssumeRoleWithWebIdentity",
        "Condition": {"StringLike": {sub_key: sub_value}},
    }


def _consolidate_sparkpilot_web_identity_statements(
    statements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge SparkPilot EMR web-identity statements that share the same OIDC
    provider into a single statement per provider with a list-valued
    ``StringLike`` ``:sub`` condition.

    This prevents the trust policy from growing by one statement per namespace
    and hitting the AWS ``ACLSizePerRole=2048`` quota.

    Non-SparkPilot statements are returned unchanged and appear first in the
    result to preserve ordering of customer-authored entries.
    """
    retained: list[dict[str, Any]] = []
    provider_sub_key: dict[str, str] = {}
    provider_patterns: dict[str, list[str]] = {}
    provider_patterns_seen: dict[str, set[str]] = {}

    for stmt in statements:
        if not _is_sparkpilot_emr_web_identity_statement(stmt):
            retained.append(stmt)
            continue

        provider_arn = _provider_arn_from_trust_statement(stmt)
        if not provider_arn:
            retained.append(stmt)
            continue

        sub_key, patterns = _sub_patterns_from_trust_statement(stmt)
        if not sub_key:
            retained.append(stmt)
            continue

        provider_sub_key.setdefault(provider_arn, sub_key)
        provider_patterns.setdefault(provider_arn, [])
        provider_patterns_seen.setdefault(provider_arn, set())

        for pattern in patterns:
            if pattern in provider_patterns_seen[provider_arn]:
                continue
            provider_patterns_seen[provider_arn].add(pattern)
            provider_patterns[provider_arn].append(pattern)

    for provider_arn, patterns in provider_patterns.items():
        sub_key = provider_sub_key[provider_arn]
        retained.append(
            _consolidated_web_identity_statement(
                provider_arn=provider_arn,
                sub_key=sub_key,
                patterns=patterns,
            )
        )

    return retained


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _sanitize_emr_job_name_component(value: str) -> str:
    sanitized = _EMR_JOB_NAME_ALLOWED_PATTERN.sub("-", value.strip())
    sanitized = re.sub(r"-{2,}", "-", sanitized)
    normalized = sanitized.strip("-._")
    return normalized or "run"


def _emr_job_run_name(job_name: str, run_id: str) -> str:
    safe_job = _sanitize_emr_job_name_component(job_name)
    safe_run = _sanitize_emr_job_name_component(run_id)
    suffix = safe_run[-_EMR_JOB_NAME_RUN_ID_CHARS:] or "run"
    prefix_budget = _EMR_JOB_NAME_MAX_LENGTH - len(suffix) - 1
    prefix = safe_job[: max(prefix_budget, 1)].rstrip("-._")
    if not prefix:
        prefix = "run"
    name = f"{prefix}-{suffix}"
    if len(name) <= _EMR_JOB_NAME_MAX_LENGTH:
        return name
    trimmed = name[:_EMR_JOB_NAME_MAX_LENGTH].rstrip("-._")
    if trimmed:
        return trimmed
    return f"run-{suffix}"[:_EMR_JOB_NAME_MAX_LENGTH]


def _safe_k8s_label_value(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    text = _K8S_LABEL_VALUE_DISALLOWED_PATTERN.sub("-", text)
    text = text[:_K8S_LABEL_VALUE_MAX_LENGTH]
    while text and not text[0].isalnum():
        text = text[1:]
    while text and not text[-1].isalnum():
        text = text[:-1]
    return text or "unknown"


def assume_role_session(role_arn: str, region: str, external_id: str | None = None) -> boto3.Session:
    settings_external_id = get_settings().assume_role_external_id
    resolved_external_id = settings_external_id if external_id is None else external_id
    resolved_external_id = resolved_external_id.strip()
    assume_role_kwargs: dict[str, Any] = {
        "RoleArn": role_arn,
        "RoleSessionName": f"sparkpilot-{uuid.uuid4().hex[:8]}",
    }
    if resolved_external_id:
        assume_role_kwargs["ExternalId"] = resolved_external_id

    sts = boto3.client("sts", region_name=region)
    response = sts.assume_role(**assume_role_kwargs)
    creds = response["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=region,
    )


def discover_eks_clusters_for_role(
    *,
    customer_role_arn: str,
    region: str,
    max_clusters: int = 50,
) -> dict[str, Any]:
    role_arn = customer_role_arn.strip()
    region_name = region.strip() or "us-east-1"
    if not role_arn:
        raise ValueError("customer_role_arn is required for BYOC-Lite discovery.")
    if parse_role_name_from_arn(role_arn, raise_on_invalid=False) is None:
        raise ValueError("customer_role_arn must match arn:aws:iam::<12-digit-account-id>:role/<role-name>.")

    settings = get_settings()
    role_account_id = parse_role_account_id_from_arn(role_arn)
    if settings.dry_run_mode:
        sample_account = role_account_id or "123456789012"
        sample_cluster_name = "sparkpilot-dryrun-cluster"
        return {
            "account_id": sample_account,
            "clusters": [
                {
                    "name": sample_cluster_name,
                    "arn": f"arn:aws:eks:{region_name}:{sample_account}:cluster/{sample_cluster_name}",
                    "status": "ACTIVE",
                    "version": "1.31",
                    "oidc_issuer": f"https://oidc.eks.{region_name}.amazonaws.com/id/DRYRUN",
                    "has_oidc": True,
                }
            ],
        }

    try:
        session = assume_role_session(role_arn, region_name)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
            raise ValueError(
                "Unable to assume customer_role_arn for BYOC-Lite discovery. "
                "Remediation: confirm trust policy allows sts:AssumeRole from SparkPilot runtime role, "
                "and if your trust policy enforces ExternalId, configure SPARKPILOT_ASSUME_ROLE_EXTERNAL_ID."
            ) from None
        raise

    sts_client = session.client("sts", region_name=region_name)
    account_id = role_account_id
    try:
        account_id = str(sts_client.get_caller_identity().get("Account") or "").strip() or role_account_id
    except ClientError:
        account_id = role_account_id

    eks_client = session.client("eks", region_name=region_name)
    cluster_names: list[str] = []
    try:
        paginator = eks_client.get_paginator("list_clusters")
        for page in paginator.paginate():
            for cluster_name in page.get("clusters", []):
                if not isinstance(cluster_name, str):
                    continue
                cluster_names.append(cluster_name)
                if len(cluster_names) >= max_clusters:
                    break
            if len(cluster_names) >= max_clusters:
                break
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
            raise ValueError(
                "Access denied while listing EKS clusters for BYOC-Lite discovery. "
                "Remediation: grant customer_role_arn eks:ListClusters and retry."
            ) from None
        raise

    discovered: list[dict[str, Any]] = []
    for cluster_name in sorted(set(cluster_names)):
        try:
            cluster = eks_client.describe_cluster(name=cluster_name).get("cluster", {})
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"ResourceNotFoundException", "NotFoundException"}:
                continue
            if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
                raise ValueError(
                    "Access denied while describing EKS clusters for BYOC-Lite discovery. "
                    "Remediation: grant customer_role_arn eks:DescribeCluster and retry."
                ) from None
            raise

        cluster_arn = str(cluster.get("arn") or "").strip()
        if not cluster_arn and account_id:
            cluster_arn = f"arn:aws:eks:{region_name}:{account_id}:cluster/{cluster_name}"
        oidc_issuer = str(cluster.get("identity", {}).get("oidc", {}).get("issuer") or "").strip() or None
        discovered.append(
            {
                "name": cluster_name,
                "arn": cluster_arn,
                "status": str(cluster.get("status") or "UNKNOWN"),
                "version": str(cluster.get("version") or "").strip() or None,
                "oidc_issuer": oidc_issuer,
                "has_oidc": bool(oidc_issuer),
            }
        )

    return {
        "account_id": account_id,
        "clusters": discovered,
    }


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

    @staticmethod
    def _role_name_from_arn(role_arn: str) -> str:
        role_name = parse_role_name_from_arn(role_arn, raise_on_invalid=True)
        assert role_name is not None
        return role_name

    @staticmethod
    def _account_id_from_arn(arn: str) -> str:
        parts = arn.split(":")
        if len(parts) < 6:
            raise ValueError("Invalid ARN.")
        return parts[4]

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

    def _describe_cluster_for_trust_update(
        self,
        *,
        eks_client: Any,
        cluster_name: str,
        environment: Environment,
        role_name: str,
    ) -> dict[str, Any]:
        try:
            return eks_client.describe_cluster(name=cluster_name).get("cluster", {})
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                required = ", ".join(TRUST_POLICY_REQUIRED_ACTIONS)
                raise ValueError(
                    "Access denied while describing EKS cluster for trust policy update. "
                    f"Required permissions: {required}. "
                    "Remediation: run "
                    f"`aws emr-containers update-role-trust-policy --cluster-name {cluster_name} "
                    f"--namespace {environment.eks_namespace} --role-name {role_name} --region {environment.region}` "
                    "with an admin role, or grant the permissions above to customer_role_arn."
                ) from None
            raise

    def _load_execution_role_trust_policy(
        self,
        *,
        iam_client: Any,
        role_name: str,
        account_id: str,
        environment: Environment,
        cluster_name: str,
    ) -> dict[str, Any]:
        try:
            role_data = iam_client.get_role(RoleName=role_name)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "NoSuchEntity":
                raise ValueError(
                    f"Execution role '{role_name}' not found in account {account_id}. "
                    "Remediation: verify SPARKPILOT_EMR_EXECUTION_ROLE_ARN is correct."
                ) from None
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                required = ", ".join(TRUST_POLICY_REQUIRED_ACTIONS)
                raise ValueError(
                    "Access denied while reading execution role trust policy. "
                    f"Required permissions: {required}. "
                    "Remediation: grant iam:GetRole to customer_role_arn, or run "
                    f"`aws emr-containers update-role-trust-policy --cluster-name {cluster_name} "
                    f"--namespace {environment.eks_namespace} --role-name {role_name} --region {environment.region}` "
                    "with an admin role."
                ) from None
            raise

        trust_policy = role_data["Role"]["AssumeRolePolicyDocument"]
        if isinstance(trust_policy, str):
            return json.loads(trust_policy)
        return trust_policy

    def _merge_sparkpilot_trust_statement(
        self,
        *,
        trust_policy: dict[str, Any],
        provider_arn: str,
        provider_path: str,
        sa_pattern: str,
        role_name: str,
    ) -> bool:
        statements = trust_policy.get("Statement", [])
        if not isinstance(statements, list):
            statements = []
        statements = [stmt for stmt in statements if isinstance(stmt, dict)]
        statements = _dedupe_trust_statements(statements)

        already_present = any(
            _statement_has_action(stmt, "sts:AssumeRoleWithWebIdentity")
            and _statement_has_federated_principal(stmt, provider_arn)
            and sa_pattern in _statement_sub_patterns(stmt, provider_path)
            for stmt in statements
        )
        if not already_present:
            statements.append(
                {
                    "Effect": "Allow",
                    "Principal": {"Federated": provider_arn},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {"StringLike": {f"{provider_path}:sub": sa_pattern}},
                }
            )

        pre_consolidation_count = len(statements)
        statements = _consolidate_sparkpilot_web_identity_statements(statements)
        if len(statements) < pre_consolidation_count:
            logger.info(
                "Consolidated trust policy for role '%s': %d → %d statements.",
                role_name,
                pre_consolidation_count,
                len(statements),
            )
        trust_policy["Statement"] = statements
        return already_present

    def _update_assume_role_policy(
        self,
        *,
        iam_client: Any,
        role_name: str,
        trust_policy: dict[str, Any],
        environment: Environment,
        cluster_name: str,
    ) -> None:
        try:
            iam_client.update_assume_role_policy(
                RoleName=role_name,
                PolicyDocument=json.dumps(trust_policy),
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            message = exc.response.get("Error", {}).get("Message", "")
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                required = ", ".join(TRUST_POLICY_REQUIRED_ACTIONS)
                raise ValueError(
                    "Access denied while updating execution role trust policy. "
                    f"Required permissions: {required}. "
                    "Remediation: run "
                    f"`aws emr-containers update-role-trust-policy --cluster-name {cluster_name} "
                    f"--namespace {environment.eks_namespace} --role-name {role_name} --region {environment.region}` "
                    "with an admin role, or grant the permissions above to customer_role_arn."
                ) from None
            if code == "MalformedPolicyDocument":
                raise ValueError(
                    f"Trust policy update failed: {message}. "
                    "Remediation: verify execution role ARN and EKS cluster name, then run "
                    f"`aws emr-containers update-role-trust-policy --cluster-name {cluster_name} "
                    f"--namespace {environment.eks_namespace} --role-name {role_name} --region {environment.region}`."
                ) from None
            if code in {"LimitExceeded", "LimitExceededException"}:
                raise ValueError(
                    "Execution role trust policy exceeds AWS size quota (ACLSizePerRole=2048). "
                    f"Role '{role_name}' cannot accept additional web-identity trust statements. "
                    "Remediation: prune stale OIDC trust statements on the execution role, or create a fresh "
                    "execution role with a minimal trust policy and set SPARKPILOT_EMR_EXECUTION_ROLE_ARN to it."
                ) from None
            raise

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

        validate_runtime_settings(self.settings)
        role_name = self._role_name_from_arn(self.settings.emr_execution_role_arn)
        account_id = self._account_id_from_arn(environment.eks_cluster_arn)
        session = assume_role_session(environment.customer_role_arn, environment.region)

        eks_client = session.client("eks", region_name=environment.region)
        cluster = self._describe_cluster_for_trust_update(
            eks_client=eks_client,
            cluster_name=cluster_name,
            environment=environment,
            role_name=role_name,
        )

        issuer = cluster.get("identity", {}).get("oidc", {}).get("issuer", "")
        if not issuer:
            raise ValueError(
                f"EKS cluster '{cluster_name}' does not have an OIDC issuer. "
                "Remediation: associate the IAM OIDC provider first with "
                f"`eksctl utils associate-iam-oidc-provider --cluster {cluster_name} "
                f"--region {environment.region} --approve`."
            )

        provider_path = issuer.removeprefix("https://")
        provider_arn = f"arn:aws:iam::{account_id}:oidc-provider/{provider_path}"
        iam_client = session.client("iam")
        trust_policy = self._load_execution_role_trust_policy(
            iam_client=iam_client,
            role_name=role_name,
            account_id=account_id,
            environment=environment,
            cluster_name=cluster_name,
        )

        sa_pattern = _emr_sa_pattern(environment.eks_namespace, account_id, role_name)
        already_present = self._merge_sparkpilot_trust_statement(
            trust_policy=trust_policy,
            provider_arn=provider_arn,
            provider_path=provider_path,
            sa_pattern=sa_pattern,
            role_name=role_name,
        )
        self._update_assume_role_policy(
            iam_client=iam_client,
            role_name=role_name,
            trust_policy=trust_policy,
            environment=environment,
            cluster_name=cluster_name,
        )

        return {
            "updated": True,
            "already_present": already_present,
            "cluster_name": cluster_name,
            "namespace": environment.eks_namespace,
            "role_name": role_name,
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

    def _list_release_labels_from_emr_containers(self, region: str) -> list[str] | None:
        labels: list[str] = []
        containers_client = boto3.client("emr-containers", region_name=region)
        if not hasattr(containers_client, "list_release_labels"):
            return None

        next_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {}
            if next_token:
                kwargs["nextToken"] = next_token
            result = containers_client.list_release_labels(**kwargs)
            labels.extend(item for item in result.get("releaseLabels", []) if isinstance(item, str))
            next_token = result.get("nextToken")
            if not next_token:
                break
        return labels

    def _list_release_labels_from_emr(self, region: str) -> list[str]:
        labels: list[str] = []
        emr_client = boto3.client("emr", region_name=region)
        next_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {}
            if next_token:
                kwargs["NextToken"] = next_token
            result = emr_client.list_release_labels(**kwargs)
            labels.extend(item for item in result.get("ReleaseLabels", []) if isinstance(item, str))
            next_token = result.get("NextToken")
            if not next_token:
                break
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

        labels = self._list_release_labels_from_emr_containers(region)
        if labels is not None:
            return labels
        return self._list_release_labels_from_emr(region)

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

    def _describe_cluster_for_trust_check(
        self,
        *,
        eks_client: Any,
        cluster_name: str,
    ) -> dict[str, Any]:
        try:
            return eks_client.describe_cluster(name=cluster_name).get("cluster", {})
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                raise ValueError(
                    "Access denied while validating execution role trust policy. "
                    "Remediation: grant customer_role_arn eks:DescribeCluster and iam:GetRole."
                ) from None
            raise

    def _load_role_trust_policy_for_check(self, *, iam_client: Any, role_name: str) -> dict[str, Any]:
        try:
            role_data = iam_client.get_role(RoleName=role_name)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "NoSuchEntity":
                raise ValueError(
                    f"Execution role '{role_name}' not found. "
                    "Remediation: verify SPARKPILOT_EMR_EXECUTION_ROLE_ARN."
                ) from None
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                raise ValueError(
                    "Access denied while reading execution role trust policy. "
                    "Remediation: grant customer_role_arn iam:GetRole."
                ) from None
            raise

        trust_policy = role_data["Role"]["AssumeRolePolicyDocument"]
        if isinstance(trust_policy, str):
            return json.loads(trust_policy)
        return trust_policy

    def _trust_statement_matches(
        self,
        *,
        statement: dict[str, Any],
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
        sub_value = string_like.get(f"{provider_path}:sub")
        return sa_pattern in _as_str_list(sub_value)

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

        validate_runtime_settings(self.settings)
        cluster_name = self._eks_cluster_name_from_arn(environment.eks_cluster_arn)
        role_name = self._role_name_from_arn(self.settings.emr_execution_role_arn)
        account_id = self._account_id_from_arn(environment.eks_cluster_arn)
        session = assume_role_session(environment.customer_role_arn, environment.region)

        eks_client = session.client("eks", region_name=environment.region)
        cluster = self._describe_cluster_for_trust_check(eks_client=eks_client, cluster_name=cluster_name)
        issuer = cluster.get("identity", {}).get("oidc", {}).get("issuer", "")
        if not issuer:
            raise ValueError(
                f"EKS cluster '{cluster_name}' does not expose an OIDC issuer. "
                "Remediation: associate OIDC provider and retry."
            )

        provider_path = issuer.removeprefix("https://")
        provider_arn = f"arn:aws:iam::{account_id}:oidc-provider/{provider_path}"
        sa_pattern = _emr_sa_pattern(environment.eks_namespace, account_id, role_name)

        iam_client = session.client("iam")
        trust_policy = self._load_role_trust_policy_for_check(iam_client=iam_client, role_name=role_name)
        statements = trust_policy.get("Statement", [])

        has_match = any(
            isinstance(stmt, dict)
            and self._trust_statement_matches(
                statement=stmt,
                provider_arn=provider_arn,
                provider_path=provider_path,
                sa_pattern=sa_pattern,
            )
            for stmt in statements
        )
        if not has_match:
            raise ValueError(
                "Execution role trust policy is missing required EMR on EKS web-identity statement. "
                "Remediation: run `aws emr-containers update-role-trust-policy --cluster-name "
                f"{cluster_name} --namespace {environment.eks_namespace} --role-name {role_name} "
                f"--region {environment.region}` and retry."
            )

        return {
            "valid": True,
            "provider_arn": provider_arn,
            "service_account_pattern": sa_pattern,
            "role_name": role_name,
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

    # -----------------------------------------------------------------------
    # EKS Pod Identity and Access Entry detection (#52)
    # -----------------------------------------------------------------------

    def check_cluster_access_mode(self, environment: Environment) -> dict[str, str | bool]:
        """Detect the EKS cluster authentication mode (API, API_AND_CONFIG_MAP, CONFIG_MAP).

        Clusters using API or API_AND_CONFIG_MAP support access entries.
        Pod Identity requires the eks-pod-identity-agent addon.
        """
        if not environment.eks_cluster_arn:
            raise ValueError("Missing EKS cluster ARN.")
        cluster_name = self._eks_cluster_name_from_arn(environment.eks_cluster_arn)

        if self.settings.dry_run_mode:
            return {
                "cluster_name": cluster_name,
                "authentication_mode": "API_AND_CONFIG_MAP",
                "access_entries_supported": True,
                "mode": "dry_run",
            }

        session = assume_role_session(environment.customer_role_arn, environment.region)
        eks_client = session.client("eks", region_name=environment.region)
        try:
            cluster = eks_client.describe_cluster(name=cluster_name).get("cluster", {})
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                raise ValueError(
                    "Access denied while checking EKS cluster access mode. "
                    "Remediation: grant customer_role_arn eks:DescribeCluster permission."
                ) from None
            raise

        access_config = cluster.get("accessConfig", {})
        auth_mode = access_config.get("authenticationMode", "CONFIG_MAP")
        access_entries_supported = auth_mode in ("API", "API_AND_CONFIG_MAP")
        return {
            "cluster_name": cluster_name,
            "authentication_mode": auth_mode,
            "access_entries_supported": access_entries_supported,
        }

    def check_pod_identity_agent(self, environment: Environment) -> dict[str, str | bool]:
        """Check whether the eks-pod-identity-agent addon is installed."""
        if not environment.eks_cluster_arn:
            raise ValueError("Missing EKS cluster ARN.")
        cluster_name = self._eks_cluster_name_from_arn(environment.eks_cluster_arn)

        if self.settings.dry_run_mode:
            return {
                "cluster_name": cluster_name,
                "addon_installed": True,
                "addon_status": "ACTIVE",
                "mode": "dry_run",
            }

        session = assume_role_session(environment.customer_role_arn, environment.region)
        eks_client = session.client("eks", region_name=environment.region)
        try:
            addon = eks_client.describe_addon(
                clusterName=cluster_name,
                addonName="eks-pod-identity-agent",
            ).get("addon", {})
            return {
                "cluster_name": cluster_name,
                "addon_installed": True,
                "addon_status": addon.get("status", "UNKNOWN"),
                "addon_version": addon.get("addonVersion", ""),
            }
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "ResourceNotFoundException":
                return {
                    "cluster_name": cluster_name,
                    "addon_installed": False,
                    "addon_status": "NOT_INSTALLED",
                }
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                raise ValueError(
                    "Access denied while checking eks-pod-identity-agent addon. "
                    "Remediation: grant customer_role_arn eks:DescribeAddon permission."
                ) from None
            raise

    def list_pod_identity_associations(self, environment: Environment) -> list[dict]:
        """List EKS Pod Identity associations for the cluster namespace."""
        if not environment.eks_cluster_arn:
            raise ValueError("Missing EKS cluster ARN.")
        if not environment.eks_namespace:
            raise ValueError("Missing EKS namespace.")
        cluster_name = self._eks_cluster_name_from_arn(environment.eks_cluster_arn)

        if self.settings.dry_run_mode:
            return []

        session = assume_role_session(environment.customer_role_arn, environment.region)
        eks_client = session.client("eks", region_name=environment.region)
        try:
            associations = []
            paginator = eks_client.get_paginator("list_pod_identity_associations")
            for page in paginator.paginate(
                clusterName=cluster_name,
                namespace=environment.eks_namespace,
            ):
                associations.extend(page.get("associations", []))
            return associations
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                raise ValueError(
                    "Access denied while listing EKS Pod Identity associations. "
                    "Remediation: grant customer_role_arn "
                    "eks:ListPodIdentityAssociations permission."
                ) from None
            raise

    # ---- EMR on EKS Security Configuration APIs (#53) ----

    def create_security_configuration(
        self,
        environment: Environment,
        *,
        name: str,
        encryption_config: dict | None = None,
        authorization_config: dict | None = None,
    ) -> dict[str, str]:
        """Create an EMR on EKS SecurityConfiguration via emr-containers API."""
        if not environment.emr_virtual_cluster_id:
            raise ValueError("Missing EMR virtual cluster ID.")

        sec_config_data: dict = {}
        if authorization_config:
            sec_config_data["authorizationConfiguration"] = authorization_config
        # Future: encryptionConfiguration when supported by emr-containers
        # For now we store the intent and create via emr-containers API
        if encryption_config:
            sec_config_data["encryptionConfiguration"] = encryption_config

        if self.settings.dry_run_mode:
            import uuid as _uuid
            return {
                "id": f"sc-{_uuid.uuid4().hex[:12]}",
                "name": name,
                "virtual_cluster_id": environment.emr_virtual_cluster_id,
                "mode": "dry_run",
            }

        session = assume_role_session(environment.customer_role_arn, environment.region)
        emr_client = session.client("emr-containers", region_name=environment.region)
        try:
            import uuid as _uuid
            resp = emr_client.create_security_configuration(
                clientToken=str(_uuid.uuid4()),
                name=name,
                securityConfigurationData=sec_config_data,
            )
            return {
                "id": resp.get("id", ""),
                "name": resp.get("name", name),
                "arn": resp.get("arn", ""),
            }
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"AccessDeniedException", "AccessDenied"}:
                raise ValueError(
                    "Access denied creating security configuration. "
                    "Grant emr-containers:CreateSecurityConfiguration."
                ) from None
            raise

    def describe_security_configuration(
        self,
        environment: Environment,
        security_configuration_id: str,
    ) -> dict:
        """Describe an EMR on EKS SecurityConfiguration."""
        if self.settings.dry_run_mode:
            return {
                "id": security_configuration_id,
                "name": f"dry-run-secconfig-{security_configuration_id[:8]}",
                "securityConfigurationData": {},
                "mode": "dry_run",
            }

        session = assume_role_session(environment.customer_role_arn, environment.region)
        emr_client = session.client("emr-containers", region_name=environment.region)
        try:
            resp = emr_client.describe_security_configuration(id=security_configuration_id)
            sc = resp.get("securityConfiguration", {})
            return {
                "id": sc.get("id", security_configuration_id),
                "name": sc.get("name", ""),
                "arn": sc.get("arn", ""),
                "securityConfigurationData": sc.get("securityConfigurationData", {}),
                "createdAt": str(sc.get("createdAt", "")),
            }
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "ResourceNotFoundException":
                raise ValueError(
                    f"Security configuration '{security_configuration_id}' not found."
                ) from None
            if code in {"AccessDeniedException", "AccessDenied"}:
                raise ValueError(
                    "Access denied describing security configuration. "
                    "Grant emr-containers:DescribeSecurityConfiguration."
                ) from None
            raise

    def list_security_configurations(
        self,
        environment: Environment,
    ) -> list[dict]:
        """List EMR on EKS SecurityConfigurations for the virtual cluster."""
        if not environment.emr_virtual_cluster_id:
            raise ValueError("Missing EMR virtual cluster ID.")

        if self.settings.dry_run_mode:
            return []

        session = assume_role_session(environment.customer_role_arn, environment.region)
        emr_client = session.client("emr-containers", region_name=environment.region)
        try:
            configs = []
            paginator = emr_client.get_paginator("list_security_configurations")
            for page in paginator.paginate(
                virtualClusterId=environment.emr_virtual_cluster_id,
            ):
                configs.extend(page.get("securityConfigurations", []))
            return configs
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"AccessDeniedException", "AccessDenied"}:
                raise ValueError(
                    "Access denied listing security configurations. "
                    "Grant emr-containers:ListSecurityConfigurations."
                ) from None
            raise

    def _describe_virtual_cluster(
        self,
        *,
        client: Any,
        virtual_cluster_id: str,
    ) -> dict[str, Any]:
        try:
            result = client.describe_virtual_cluster(id=virtual_cluster_id)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "")
            if code in {"ResourceNotFoundException", "ValidationException"}:
                raise ValueError(
                    f"EMR virtual cluster '{virtual_cluster_id}' was not found. "
                    "Remediation: rerun full-BYOC provisioning_emr stage to recreate and wire the virtual cluster."
                ) from None
            if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
                required = ", ".join(VIRTUAL_CLUSTER_REFERENCE_REQUIRED_ACTIONS)
                raise ValueError(
                    "Access denied while validating EMR virtual cluster reference. "
                    f"Required permissions: {required}. "
                    "Remediation: grant permissions above to customer_role_arn and retry provisioning."
                ) from None
            raise

        virtual_cluster = result.get("virtualCluster", {})
        if not isinstance(virtual_cluster, dict):
            raise ValueError(
                "EMR virtual cluster validation returned an unexpected response shape. "
                "Remediation: retry; if persistent, verify emr-containers API access in customer account."
            )
        return virtual_cluster

    def _validate_virtual_cluster_state(
        self,
        *,
        state: str,
        virtual_cluster_id: str,
        require_running: bool,
    ) -> None:
        if require_running and state != "RUNNING":
            raise ValueError(
                f"EMR virtual cluster '{virtual_cluster_id}' is in state '{state or 'UNKNOWN'}'. "
                "Remediation: wait until RUNNING or rerun provisioning_emr if the cluster does not recover."
            )
        if not require_running and state in {"TERMINATING", "TERMINATED", "ARRESTED"}:
            raise ValueError(
                f"EMR virtual cluster '{virtual_cluster_id}' is in terminal state '{state}'. "
                "Remediation: rerun provisioning_emr to create a healthy virtual cluster."
            )

    def _validate_virtual_cluster_provider(
        self,
        *,
        virtual_cluster_id: str,
        container_provider: dict[str, Any],
        cluster_name: str,
    ) -> str:
        provider_type = str(container_provider.get("type") or "")
        if provider_type and provider_type != "EKS":
            raise ValueError(
                f"EMR virtual cluster '{virtual_cluster_id}' is bound to unsupported provider type '{provider_type}'. "
                "Remediation: recreate the virtual cluster with container provider type EKS."
            )

        provider_cluster = str(container_provider.get("id") or "").strip()
        if provider_cluster and provider_cluster != cluster_name:
            raise ValueError(
                f"EMR virtual cluster '{virtual_cluster_id}' is bound to EKS cluster '{provider_cluster}', "
                f"expected '{cluster_name}'. Remediation: rerun provisioning_emr to bind the correct EKS cluster."
            )
        return provider_cluster

    def _virtual_cluster_namespace(self, container_provider: dict[str, Any]) -> str:
        provider_info = container_provider.get("info", {})
        if not isinstance(provider_info, dict):
            provider_info = {}
        eks_info = provider_info.get("eksInfo", {})
        if not isinstance(eks_info, dict):
            return ""
        return str(eks_info.get("namespace") or "").strip()

    def validate_virtual_cluster_reference(
        self,
        environment: Environment,
        *,
        require_running: bool = False,
    ) -> dict[str, str | bool]:
        if not environment.eks_cluster_arn:
            raise ValueError("Missing EKS cluster ARN.")
        if not environment.emr_virtual_cluster_id:
            raise ValueError("Missing EMR virtual cluster id.")

        cluster_name = self._eks_cluster_name_from_arn(environment.eks_cluster_arn)
        virtual_cluster_id = str(environment.emr_virtual_cluster_id).strip()
        if self.settings.dry_run_mode:
            namespace = environment.eks_namespace or "sparkpilot-system"
            return {
                "valid": True,
                "mode": "dry_run",
                "virtual_cluster_id": virtual_cluster_id,
                "state": "RUNNING",
                "cluster_name": cluster_name,
                "namespace": namespace,
            }

        session = assume_role_session(environment.customer_role_arn, environment.region)
        client = session.client("emr-containers", region_name=environment.region)
        virtual_cluster = self._describe_virtual_cluster(
            client=client,
            virtual_cluster_id=virtual_cluster_id,
        )

        state = str(virtual_cluster.get("state") or "").upper()
        self._validate_virtual_cluster_state(
            state=state,
            virtual_cluster_id=virtual_cluster_id,
            require_running=require_running,
        )

        container_provider = virtual_cluster.get("containerProvider", {})
        if not isinstance(container_provider, dict):
            container_provider = {}
        provider_cluster = self._validate_virtual_cluster_provider(
            virtual_cluster_id=virtual_cluster_id,
            container_provider=container_provider,
            cluster_name=cluster_name,
        )

        namespace_text = self._virtual_cluster_namespace(container_provider)
        if environment.eks_namespace and namespace_text and namespace_text != environment.eks_namespace:
            raise ValueError(
                f"EMR virtual cluster namespace '{namespace_text}' does not match environment namespace "
                f"'{environment.eks_namespace}'. Remediation: rerun provisioning_emr and align namespace wiring."
            )

        return {
            "valid": True,
            "virtual_cluster_id": virtual_cluster_id,
            "state": state or "UNKNOWN",
            "cluster_name": provider_cluster or cluster_name,
            "namespace": namespace_text or environment.eks_namespace or "",
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
        project = environment.eks_namespace or environment.id
        cost_center = resolve_cost_center_for_environment(settings=self.settings, environment=environment)

        chargeback_labels = {
            "sparkpilot-run-id": run.id,
            "sparkpilot-team": environment.tenant_id,
            "sparkpilot-project": project,
            "sparkpilot-cost-center": cost_center,
        }
        for label_key, raw_value in chargeback_labels.items():
            safe_value = _safe_k8s_label_value(raw_value)
            spark_conf.setdefault(f"spark.kubernetes.driver.label.{label_key}", safe_value)
            spark_conf.setdefault(f"spark.kubernetes.executor.label.{label_key}", safe_value)

        _yunikorn_queue = getattr(environment, "yunikorn_queue", None)
        if _yunikorn_queue:
            spark_conf["spark.kubernetes.driver.annotation.yunikorn.apache.org/queue-name"] = _yunikorn_queue
            spark_conf["spark.kubernetes.executor.annotation.yunikorn.apache.org/queue-name"] = _yunikorn_queue

        _event_log_s3_uri = getattr(environment, "event_log_s3_uri", None)
        if _event_log_s3_uri:
            spark_conf.setdefault("spark.eventLog.enabled", "true")
            spark_conf.setdefault("spark.eventLog.dir", _event_log_s3_uri)

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
            name=_emr_job_run_name(job.name, run.id),
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
                "sparkpilot:project": _safe_tag_value(project),
                "sparkpilot:cost_center": _safe_tag_value(cost_center),
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

    def create_job_template(
        self,
        env: Environment,
        *,
        name: str,
        job_driver: dict,
        configuration_overrides: dict,
        tags: dict,
    ) -> str:
        """Create EMR on EKS job template, returns EMR template ID."""
        session = assume_role_session(env.customer_role_arn, env.region)
        client = session.client("emr-containers", region_name=env.region)
        response = client.create_job_template(
            name=name,
            jobTemplateData={
                "executionRoleArn": self.settings.emr_execution_role_arn,
                "releaseLabel": self.settings.emr_release_label or "emr-6.15.0-latest",
                "jobDriver": job_driver,
                "configurationOverrides": configuration_overrides,
            },
            tags=tags,
        )
        return response["id"]

    def describe_job_template(self, env: Environment, template_id: str) -> dict:
        session = assume_role_session(env.customer_role_arn, env.region)
        client = session.client("emr-containers", region_name=env.region)
        return client.describe_job_template(id=template_id)["jobTemplate"]

    def delete_job_template(self, env: Environment, template_id: str) -> None:
        session = assume_role_session(env.customer_role_arn, env.region)
        client = session.client("emr-containers", region_name=env.region)
        client.delete_job_template(id=template_id)

    def list_job_templates(self, env: Environment) -> list[dict]:
        session = assume_role_session(env.customer_role_arn, env.region)
        client = session.client("emr-containers", region_name=env.region)
        paginator = client.get_paginator("list_job_templates")
        templates: list[dict] = []
        for page in paginator.paginate():
            templates.extend(page.get("templates", []))
        return templates

    def create_managed_endpoint(
        self,
        env: Environment,
        *,
        name: str,
        execution_role_arn: str,
        release_label: str,
        certificate_arn: str | None = None,
    ) -> str:
        """Create EMR on EKS managed endpoint, returns endpoint ID."""
        session = assume_role_session(env.customer_role_arn, env.region)
        client = session.client("emr-containers", region_name=env.region)
        kwargs: dict = {
            "name": name,
            "virtualClusterId": env.emr_virtual_cluster_id,
            "type": "JUPYTER_ENTERPRISE_GATEWAY",
            "releaseLabel": release_label,
            "executionRoleArn": execution_role_arn,
        }
        if certificate_arn:
            kwargs["certificateArn"] = certificate_arn
        response = client.create_managed_endpoint(**kwargs)
        return response["id"]

    def describe_managed_endpoint(self, env: Environment, endpoint_id: str) -> dict:
        session = assume_role_session(env.customer_role_arn, env.region)
        client = session.client("emr-containers", region_name=env.region)
        return client.describe_managed_endpoint(
            id=endpoint_id, virtualClusterId=env.emr_virtual_cluster_id
        )["endpoint"]

    def delete_managed_endpoint(self, env: Environment, endpoint_id: str) -> None:
        session = assume_role_session(env.customer_role_arn, env.region)
        client = session.client("emr-containers", region_name=env.region)
        client.delete_managed_endpoint(id=endpoint_id, virtualClusterId=env.emr_virtual_cluster_id)


def detect_yunikorn(env: Environment) -> bool:
    """Return True if YuniKorn scheduler is detected on the EKS cluster."""
    cluster_arn = env.eks_cluster_arn or ""
    if not cluster_arn:
        return False
    try:
        cluster_name = EmrEksClient._eks_cluster_name_from_arn(cluster_arn)
    except ValueError:
        return False
    session = assume_role_session(env.customer_role_arn, env.region)
    eks_client = session.client("eks", region_name=env.region)
    try:
        response = eks_client.describe_addon(
            clusterName=cluster_name,
            addonName="yunikorn",
        )
        return response["addon"]["status"] == "ACTIVE"
    except ClientError as e:
        if e.response["Error"]["Code"] in ("ResourceNotFoundException", "InvalidParameterException"):
            return False
        raise


@dataclass(slots=True)
class EmrServerlessDispatchResult:
    application_id: str
    job_run_id: str
    log_group: str
    log_stream_prefix: str
    driver_log_uri: str | None
    spark_ui_uri: str | None
    aws_request_id: str | None = None


@dataclass(slots=True)
class EmrEc2DispatchResult:
    cluster_id: str
    step_id: str
    log_group: str
    log_stream_prefix: str
    driver_log_uri: str | None
    spark_ui_uri: str | None
    aws_request_id: str | None = None


class EmrServerlessClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _preflight_application(self, client: Any, application_id: str) -> None:
        """Verify the EMR Serverless application exists and is in STARTED state."""
        try:
            result = client.get_application(applicationId=application_id)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "")
            if code in ("ResourceNotFoundException",):
                raise ValueError(
                    f"EMR Serverless application '{application_id}' not found. "
                    "Ensure the application exists in the target account and region."
                ) from exc
            raise
        application = result.get("application", {})
        state = application.get("state", "UNKNOWN")
        if state != "STARTED":
            raise ValueError(
                f"EMR Serverless application '{application_id}' is in state '{state}', expected 'STARTED'. "
                "Start the application before dispatching runs."
            )

    def start_job_run(self, environment: Environment, job: Job, run: Run) -> EmrServerlessDispatchResult:
        application_id = environment.emr_serverless_application_id
        if not application_id:
            raise ValueError(
                f"Environment '{environment.id}' has no emr_serverless_application_id configured."
            )

        log_group = f"{self.settings.log_group_prefix}/{environment.id}"
        stream_prefix = f"{run.id}/attempt-{run.attempt}"

        if self.settings.dry_run_mode:
            job_run_id = f"jr-{uuid.uuid4().hex[:12]}"
            return EmrServerlessDispatchResult(
                application_id=application_id,
                job_run_id=job_run_id,
                log_group=log_group,
                log_stream_prefix=stream_prefix,
                driver_log_uri=f"cloudwatch://{log_group}/{stream_prefix}/driver",
                spark_ui_uri=None,
            )

        validate_runtime_settings(self.settings)
        session = assume_role_session(environment.customer_role_arn, environment.region)
        client = session.client("emr-serverless", region_name=environment.region)
        self._preflight_application(client, application_id)

        spark_conf = {**(job.spark_conf_json or {}), **(run.spark_conf_overrides_json or {})}
        args = run.args_overrides_json or job.args_json or []
        spark_params = " ".join(f"--conf {k}={v}" for k, v in spark_conf.items()) if spark_conf else ""

        spark_submit: dict[str, Any] = {
            "entryPoint": job.artifact_uri,
            "entryPointArguments": [str(a) for a in args],
        }
        if spark_params:
            spark_submit["sparkSubmitParameters"] = spark_params

        start_kwargs: dict[str, Any] = {
            "applicationId": application_id,
            "executionRoleArn": self.settings.emr_execution_role_arn,
            "jobDriver": {"sparkSubmit": spark_submit},
            "name": _emr_job_run_name(job.name, run.id),
            "configurationOverrides": {
                "monitoringConfiguration": {
                    "cloudWatchLoggingConfiguration": {
                        "enabled": True,
                        "logGroupName": log_group,
                        "logStreamNamePrefix": stream_prefix,
                    }
                }
            },
            "tags": {
                "sparkpilot:run_id": run.id[:256],
                "sparkpilot:environment_id": environment.id[:256],
                "sparkpilot:team": (environment.tenant_id or "")[:256],
            },
        }

        result = client.start_job_run(**start_kwargs)
        metadata = result.get("ResponseMetadata", {})
        job_run_id = result["jobRunId"]
        return EmrServerlessDispatchResult(
            application_id=application_id,
            job_run_id=job_run_id,
            log_group=log_group,
            log_stream_prefix=stream_prefix,
            driver_log_uri=f"cloudwatch://{log_group}/{stream_prefix}/driver",
            spark_ui_uri=None,
            aws_request_id=metadata.get("RequestId"),
        )

    def describe_job_run(self, application_id: str, job_run_id: str) -> tuple[str, str | None]:
        if self.settings.dry_run_mode:
            return "RUNNING", None
        try:
            # We need the environment's role ARN to get the session; callers pass pre-created sessions.
            # This method is intended to be called via the reconciliation path which constructs its
            # own session. We expose it here as a direct boto3 call using the platform's default
            # credentials (non-assumed-role) for describe calls originating from the control plane.
            client = boto3.client("emr-serverless")
            result = client.get_job_run(applicationId=application_id, jobRunId=job_run_id)
        except ClientError as exc:
            return "FAILED", str(exc)
        job_run = result.get("jobRun", {})
        state = job_run.get("state", "FAILED")
        failure = job_run.get("stateDetails")
        return state, failure

    def cancel_job_run(self, application_id: str, job_run_id: str) -> str | None:
        if self.settings.dry_run_mode:
            return None
        client = boto3.client("emr-serverless")
        result = client.cancel_job_run(applicationId=application_id, jobRunId=job_run_id)
        metadata = result.get("ResponseMetadata", {})
        return metadata.get("RequestId")


class EmrEc2Client:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _preflight_cluster(self, client: Any, cluster_id: str) -> None:
        """Verify the EMR cluster exists and is in WAITING or RUNNING state."""
        try:
            result = client.describe_cluster(ClusterId=cluster_id)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "")
            if code in ("InvalidRequestException",):
                raise ValueError(
                    f"EMR cluster '{cluster_id}' not found. "
                    "Ensure the cluster exists in the target account and region."
                ) from exc
            raise
        cluster = result.get("Cluster", {})
        status = cluster.get("Status", {})
        state = status.get("State", "UNKNOWN")
        if state not in ("WAITING", "RUNNING"):
            raise ValueError(
                f"EMR cluster '{cluster_id}' is in state '{state}', expected 'WAITING' or 'RUNNING'. "
                "The cluster must be active before dispatching runs."
            )

    def start_job_run(self, environment: Environment, job: Job, run: Run) -> EmrEc2DispatchResult:
        cluster_id = environment.emr_on_ec2_cluster_id
        if not cluster_id:
            raise ValueError(
                f"Environment '{environment.id}' has no emr_on_ec2_cluster_id configured."
            )

        log_group = f"{self.settings.log_group_prefix}/{environment.id}"
        stream_prefix = f"{run.id}/attempt-{run.attempt}"

        if self.settings.dry_run_mode:
            step_id = f"s-{uuid.uuid4().hex[:12].upper()}"
            return EmrEc2DispatchResult(
                cluster_id=cluster_id,
                step_id=step_id,
                log_group=log_group,
                log_stream_prefix=stream_prefix,
                driver_log_uri=f"cloudwatch://{log_group}/{stream_prefix}/driver",
                spark_ui_uri=None,
            )

        validate_runtime_settings(self.settings)
        session = assume_role_session(environment.customer_role_arn, environment.region)
        client = session.client("emr", region_name=environment.region)
        self._preflight_cluster(client, cluster_id)

        spark_conf = {**(job.spark_conf_json or {}), **(run.spark_conf_overrides_json or {})}
        args = run.args_overrides_json or job.args_json or []
        conf_flags: list[str] = []
        for k, v in spark_conf.items():
            conf_flags.extend(["--conf", f"{k}={v}"])

        step_args = ["spark-submit", "--deploy-mode", "cluster"]
        step_args.extend(conf_flags)
        step_args.append(job.artifact_uri)
        step_args.extend(str(a) for a in args)

        result = client.add_job_flow_steps(
            JobFlowId=cluster_id,
            Steps=[
                {
                    "Name": _emr_job_run_name(job.name, run.id),
                    "ActionOnFailure": "CONTINUE",
                    "HadoopJarStep": {
                        "Jar": "command-runner.jar",
                        "Args": step_args,
                    },
                }
            ],
        )
        metadata = result.get("ResponseMetadata", {})
        step_ids: list[str] = result.get("StepIds", [])
        if not step_ids:
            raise ValueError("EMR AddJobFlowSteps returned no StepIds.")
        step_id = step_ids[0]
        return EmrEc2DispatchResult(
            cluster_id=cluster_id,
            step_id=step_id,
            log_group=log_group,
            log_stream_prefix=stream_prefix,
            driver_log_uri=f"cloudwatch://{log_group}/{stream_prefix}/driver",
            spark_ui_uri=None,
            aws_request_id=metadata.get("RequestId"),
        )

    def describe_step(self, cluster_id: str, step_id: str) -> tuple[str, str | None]:
        if self.settings.dry_run_mode:
            return "RUNNING", None
        client = boto3.client("emr")
        try:
            result = client.describe_step(ClusterId=cluster_id, StepId=step_id)
        except ClientError as exc:
            return "FAILED", str(exc)
        step = result.get("Step", {})
        status = step.get("Status", {})
        state = status.get("State", "FAILED")
        failure_details = status.get("FailureDetails", {})
        reason = failure_details.get("Reason") if failure_details else None
        return state, reason

    def cancel_step(self, cluster_id: str, step_id: str) -> str | None:
        if self.settings.dry_run_mode:
            return None
        client = boto3.client("emr")
        result = client.cancel_steps(
            ClusterId=cluster_id,
            StepIds=[step_id],
        )
        metadata = result.get("ResponseMetadata", {})
        return metadata.get("RequestId")


class CloudWatchLogsProxy:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _dry_run_lines(self, log_stream_prefix: str | None) -> list[str]:
        run_hint = log_stream_prefix or "unknown-run"
        return [
            f"[{run_hint}] Spark application started",
            f"[{run_hint}] Executors requested",
            f"[{run_hint}] Job completed successfully",
        ]

    def _collect_log_events(
        self,
        *,
        client: Any,
        log_group: str,
        log_stream_prefix: str | None,
        limit: int,
        start_time_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        request_base: dict[str, Any] = {"logGroupName": log_group, "interleaved": True}
        if log_stream_prefix:
            request_base["logStreamNamePrefix"] = log_stream_prefix
        if start_time_ms is not None:
            request_base["startTime"] = start_time_ms

        events: list[dict[str, Any]] = []
        next_token: str | None = None
        previous_token: str | None = None
        page_count = 0
        max_pages = 25
        page_limit = min(max(limit, 1), 10_000)

        while True:
            request = dict(request_base)
            request["limit"] = page_limit
            if next_token:
                request["nextToken"] = next_token
            response = client.filter_log_events(**request)
            events.extend(response.get("events", []))
            page_count += 1

            next_token = response.get("nextToken")
            if not next_token or next_token == previous_token or page_count >= max_pages:
                break
            previous_token = next_token
        return events

    def _normalize_log_events(self, events: list[dict[str, Any]], limit: int) -> list[str]:
        events.sort(
            key=lambda event: (
                int(event.get("timestamp", 0)),
                int(event.get("ingestionTime", 0)),
                str(event.get("eventId", "")),
            )
        )
        if len(events) > limit:
            events = events[-limit:]
        return [str(event.get("message", "")) for event in events]

    def _raise_cloudwatch_error(
        self,
        *,
        exc: ClientError,
        role_arn: str,
        region: str,
        log_group: str,
        log_stream_prefix: str | None,
    ) -> None:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        error_message = exc.response.get("Error", {}).get("Message", str(exc))
        if error_code == "ResourceNotFoundException":
            return

        logger.warning(
            "CloudWatch log fetch failed for group=%s prefix=%s region=%s role=%s error_code=%s message=%s",
            log_group,
            log_stream_prefix,
            region,
            role_arn,
            error_code,
            error_message,
        )

        mapped_log_errors: dict[str, tuple[int, str]] = {
            "AccessDeniedException": (
                403,
                f"Access denied reading CloudWatch logs (group={log_group}). "
                "Ensure customer_role_arn has logs:FilterLogEvents and logs:GetLogEvents permissions.",
            ),
            "AccessDenied": (
                403,
                f"Access denied reading CloudWatch logs (group={log_group}). "
                "Ensure customer_role_arn has logs:FilterLogEvents and logs:GetLogEvents permissions.",
            ),
            "ThrottlingException": (
                429,
                "CloudWatch Logs API rate limit exceeded. Retry after a short delay.",
            ),
            "Throttling": (
                429,
                "CloudWatch Logs API rate limit exceeded. Retry after a short delay.",
            ),
            "ServiceUnavailableException": (
                503,
                "CloudWatch Logs service is temporarily unavailable. Retry shortly.",
            ),
            "InvalidParameterException": (
                400,
                f"Invalid CloudWatch Logs parameters (group={log_group}, prefix={log_stream_prefix}). "
                "Check log group and stream prefix configuration.",
            ),
        }

        from sparkpilot.exceptions import SparkPilotError

        if error_code in mapped_log_errors:
            status_code, detail = mapped_log_errors[error_code]
            raise SparkPilotError(detail=detail, status_code=status_code) from exc

        raise SparkPilotError(
            detail=f"AWS CloudWatch Logs error ({error_code}): {error_message}",
            status_code=502,
        ) from exc

    def fetch_lines(
        self,
        *,
        role_arn: str,
        region: str,
        log_group: str | None,
        log_stream_prefix: str | None,
        limit: int = 200,
        start_time_ms: int | None = None,
    ) -> list[str]:
        if not log_group:
            return []
        if self.settings.dry_run_mode:
            return self._dry_run_lines(log_stream_prefix)

        try:
            session = assume_role_session(role_arn, region)
            client = session.client("logs", region_name=region)
            events = self._collect_log_events(
                client=client,
                log_group=log_group,
                log_stream_prefix=log_stream_prefix,
                limit=limit,
                start_time_ms=start_time_ms,
            )
            return self._normalize_log_events(events, limit)
        except ClientError as exc:
            self._raise_cloudwatch_error(
                exc=exc,
                role_arn=role_arn,
                region=region,
                log_group=log_group,
                log_stream_prefix=log_stream_prefix,
            )
            return []
