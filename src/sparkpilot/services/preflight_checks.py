"""Issue #3 IAM/IRSA dispatch-gate preflight checks.

These checks enforce a deterministic pre-dispatch sequence for BYOC-Lite
EMR on EKS runs:
1. sts:GetCallerIdentity (assumed customer role session)
2. iam:SimulatePrincipalPolicy
3. eks:DescribeCluster
4. IRSA trust/service-account subject validation
"""

from __future__ import annotations

from typing import Any, Callable

from botocore.exceptions import ClientError

from sparkpilot.aws_clients import DISPATCH_SIMULATION_ACTIONS, EmrEksClient, assume_role_session
from sparkpilot.config import get_settings
from sparkpilot.models import Environment
from sparkpilot.services.iam_validation import validate_assume_role_chain

ISSUE3_CHECK_CODES = {
    "sts": "issue3.sts_caller_identity",
    "simulate": "issue3.iam_simulate_principal_policy",
    "describe": "issue3.eks_describe_cluster",
    "irsa": "issue3.irsa_trust_subject",
}


def _add_issue3_dispatch_gate_checks(
    *,
    environment: Environment,
    add_check: Callable[..., None],
) -> None:
    """Add Issue #3 dispatch-gate checks for BYOC-Lite EMR on EKS environments."""
    if environment.engine != "emr_on_eks" or environment.provisioning_mode != "byoc_lite":
        return

    sts_ready = _add_issue3_sts_caller_identity_check(environment=environment, add_check=add_check)
    if not sts_ready:
        _add_skipped(add_check, ISSUE3_CHECK_CODES["simulate"], "Skipped because sts:GetCallerIdentity failed.")
        _add_skipped(add_check, ISSUE3_CHECK_CODES["describe"], "Skipped because sts:GetCallerIdentity failed.")
        _add_skipped(add_check, ISSUE3_CHECK_CODES["irsa"], "Skipped because sts:GetCallerIdentity failed.")
        return

    simulate_ready = _add_issue3_iam_simulation_check(environment=environment, add_check=add_check)
    if not simulate_ready:
        _add_skipped(
            add_check,
            ISSUE3_CHECK_CODES["describe"],
            "Skipped because iam:SimulatePrincipalPolicy failed or required actions were denied.",
        )
        _add_skipped(
            add_check,
            ISSUE3_CHECK_CODES["irsa"],
            "Skipped because iam:SimulatePrincipalPolicy failed or required actions were denied.",
        )
        return

    describe_ready = _add_issue3_eks_describe_cluster_check(environment=environment, add_check=add_check)
    if not describe_ready:
        _add_skipped(add_check, ISSUE3_CHECK_CODES["irsa"], "Skipped because eks:DescribeCluster failed.")
        return

    _add_issue3_irsa_subject_check(environment=environment, add_check=add_check)


def _add_issue3_sts_caller_identity_check(*, environment: Environment, add_check: Callable[..., None]) -> bool:
    if not environment.customer_role_arn:
        add_check(
            code=ISSUE3_CHECK_CODES["sts"],
            status_value="fail",
            message="customer_role_arn is required before running sts:GetCallerIdentity.",
            remediation="Set customer_role_arn to arn:aws:iam::<account-id>:role/<role-name>.",
        )
        return False

    result = validate_assume_role_chain(environment.customer_role_arn, environment.region)
    if result.get("success"):
        add_check(
            code=ISSUE3_CHECK_CODES["sts"],
            status_value="pass",
            message="sts:GetCallerIdentity succeeded for assumed customer role session.",
            details={
                "assumed_identity_arn": str(result.get("assumed_identity_arn") or result.get("assumed_role_arn") or ""),
                "assumed_account": str(result.get("assumed_account") or ""),
            },
        )
        return True

    add_check(
        code=ISSUE3_CHECK_CODES["sts"],
        status_value="fail",
        message=str(result.get("error") or "Unable to validate caller identity for customer role."),
        remediation=str(
            result.get("remediation")
            or "Grant sts:AssumeRole for the runtime principal and verify customer role trust policy."
        ),
        details={"customer_role_arn": environment.customer_role_arn},
    )
    return False


