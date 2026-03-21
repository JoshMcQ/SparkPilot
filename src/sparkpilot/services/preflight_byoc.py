"""BYOC-Lite specific preflight checks.

Extracted from preflight.py to keep that module focused on the core builder,
TTL cache, and summary helpers.
"""

import os
import re
from typing import Callable

from sparkpilot.aws_clients import EmrEksClient, parse_role_name_from_arn
from sparkpilot.models import Environment

# ---------------------------------------------------------------------------
# BYOC-Lite constants
# ---------------------------------------------------------------------------

BYOC_LITE_CUSTOMER_ROLE_REQUIRED_ACTIONS = [
    "emr-containers:ListVirtualClusters",
    "emr-containers:CreateVirtualCluster",
    "emr-containers:UpdateRoleTrustPolicy",
    "emr-containers:StartJobRun",
    "emr-containers:DescribeJobRun",
    "emr-containers:CancelJobRun",
    "eks:DescribeCluster",
    "iam:GetOpenIDConnectProvider",
    "iam:GetRole",
    "iam:SimulatePrincipalPolicy",
    "iam:UpdateAssumeRolePolicy",
    "iam:PassRole",
    "logs:DescribeLogGroups",
    "logs:DescribeLogStreams",
    "logs:FilterLogEvents",
    "logs:GetLogEvents",
]

RESERVED_BYOC_LITE_NAMESPACES = {"default", "kube-system", "kube-public", "kube-node-lease"}

BYOC_LITE_EXECUTION_ROLE_REQUIRED_ACTIONS = [
    "s3:GetObject",
    "s3:PutObject",
    "logs:CreateLogGroup",
    "logs:CreateLogStream",
    "logs:PutLogEvents",
    "sts:AssumeRoleWithWebIdentity",
]

SPOT_SELECTOR_CONF_KEYS = {
    "spark.kubernetes.executor.node.selector.eks.amazonaws.com/capacityType",
    "spark.kubernetes.executor.node.selector.karpenter.sh/capacity-type",
}
SPOT_TOLERATION_HINTS = ("spot", "capacity-type", "capacitytype")

K8S_NAMESPACE_PATTERN = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$")
EKS_CLUSTER_ARN_PATTERN = re.compile(
    r"^arn:aws[a-zA-Z-]*:eks:[a-z0-9-]+:\d{12}:cluster/[A-Za-z0-9][A-Za-z0-9-_]{0,99}$"
)


# ---------------------------------------------------------------------------
# ARN / cluster helpers
# ---------------------------------------------------------------------------

def _arn_account_id(arn: str | None) -> str | None:
    if not arn:
        return None
    parts = arn.split(":")
    if len(parts) < 6:
        return None
    return parts[4]


def _eks_cluster_region(eks_cluster_arn: str | None) -> str | None:
    if not eks_cluster_arn:
        return None
    parts = eks_cluster_arn.split(":")
    if len(parts) < 6:
        return None
    return parts[3]


def _dispatch_policy_remediation_command(customer_role_name: str) -> str:
    return (
        "aws iam put-role-policy "
        f"--role-name {customer_role_name} "
        "--policy-name SparkPilotByocLiteDispatch "
        "--policy-document '{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"emr-containers:StartJobRun\",\"emr-containers:DescribeJobRun\",\"emr-containers:CancelJobRun\"],\"Resource\":\"*\"}]}'"
    )


def _pass_role_policy_remediation_command(customer_role_name: str, execution_role_arn: str) -> str:
    return (
        "aws iam put-role-policy "
        f"--role-name {customer_role_name} "
        "--policy-name SparkPilotByocLitePassRole "
        "--policy-document '{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"iam:PassRole\"],\"Resource\":[\""
        f"{execution_role_arn}"
        "\"]}]}'"
    )