def _add_issue3_iam_simulation_check(*, environment: Environment, add_check: Callable[..., None]) -> bool:
    settings = get_settings()
    if settings.dry_run_mode:
        add_check(
            code=ISSUE3_CHECK_CODES["simulate"],
            status_value="pass",
            message="iam:SimulatePrincipalPolicy checks skipped in dry_run mode.",
            details={"mode": "dry_run"},
        )
        return True

    execution_role_arn = settings.emr_execution_role_arn.strip()
    if not execution_role_arn:
        add_check(
            code=ISSUE3_CHECK_CODES["simulate"],
            status_value="fail",
            message="SPARKPILOT_EMR_EXECUTION_ROLE_ARN is empty; cannot validate iam:PassRole simulation.",
            remediation="Set SPARKPILOT_EMR_EXECUTION_ROLE_ARN to a valid IAM role ARN and retry preflight.",
        )
        return False

    try:
        session = assume_role_session(environment.customer_role_arn, environment.region)
        iam_client = session.client("iam")

        dispatch_eval = iam_client.simulate_principal_policy(
            PolicySourceArn=environment.customer_role_arn,
            ActionNames=[*DISPATCH_SIMULATION_ACTIONS, "eks:DescribeCluster"],
            ResourceArns=["*"],
        )
        pass_role_eval = iam_client.simulate_principal_policy(
            PolicySourceArn=environment.customer_role_arn,
            ActionNames=["iam:PassRole"],
            ResourceArns=[execution_role_arn],
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
            add_check(
                code=ISSUE3_CHECK_CODES["simulate"],
                status_value="fail",
                message=(
                    "Access denied while running iam:SimulatePrincipalPolicy for dispatch prerequisites."
                ),
                remediation=(
                    "Grant customer_role_arn iam:SimulatePrincipalPolicy, or validate StartJobRun/PassRole/"
                    "DescribeCluster permissions manually."
                ),
            )
            return False
        raise

    denied_actions: list[str] = []
    for result in dispatch_eval.get("EvaluationResults", []):
        action_name = str(result.get("EvalActionName") or "")
        if str(result.get("EvalDecision") or "").lower() != "allowed":
            denied_actions.append(action_name)

    pass_role_result = next(iter(pass_role_eval.get("EvaluationResults", [])), {})
    pass_role_allowed = str(pass_role_result.get("EvalDecision") or "").lower() == "allowed"
    if not pass_role_allowed:
        denied_actions.append("iam:PassRole")

    if denied_actions:
        denied_sorted = sorted(set(denied_actions))
        add_check(
            code=ISSUE3_CHECK_CODES["simulate"],
            status_value="fail",
            message="Required dispatch permissions are denied by IAM policy simulation.",
            remediation=(
                "Allow emr-containers:StartJobRun/DescribeJobRun/CancelJobRun, eks:DescribeCluster, "
                "and iam:PassRole on the execution role for customer_role_arn."
            ),
            details={
                "denied_actions": ", ".join(denied_sorted),
                "execution_role_arn": execution_role_arn,
            },
        )
        return False

    add_check(
        code=ISSUE3_CHECK_CODES["simulate"],
        status_value="pass",
        message="iam:SimulatePrincipalPolicy allows dispatch-required actions and iam:PassRole.",
        details={
            "simulated_actions": ", ".join([*DISPATCH_SIMULATION_ACTIONS, "eks:DescribeCluster", "iam:PassRole"]),
            "execution_role_arn": execution_role_arn,
        },
    )
    return True


def _add_issue3_eks_describe_cluster_check(*, environment: Environment, add_check: Callable[..., None]) -> bool:
    settings = get_settings()
    if not environment.eks_cluster_arn:
        add_check(
            code=ISSUE3_CHECK_CODES["describe"],
            status_value="fail",
            message="eks_cluster_arn is required before running eks:DescribeCluster.",
            remediation="Set eks_cluster_arn to the target customer EKS cluster ARN and retry preflight.",
        )
        return False

    if settings.dry_run_mode:
        add_check(
            code=ISSUE3_CHECK_CODES["describe"],
            status_value="pass",
            message="eks:DescribeCluster checks skipped in dry_run mode.",
            details={"mode": "dry_run"},
        )
        return True

    emr = EmrEksClient()
    cluster_name = emr._eks_cluster_name_from_arn(environment.eks_cluster_arn)  # noqa: SLF001

    try:
        session = assume_role_session(environment.customer_role_arn, environment.region)
        eks_client = session.client("eks", region_name=environment.region)
        cluster = eks_client.describe_cluster(name=cluster_name).get("cluster", {})
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation"}:
            add_check(
                code=ISSUE3_CHECK_CODES["describe"],
                status_value="fail",
                message="Access denied while calling eks:DescribeCluster for preflight gating.",
                remediation="Grant customer_role_arn eks:DescribeCluster on the target cluster and retry.",
                details={"cluster_name": cluster_name},
            )
            return False
        raise

    cluster_status = str(cluster.get("status") or "UNKNOWN")
    issuer = str(cluster.get("identity", {}).get("oidc", {}).get("issuer") or "")
    described_arn = str(cluster.get("arn") or "")

    if cluster_status != "ACTIVE":
        add_check(
            code=ISSUE3_CHECK_CODES["describe"],
            status_value="fail",
            message=f"EKS cluster '{cluster_name}' status is {cluster_status}, expected ACTIVE.",
            remediation="Wait for cluster to become ACTIVE before submitting Spark runs.",
            details={"cluster_arn": described_arn, "cluster_status": cluster_status},
        )
        return False

    if not issuer:
        add_check(
            code=ISSUE3_CHECK_CODES["describe"],
            status_value="fail",
            message=(
                f"EKS cluster '{cluster_name}' does not expose an OIDC issuer in DescribeCluster response."
            ),
            remediation=(
                "Associate an IAM OIDC provider for the cluster, then retry preflight. Example: "
                f"eksctl utils associate-iam-oidc-provider --cluster {cluster_name} --region {environment.region} --approve"
            ),
            details={"cluster_arn": described_arn, "cluster_status": cluster_status},
        )
        return False

    add_check(
        code=ISSUE3_CHECK_CODES["describe"],
        status_value="pass",
        message="eks:DescribeCluster succeeded and returned ACTIVE cluster with OIDC issuer.",
        details={
            "cluster_name": cluster_name,
            "cluster_arn": described_arn,
            "cluster_status": cluster_status,
            "oidc_issuer": issuer,
        },
    )
    return True


def _add_issue3_irsa_subject_check(*, environment: Environment, add_check: Callable[..., None]) -> bool:
    emr = EmrEksClient()
    try:
        trust = emr.check_execution_role_trust_policy(environment)
    except ValueError as exc:
        add_check(
            code=ISSUE3_CHECK_CODES["irsa"],
            status_value="fail",
            message=str(exc),
            remediation=(
                "Ensure execution role trust policy contains sts:AssumeRoleWithWebIdentity with "
                "the expected OIDC provider and SparkPilot EMR service-account subject pattern."
            ),
        )
        return False

    add_check(
        code=ISSUE3_CHECK_CODES["irsa"],
        status_value="pass",
        message="IRSA trust policy includes required web-identity principal and service-account subject pattern.",
        details={
            "provider_arn": str(trust.get("provider_arn") or ""),
            "service_account_pattern": str(trust.get("service_account_pattern") or ""),
            "role_name": str(trust.get("role_name") or ""),
        },
    )
    return True


def _add_skipped(add_check: Callable[..., None], code: str, message: str) -> None:
    add_check(
        code=code,
        status_value="warning",
        message=message,
    )