def _preflight_auto_trust_update_enabled() -> bool:
    value = os.getenv("SPARKPILOT_PREFLIGHT_AUTOFIX_TRUST_POLICY", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


# ---------------------------------------------------------------------------
# Spark conf Spot helpers
# ---------------------------------------------------------------------------

def _spark_conf_has_spot_selector(spark_conf: dict[str, str] | None) -> bool:
    if not spark_conf:
        return False
    for key, value in spark_conf.items():
        value_text = str(value).strip().lower()
        if key in SPOT_SELECTOR_CONF_KEYS and value_text == "spot":
            return True
        if key.startswith("spark.kubernetes.executor.node.selector.") and value_text == "spot":
            return True
    return False


def _spark_conf_has_spot_toleration(spark_conf: dict[str, str] | None) -> bool:
    if not spark_conf:
        return False
    for key, value in spark_conf.items():
        key_text = str(key).lower()
        value_text = str(value).lower()
        if key_text.startswith("spark.kubernetes.executor.toleration."):
            if any(token in value_text for token in SPOT_TOLERATION_HINTS):
                return True
        if key_text == "spark.kubernetes.executor.tolerations":
            if any(token in value_text for token in SPOT_TOLERATION_HINTS):
                return True
    return False


# ---------------------------------------------------------------------------
# BYOC-Lite AWS prechecks
# ---------------------------------------------------------------------------

def _run_byoc_lite_aws_prechecks(
    *,
    environment: Environment,
    spark_conf: dict[str, str] | None,
    aws_precheck_eligible: bool,
    add_check: Callable[..., None],
) -> None:
    if not aws_precheck_eligible:
        _add_byoc_lite_skipped_aws_prechecks(add_check=add_check)
        return

    emr = EmrEksClient()
    _add_byoc_lite_oidc_association_check(emr=emr, environment=environment, add_check=add_check)
    _add_byoc_lite_execution_role_trust_check(emr=emr, environment=environment, add_check=add_check)
    _add_byoc_lite_pod_identity_readiness_check(emr=emr, environment=environment, add_check=add_check)
    _add_byoc_lite_access_entry_mode_check(emr=emr, environment=environment, add_check=add_check)
    _add_byoc_lite_dispatch_permission_checks(emr=emr, environment=environment, add_check=add_check)
    _add_byoc_lite_namespace_collision_check(emr=emr, environment=environment, add_check=add_check)
    _add_byoc_lite_spot_capacity_checks(emr=emr, environment=environment, add_check=add_check)
    _add_byoc_lite_spot_executor_placement_check(spark_conf=spark_conf, add_check=add_check)


def _add_byoc_lite_oidc_association_check(
    *, emr: EmrEksClient, environment: Environment, add_check: Callable[..., None]
) -> None:
    try:
        oidc_result = emr.check_oidc_provider_association(environment)
        if bool(oidc_result.get("associated")):
            add_check(
                code="byoc_lite.oidc_association",
                status_value="pass",
                message="OIDC provider is associated for target EKS cluster.",
                details={
                    "oidc_provider_arn": str(oidc_result.get("oidc_provider_arn") or ""),
                    "cluster_name": str(oidc_result.get("cluster_name") or ""),
                },
            )
            return
        cluster_name = str(oidc_result.get("cluster_name") or "<cluster-name>")
        add_check(
            code="byoc_lite.oidc_association",
            status_value="fail",
            message="OIDC provider is not associated for target EKS cluster.",
            remediation=(
                "Detect+instruct mode (default, no IAM mutation): run "
                f"`eksctl utils associate-iam-oidc-provider --cluster {cluster_name} "
                f"--region {environment.region} --approve` in the customer account. "
                "Optional automation mode can be explicitly enabled later if desired "
                "(SPARKPILOT_PREFLIGHT_AUTOFIX_OIDC_PROVIDER=true)."
            ),
            details={
                "oidc_provider_arn": str(oidc_result.get("oidc_provider_arn") or ""),
                "cluster_name": cluster_name,
                "required_permissions": "eks:DescribeCluster, iam:GetOpenIDConnectProvider, iam:CreateOpenIDConnectProvider",
                "automation_mode": "detect_only",
            },
        )
    except ValueError as exc:
        add_check(
            code="byoc_lite.oidc_association",
            status_value="fail",
            message=str(exc),
            remediation=(
                "Grant customer_role_arn permissions `eks:DescribeCluster` and `iam:GetOpenIDConnectProvider` "
                "for detection (plus `iam:CreateOpenIDConnectProvider` if you want optional automation), "
                "then retry preflight."
            ),
            details={
                "required_permissions": "eks:DescribeCluster, iam:GetOpenIDConnectProvider, iam:CreateOpenIDConnectProvider",
                "automation_mode": "detect_only",
            },
        )


def _add_byoc_lite_execution_role_trust_check(
    *, emr: EmrEksClient, environment: Environment, add_check: Callable[..., None]
) -> None:
    try:
        trust_result = emr.check_execution_role_trust_policy(environment)
        add_check(
            code="byoc_lite.execution_role_trust",
            status_value="pass",
            message="Execution role trust policy includes required EMR web-identity statement.",
            details={
                "role_name": str(trust_result.get("role_name") or ""),
                "provider_arn": str(trust_result.get("provider_arn") or ""),
            },
        )
        return
    except ValueError as exc:
        if _preflight_auto_trust_update_enabled():
            try:
                update_result = emr.update_execution_role_trust_policy(environment)
                trust_result = emr.check_execution_role_trust_policy(environment)
                add_check(
                    code="byoc_lite.execution_role_trust",
                    status_value="pass",
                    message="Execution role trust policy was auto-remediated during preflight.",
                    details={
                        "auto_remediated": True,
                        "updated": bool(update_result.get("updated")),
                        "already_present": bool(update_result.get("already_present")),
                        "role_name": str(trust_result.get("role_name") or update_result.get("role_name") or ""),
                        "provider_arn": str(
                            trust_result.get("provider_arn")
                            or update_result.get("provider_arn")
                            or ""
                        ),
                    },
                )
                return
            except ValueError as update_exc:
                add_check(
                    code="byoc_lite.execution_role_trust",
                    status_value="fail",
                    message=(
                        f"{exc} Auto-remediation attempt failed: {update_exc}"
                    ),
                    remediation=str(update_exc),
                )
                return

        add_check(
            code="byoc_lite.execution_role_trust",
            status_value="fail",
            message=str(exc),
            remediation="Fix execution role trust policy for EMR on EKS service accounts and retry preflight.",
        )


def _add_byoc_lite_pod_identity_readiness_check(
    *, emr: EmrEksClient, environment: Environment, add_check: Callable[..., None]
) -> None:
    """Check if the EKS Pod Identity agent addon is installed (#52)."""
    try:
        result = emr.check_pod_identity_agent(environment)
        if result.get("addon_installed"):
            addon_status = result.get("addon_status", "UNKNOWN")
            if addon_status == "ACTIVE":
                add_check(
                    code="byoc_lite.pod_identity_readiness",
                    status_value="pass",
                    message="EKS Pod Identity agent is installed and active.",
                    details={
                        "addon_status": addon_status,
                        "addon_version": str(result.get("addon_version", "")),
                    },
                )
            else:
                add_check(
                    code="byoc_lite.pod_identity_readiness",
                    status_value="warning",
                    message=f"EKS Pod Identity agent addon is installed but status is {addon_status}.",
                    remediation="Wait for the eks-pod-identity-agent addon to reach ACTIVE status.",
                    details={"addon_status": addon_status},
                )
        else:
            add_check(
                code="byoc_lite.pod_identity_readiness",
                status_value="warning",
                message=(
                    "EKS Pod Identity agent is not installed. "
                    "Using IRSA (IAM Roles for Service Accounts) as fallback."
                ),
                remediation=(
                    "Install the eks-pod-identity-agent addon: "
                    "aws eks create-addon --cluster-name <name> "
                    "--addon-name eks-pod-identity-agent --region <region>"
                ),
            )
    except ValueError as exc:
        add_check(
            code="byoc_lite.pod_identity_readiness",
            status_value="warning",
            message=f"Unable to check Pod Identity readiness: {exc}",
            remediation="Grant customer_role_arn eks:DescribeAddon permission.",
        )


def _add_byoc_lite_access_entry_mode_check(
    *, emr: EmrEksClient, environment: Environment, add_check: Callable[..., None]
) -> None:
    """Check the EKS cluster authentication mode for access entries support (#52)."""
    try:
        result = emr.check_cluster_access_mode(environment)
        auth_mode = result.get("authentication_mode", "CONFIG_MAP")
        if result.get("access_entries_supported"):
            add_check(
                code="byoc_lite.access_entry_mode",
                status_value="pass",
                message=f"EKS cluster authentication mode is {auth_mode}, access entries are supported.",
                details={
                    "authentication_mode": auth_mode,
                    "cluster_name": str(result.get("cluster_name", "")),
                },
            )
        else:
            add_check(
                code="byoc_lite.access_entry_mode",
                status_value="warning",
                message=(
                    f"EKS cluster authentication mode is {auth_mode}. "
                    "Access entries require API or API_AND_CONFIG_MAP mode."
                ),
                remediation=(
                    "Update cluster access configuration: "
                    "aws eks update-cluster-config --name <name> "
                    "--access-config authenticationMode=API_AND_CONFIG_MAP"
                ),
                details={"authentication_mode": auth_mode},
            )
    except ValueError as exc:
        add_check(
            code="byoc_lite.access_entry_mode",
            status_value="warning",
            message=f"Unable to check EKS access entry mode: {exc}",
            remediation="Grant customer_role_arn eks:DescribeCluster permission.",
        )


def _add_byoc_lite_dispatch_permission_checks(
    *, emr: EmrEksClient, environment: Environment, add_check: Callable[..., None]
) -> None:
    try:
        permissions = emr.check_customer_role_dispatch_permissions(environment)
        dispatch_allowed = bool(permissions.get("dispatch_actions_allowed"))
        pass_role_allowed = bool(permissions.get("pass_role_allowed"))
        denied_actions = str(permissions.get("denied_dispatch_actions") or "")
        execution_role_arn = str(permissions.get("execution_role_arn") or "")
        customer_role_name = parse_role_name_from_arn(environment.customer_role_arn) or "<customer-role-name>"

        add_check(
            code="byoc_lite.customer_role_dispatch",
            status_value="pass" if dispatch_allowed else "fail",
            message=(
                "Customer role allows required EMR dispatch actions."
                if dispatch_allowed
                else "Customer role is missing required EMR dispatch actions."
            ),
            remediation=(
                "Add dispatch actions and retry preflight. Command: "
                + _dispatch_policy_remediation_command(customer_role_name)
            )
            if not dispatch_allowed
            else None,
            details={"denied_actions": denied_actions},
        )
        add_check(
            code="byoc_lite.iam_pass_role",
            status_value="pass" if pass_role_allowed else "fail",
            message=(
                "Customer role allows iam:PassRole for execution role."
                if pass_role_allowed
                else "Customer role does not allow iam:PassRole for execution role."
            ),
            remediation=(
                "Grant iam:PassRole on the execution role and retry preflight. Command: "
                + _pass_role_policy_remediation_command(
                    customer_role_name,
                    execution_role_arn or "<execution-role-arn>",
                )
            )
            if not pass_role_allowed
            else None,
            details={"execution_role_arn": execution_role_arn},
        )
    except ValueError as exc:
        customer_role_name = parse_role_name_from_arn(environment.customer_role_arn) or "<customer-role-name>"
        add_check(
            code="byoc_lite.customer_role_dispatch",
            status_value="fail",
            message=str(exc),
            remediation=(
                "Allow IAM simulation for the customer role and rerun preflight. Command: "
                "aws iam put-role-policy "
                f"--role-name {customer_role_name} "
                "--policy-name SparkPilotPreflightSimulation "
                "--policy-document '{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"iam:SimulatePrincipalPolicy\"],\"Resource\":\"*\"}]}'"
            ),
            details={"required_actions": ", ".join(BYOC_LITE_CUSTOMER_ROLE_REQUIRED_ACTIONS)},
        )
        add_check(
            code="byoc_lite.iam_pass_role",
            status_value="fail",
            message="Unable to validate iam:PassRole due to dispatch permission check failure.",
            remediation=(
                "After enabling IAM simulation, rerun preflight and apply PassRole policy if needed. "
                "Required action: iam:PassRole on SPARKPILOT_EMR_EXECUTION_ROLE_ARN."
            ),
        )


def _add_byoc_lite_namespace_collision_check(
    *, emr: EmrEksClient, environment: Environment, add_check: Callable[..., None]
) -> None:
    try:
        collision = emr.find_namespace_virtual_cluster_collision(environment)
    except ValueError as exc:
        add_check(
            code="byoc_lite.namespace_collision",
            status_value="warning",
            message=f"Unable to evaluate namespace collision status: {exc}",
            remediation="Grant customer_role_arn emr-containers:ListVirtualClusters permission.",
        )
        return

    if not collision:
        add_check(
            code="byoc_lite.namespace_collision",
            status_value="pass",
            message="No active EMR virtual-cluster collision detected for eks_namespace.",
            details={"eks_namespace": str(environment.eks_namespace or "")},
        )
        return

    collision_id = str(collision.get("id") or "")
    if environment.emr_virtual_cluster_id and collision_id == str(environment.emr_virtual_cluster_id):
        add_check(
            code="byoc_lite.namespace_collision",
            status_value="pass",
            message="Namespace maps to this environment's configured EMR virtual cluster.",
            details={
                "virtual_cluster_id": collision_id,
                "virtual_cluster_state": str(collision.get("state") or ""),
            },
        )
        return

    add_check(
        code="byoc_lite.namespace_collision",
        status_value="fail",
        message=(
            f"Namespace collision detected: eks_namespace '{environment.eks_namespace}' already maps to "
            f"virtual cluster '{collision_id}' (state={collision.get('state')})."
        ),
        remediation=(
            "Use a unique namespace for this environment, or retire the conflicting virtual cluster. "
            f"Example: aws emr-containers delete-virtual-cluster --id {collision_id} --region {environment.region}"
        ),
        details={
            "collision_virtual_cluster_id": collision_id,
            "collision_virtual_cluster_name": str(collision.get("name") or ""),
            "collision_virtual_cluster_state": str(collision.get("state") or ""),
            "eks_namespace": str(environment.eks_namespace or ""),
        },
    )


def _add_byoc_lite_spot_capacity_checks(
    *, emr: EmrEksClient, environment: Environment, add_check: Callable[..., None]
) -> None:
    try:
        nodegroups = emr.describe_nodegroups(environment)
        spot_nodegroups = [
            item
            for item in nodegroups
            if str(item.get("capacity_type", "")).upper() == "SPOT"
        ]
        if spot_nodegroups:
            add_check(
                code="byoc_lite.spot_capacity",
                status_value="pass",
                message="EKS cluster has Spot-capable managed node groups.",
                details={
                    "spot_nodegroups": len(spot_nodegroups),
                    "total_nodegroups": len(nodegroups),
                },
            )
        elif nodegroups:
            add_check(
                code="byoc_lite.spot_capacity",
                status_value="warning",
                message="No Spot-capable managed node groups were found; workloads may run on on-demand capacity only.",
                remediation=(
                    "Configure at least one Spot-capable node group or Karpenter NodePool "
                    "for executor workloads."
                ),
                details={"total_nodegroups": len(nodegroups)},
            )
        else:
            add_check(
                code="byoc_lite.spot_capacity",
                status_value="warning",
                message="No managed node groups were discovered for Spot validation.",
                remediation=(
                    "If this cluster is Karpenter-only, validate Spot-capable NodePools manually "
                    "or add managed node groups for explicit Spot validation."
                ),
            )

        spot_instance_types = sorted(
            {
                str(instance_type)
                for nodegroup in spot_nodegroups
                for instance_type in (nodegroup.get("instance_types") or [])
            }
        )
        if len(spot_instance_types) >= 3:
            add_check(
                code="byoc_lite.spot_diversification",
                status_value="pass",
                message="Spot instance diversification check passed (>= 3 instance types).",
                details={"spot_instance_types": ", ".join(spot_instance_types)},
            )
        elif spot_nodegroups:
            add_check(
                code="byoc_lite.spot_diversification",
                status_value="warning",
                message="Spot diversification is below recommended threshold (fewer than 3 instance types).",
                remediation=(
                    "Configure at least 3 instance types across Spot capacity pools to reduce "
                    "interruption and capacity risk."
                ),
                details={"spot_instance_types": ", ".join(spot_instance_types)},
            )
        else:
            add_check(
                code="byoc_lite.spot_diversification",
                status_value="warning",
                message="Spot diversification check skipped because no Spot-capable managed node groups were found.",
                remediation=(
                    "Add Spot-capable node groups or Karpenter Spot NodePools with diversified "
                    "instance type requirements."
                ),
            )
    except ValueError as exc:
        add_check(
            code="byoc_lite.spot_capacity",
            status_value="warning",
            message=str(exc),
            remediation=(
                "Grant EKS nodegroup read permissions or validate Spot capacity manually with "
                "`aws eks list-nodegroups` and `aws eks describe-nodegroup`."
            ),
        )
        add_check(
            code="byoc_lite.spot_diversification",
            status_value="warning",
            message="Spot diversification check skipped because Spot node group metadata could not be loaded.",
        )


def _add_byoc_lite_spot_executor_placement_check(
    *, spark_conf: dict[str, str] | None, add_check: Callable[..., None]
) -> None:
    has_spot_selector = _spark_conf_has_spot_selector(spark_conf)
    has_spot_toleration = _spark_conf_has_spot_toleration(spark_conf)
    if has_spot_selector and has_spot_toleration:
        add_check(
            code="byoc_lite.spot_executor_placement",
            status_value="pass",
            message="Executor Spark configuration includes Spot node selectors and toleration hints.",
        )
        return
    if has_spot_selector:
        add_check(
            code="byoc_lite.spot_executor_placement",
            status_value="warning",
            message="Executor Spark configuration has Spot node selectors but no Spot toleration hints.",
            remediation=(
                "Add executor Spot tolerations (for example `spark.kubernetes.executor.tolerations`) "
                "to improve placement on tainted Spot pools."
            ),
        )
        return
    add_check(
        code="byoc_lite.spot_executor_placement",
        status_value="warning",
        message="Executor Spark configuration does not include a Spot node selector.",
        remediation=(
            "Set executor node selector Spark config such as "
            "`spark.kubernetes.executor.node.selector.eks.amazonaws.com/capacityType=SPOT` "
            "or `spark.kubernetes.executor.node.selector.karpenter.sh/capacity-type=spot`."
        ),
    )


def _add_byoc_lite_skipped_aws_prechecks(*, add_check: Callable[..., None]) -> None:
    add_check(
        code="byoc_lite.customer_role_dispatch",
        status_value="warning",
        message="Dispatch permission checks were skipped because base BYOC-Lite prerequisites are not ready.",
        details={"required_actions": ", ".join(BYOC_LITE_CUSTOMER_ROLE_REQUIRED_ACTIONS)},
    )
    add_check(
        code="byoc_lite.iam_pass_role",
        status_value="warning",
        message="iam:PassRole validation was skipped because base BYOC-Lite prerequisites are not ready.",
    )
    add_check(
        code="byoc_lite.execution_role_trust",
        status_value="warning",
        message="Execution role trust validation was skipped because base BYOC-Lite prerequisites are not ready.",
        details={"required_actions": ", ".join(BYOC_LITE_EXECUTION_ROLE_REQUIRED_ACTIONS)},
    )
    add_check(
        code="byoc_lite.oidc_association",
        status_value="warning",
        message="OIDC association check was skipped because base BYOC-Lite prerequisites are not ready.",
    )
    add_check(
        code="byoc_lite.pod_identity_readiness",
        status_value="warning",
        message="Pod Identity readiness check was skipped because base BYOC-Lite prerequisites are not ready.",
    )
    add_check(
        code="byoc_lite.access_entry_mode",
        status_value="warning",
        message="Access entry mode check was skipped because base BYOC-Lite prerequisites are not ready.",
    )
    add_check(
        code="byoc_lite.namespace_collision",
        status_value="warning",
        message="Namespace collision check was skipped because base BYOC-Lite prerequisites are not ready.",
    )
    add_check(
        code="byoc_lite.spot_capacity",
        status_value="warning",
        message="Spot capacity check was skipped because base BYOC-Lite prerequisites are not ready.",
    )
    add_check(
        code="byoc_lite.spot_diversification",
        status_value="warning",
        message="Spot diversification check was skipped because base BYOC-Lite prerequisites are not ready.",
    )
    add_check(
        code="byoc_lite.spot_executor_placement",
        status_value="warning",
        message="Executor Spot placement check was skipped because base BYOC-Lite prerequisites are not ready.",
    )


# ---------------------------------------------------------------------------
# BYOC-Lite configuration checks (entry point called by preflight builder)
# ---------------------------------------------------------------------------

def _add_byoc_lite_configuration_checks(
    *,
    environment: Environment,
    spark_conf: dict[str, str] | None,
    add_check: Callable[..., None],
) -> None:
    if environment.provisioning_mode != "byoc_lite":
        return
    cluster_arn_valid = _add_byoc_lite_cluster_arn_check(environment=environment, add_check=add_check)
    namespace_valid = _add_byoc_lite_namespace_checks(environment=environment, add_check=add_check)
    cluster_region_matches = _add_byoc_lite_cluster_region_check(environment=environment, add_check=add_check)
    accounts_aligned = _add_byoc_lite_account_alignment_check(environment=environment, add_check=add_check)
    aws_precheck_eligible = _is_byoc_lite_aws_precheck_eligible(
        environment=environment,
        cluster_arn_valid=cluster_arn_valid,
        namespace_valid=namespace_valid,
        cluster_region_matches=cluster_region_matches,
        accounts_aligned=accounts_aligned,
    )
    _run_byoc_lite_aws_prechecks(
        environment=environment,
        spark_conf=spark_conf,
        aws_precheck_eligible=aws_precheck_eligible,
        add_check=add_check,
    )


def _add_byoc_lite_cluster_arn_check(*, environment: Environment, add_check: Callable[..., None]) -> bool:
    cluster_arn_valid = bool(environment.eks_cluster_arn and EKS_CLUSTER_ARN_PATTERN.match(environment.eks_cluster_arn))
    if cluster_arn_valid:
        add_check(
            code="byoc_lite.eks_cluster_arn",
            status_value="pass",
            message="eks_cluster_arn is configured.",
        )
    else:
        add_check(
            code="byoc_lite.eks_cluster_arn",
            status_value="fail",
            message="eks_cluster_arn is missing or malformed for BYOC-Lite.",
            remediation="Set eks_cluster_arn to arn:aws:eks:<region>:<account-id>:cluster/<cluster-name>.",
        )
    return cluster_arn_valid


def _add_byoc_lite_namespace_checks(*, environment: Environment, add_check: Callable[..., None]) -> bool:
    namespace = str(environment.eks_namespace or "")
    namespace_trimmed = namespace.strip()

    if namespace:
        add_check(
            code="byoc_lite.eks_namespace",
            status_value="pass",
            message="eks_namespace is configured.",
        )
    else:
        add_check(
            code="byoc_lite.eks_namespace",
            status_value="fail",
            message="eks_namespace is missing for BYOC-Lite.",
            remediation="Set eks_namespace when creating the environment.",
        )

    namespace_trimmed_valid = True
    if namespace and namespace != namespace_trimmed:
        namespace_trimmed_valid = False
        add_check(
            code="byoc_lite.eks_namespace_normalized",
            status_value="fail",
            message="eks_namespace cannot contain leading or trailing whitespace.",
            remediation="Trim spaces and use a normalized namespace value such as `sparkpilot-team`.",
            details={"eks_namespace": namespace, "normalized": namespace_trimmed},
        )
    elif namespace:
        add_check(
            code="byoc_lite.eks_namespace_normalized",
            status_value="pass",
            message="eks_namespace is normalized (no leading/trailing whitespace).",
        )

    namespace_format_valid = bool(namespace_trimmed and K8S_NAMESPACE_PATTERN.match(namespace_trimmed))
    if namespace_format_valid:
        add_check(
            code="byoc_lite.eks_namespace_format",
            status_value="pass",
            message="eks_namespace matches Kubernetes DNS label format.",
        )
    elif namespace_trimmed:
        add_check(
            code="byoc_lite.eks_namespace_format",
            status_value="fail",
            message="eks_namespace must be lowercase alphanumeric with '-' separators.",
            remediation=(
                "Use a namespace like sparkpilot-team. Allowed regex: "
                "^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ (max 63 chars)."
            ),
            details={"eks_namespace": namespace_trimmed},
        )

    namespace_reserved = namespace_trimmed in RESERVED_BYOC_LITE_NAMESPACES
    if namespace_reserved:
        add_check(
            code="byoc_lite.namespace_bootstrap",
            status_value="fail",
            message=f"eks_namespace '{namespace_trimmed}' is reserved and not allowed for BYOC-Lite.",
            remediation=(
                "Create and use a dedicated namespace for SparkPilot workloads, for example "
                "'sparkpilot-team'."
            ),
            details={"eks_namespace": namespace_trimmed},
        )
    elif namespace_trimmed:
        add_check(
            code="byoc_lite.namespace_bootstrap",
            status_value="pass",
            message="eks_namespace is suitable for BYOC-Lite bootstrap.",
        )

    return namespace_trimmed_valid and namespace_format_valid and not namespace_reserved


def _add_byoc_lite_cluster_region_check(*, environment: Environment, add_check: Callable[..., None]) -> bool:
    cluster_region = _eks_cluster_region(environment.eks_cluster_arn)
    cluster_region_matches = bool(cluster_region and cluster_region == environment.region)
    if cluster_region_matches:
        add_check(
            code="byoc_lite.eks_cluster_region",
            status_value="pass",
            message="eks_cluster_arn region matches environment region.",
            details={"cluster_region": cluster_region, "environment_region": environment.region},
        )
    elif cluster_region:
        add_check(
            code="byoc_lite.eks_cluster_region",
            status_value="fail",
            message="eks_cluster_arn region does not match environment region.",
            remediation="Use an EKS cluster ARN in the same region as the environment.",
            details={"cluster_region": cluster_region, "environment_region": environment.region},
        )
    return cluster_region_matches


def _add_byoc_lite_account_alignment_check(*, environment: Environment, add_check: Callable[..., None]) -> bool:
    role_account = _arn_account_id(environment.customer_role_arn)
    cluster_account = _arn_account_id(environment.eks_cluster_arn)
    accounts_aligned = bool(role_account and cluster_account and role_account == cluster_account)
    if accounts_aligned:
        add_check(
            code="byoc_lite.account_alignment",
            status_value="pass",
            message="customer_role_arn account matches eks_cluster_arn account.",
        )
    elif role_account and cluster_account:
        add_check(
            code="byoc_lite.account_alignment",
            status_value="fail",
            message="customer_role_arn account does not match eks_cluster_arn account.",
            remediation="Use a customer role in the same AWS account as the target EKS cluster.",
            details={"role_account_id": role_account, "cluster_account_id": cluster_account},
        )
    return accounts_aligned


def _is_byoc_lite_aws_precheck_eligible(
    *,
    environment: Environment,
    cluster_arn_valid: bool,
    namespace_valid: bool,
    cluster_region_matches: bool,
    accounts_aligned: bool,
) -> bool:
    return (
        environment.status == "ready"
        and bool(environment.emr_virtual_cluster_id)
        and cluster_arn_valid
        and namespace_valid
        and cluster_region_matches
        and accounts_aligned
    )
