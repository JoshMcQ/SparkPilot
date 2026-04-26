"""Provisioning worker: brings environments from 'queued' to 'ready'."""

import logging
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from sparkpilot.audit import write_audit_event
from sparkpilot.aws_clients import EmrEksClient
from sparkpilot.config import get_settings
from sparkpilot.error_handling import error_details, error_message
from sparkpilot.exceptions import ProvisioningPermanentError
from sparkpilot.models import Environment, ProvisioningOperation
from sparkpilot.terraform_orchestrator import TerraformApplyResult, TerraformOrchestrator, TerraformPlanResult
from sparkpilot.services._helpers import _now
from sparkpilot.services.preflight import (
    _build_preflight,
    _preflight_summary,
)
from sparkpilot.services.workers_common import (
    _claim_provisioning_operations,
    _release_operation_claim,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provisioning step constants & checkpoint helpers
# ---------------------------------------------------------------------------

PROVISIONING_STEPS = [
    "provisioning_network",
    "provisioning_eks",
    "provisioning_emr",
    "validating_bootstrap",
    "validating_runtime",
]
FULL_BYOC_TERRAFORM_STAGES = {"provisioning_network", "provisioning_eks", "provisioning_emr"}
FULL_BYOC_CHECKPOINT_AUDIT_ACTION = "environment.full_byoc_checkpoint"

KNOWN_GOOD_VPC_ENDPOINTS = [
    "ec2",
    "ecr.api",
    "ecr.dkr",
    "s3",
    "logs",
    "sts",
    "eks",
    "eks-auth",
    "elasticloadbalancing",
]
REQUIRED_FULL_BYOC_OUTPUTS = ("eks_cluster_arn", "emr_virtual_cluster_id")
FULL_BYOC_RUNTIME_PREFLIGHT_CODES = {
    "config.execution_role",
    "config.log_group_prefix",
    "config.emr_release_label",
    "environment.customer_role_arn",
    "environment.virtual_cluster",
}


def _new_full_byoc_checkpoint() -> dict[str, Any]:
    return {
        "terraform_workspace": None,
        "terraform_state_key": None,
        "last_successful_stage": None,
        "attempt_count_by_stage": {},
        "artifacts": [],
    }


def _full_byoc_start_index(op: ProvisioningOperation) -> int:
    if op.step in PROVISIONING_STEPS:
        return PROVISIONING_STEPS.index(op.step)
    if op.state in PROVISIONING_STEPS:
        return PROVISIONING_STEPS.index(op.state)
    return 0


def _checkpoint_resume_index(checkpoint: dict[str, Any], op: ProvisioningOperation) -> int:
    """Resume from the stage after the last successful one in the checkpoint."""
    last = checkpoint.get("last_successful_stage")
    if isinstance(last, str) and last in PROVISIONING_STEPS:
        return PROVISIONING_STEPS.index(last) + 1
    return _full_byoc_start_index(op)


def _checkpoint_attempts(checkpoint: dict[str, Any]) -> dict[str, int]:
    raw = checkpoint.get("attempt_count_by_stage", {})
    if not isinstance(raw, dict):
        return {}
    attempts: dict[str, int] = {}
    for key, value in raw.items():
        try:
            attempts[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return attempts


def _checkpoint_with_updates(
    checkpoint: dict[str, Any],
    *,
    attempts: dict[str, int],
    last_successful_stage: str | None,
    workspace: str | None = None,
    state_key: str | None = None,
) -> dict[str, Any]:
    artifacts = checkpoint.get("artifacts", [])
    if not isinstance(artifacts, list):
        artifacts = []
    return {
        "terraform_workspace": workspace if workspace is not None else checkpoint.get("terraform_workspace"),
        "terraform_state_key": state_key if state_key is not None else checkpoint.get("terraform_state_key"),
        "last_successful_stage": last_successful_stage,
        "attempt_count_by_stage": attempts,
        "artifacts": artifacts,
    }


def _record_full_byoc_stage_artifact(
    checkpoint: dict[str, Any],
    *,
    step: str,
    attempt: int,
    kind: str,
    result: TerraformPlanResult | TerraformApplyResult,
) -> dict[str, Any]:
    artifacts = checkpoint.get("artifacts", [])
    if not isinstance(artifacts, list):
        artifacts = []
    entry: dict[str, Any] = {
        "stage": step,
        "attempt": attempt,
        "kind": kind,
        "ok": result.ok,
        "command": " ".join(result.command),
        "error": result.error,
        "stdout_excerpt": result.stdout_excerpt,
        "stderr_excerpt": result.stderr_excerpt,
    }
    if isinstance(result, TerraformPlanResult):
        entry["plan_path"] = result.plan_path
    artifacts.append(entry)
    if len(artifacts) > 40:
        artifacts = artifacts[-40:]
    updated = dict(checkpoint)
    updated["artifacts"] = artifacts
    return updated


def _record_full_byoc_validation_artifact(
    checkpoint: dict[str, Any],
    *,
    step: str,
    attempt: int,
    ok: bool,
    summary: str,
    details: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    artifacts = checkpoint.get("artifacts", [])
    if not isinstance(artifacts, list):
        artifacts = []
    entry: dict[str, Any] = {
        "stage": step,
        "attempt": attempt,
        "kind": "validation",
        "ok": ok,
        "summary": summary,
        "error": error,
        "details": details or {},
    }
    artifacts.append(entry)
    if len(artifacts) > 40:
        artifacts = artifacts[-40:]
    updated = dict(checkpoint)
    updated["artifacts"] = artifacts
    return updated


def _load_full_byoc_checkpoint(db: Session, op_id: str, env_id: str) -> dict[str, Any]:
    from sqlalchemy import and_, select
    from sparkpilot.models import AuditEvent
    events = list(
        db.execute(
            select(AuditEvent)
            .where(
                and_(
                    AuditEvent.action == FULL_BYOC_CHECKPOINT_AUDIT_ACTION,
                    AuditEvent.entity_type == "environment",
                    AuditEvent.entity_id == env_id,
                )
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(25)
        ).scalars()
    )
    for event in events:
        details = event.details_json if isinstance(event.details_json, dict) else {}
        if details.get("operation_id") != op_id:
            continue
        checkpoint = details.get("checkpoint")
        if isinstance(checkpoint, dict):
            return checkpoint
    return _new_full_byoc_checkpoint()


def _write_full_byoc_checkpoint(
    db: Session,
    *,
    actor: str,
    env: Environment,
    op_id: str,
    checkpoint: dict[str, Any],
) -> None:
    write_audit_event(
        db,
        actor=actor,
        action=FULL_BYOC_CHECKPOINT_AUDIT_ACTION,
        entity_type="environment",
        entity_id=env.id,
        tenant_id=env.tenant_id,
        details={
            "operation_id": op_id,
            "stage": checkpoint.get("last_successful_stage"),
            "checkpoint": checkpoint,
        },
    )


# ---------------------------------------------------------------------------
# Provisioning state helpers
# ---------------------------------------------------------------------------

def _validate_customer_role_arn(environment: Environment) -> None:
    if not environment.customer_role_arn.startswith("arn:aws:iam::"):
        raise ValueError("Invalid customer role ARN.")


def _set_provisioning_ready(
    db: Session,
    *,
    actor: str,
    environment: Environment,
    operation: ProvisioningOperation,
    action: str,
    message: str,
    details: dict[str, Any],
) -> None:
    environment.status = "ready"
    operation.state = "ready"
    operation.step = "ready"
    operation.message = message
    operation.ended_at = _now()
    write_audit_event(
        db,
        actor=actor,
        action=action,
        entity_type="environment",
        entity_id=environment.id,
        tenant_id=environment.tenant_id,
        details=details,
    )


def _set_provisioning_failed(
    db: Session,
    *,
    actor: str,
    environment: Environment,
    operation: ProvisioningOperation,
    exc: Exception,
    include_error_type: bool,
) -> None:
    environment.status = "failed"
    operation.state = "failed"
    operation.step = "failed"
    operation.message = error_message(exc, include_type=include_error_type)
    operation.ended_at = _now()
    details = error_details(exc, include_type=include_error_type)
    write_audit_event(
        db,
        actor=actor,
        action="environment.provisioning_failed",
        entity_type="environment",
        entity_id=environment.id,
        tenant_id=environment.tenant_id,
        details=details,
    )


def _audit_byoc_lite_event(
    db: Session,
    *,
    actor: str,
    environment: Environment,
    action: str,
    details: dict[str, Any],
) -> None:
    write_audit_event(
        db,
        actor=actor,
        action=action,
        entity_type="environment",
        entity_id=environment.id,
        tenant_id=environment.tenant_id,
        details=details,
    )


def _extract_terraform_output(outputs: dict[str, Any], key: str) -> str:
    raw = outputs.get(key)
    if isinstance(raw, dict):
        candidate = raw.get("value")
    else:
        candidate = raw
    if not isinstance(candidate, str):
        return ""
    return candidate.strip()


def _account_id_from_role_arn(role_arn: str) -> str:
    parts = role_arn.split(":")
    if len(parts) >= 5 and len(parts[4]) == 12 and parts[4].isdigit():
        return parts[4]
    raise ValueError(f"Cannot extract AWS account ID from role ARN: {role_arn!r}")


def _assign_full_byoc_outputs(environment: Environment, outputs: dict[str, Any]) -> None:
    values = {
        key: _extract_terraform_output(outputs, key)
        for key in REQUIRED_FULL_BYOC_OUTPUTS
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        if get_settings().dry_run_mode:
            account_id = _account_id_from_role_arn(environment.customer_role_arn)
            if not values["eks_cluster_arn"]:
                values["eks_cluster_arn"] = (
                    f"arn:aws:eks:{environment.region}:{account_id}:cluster/sparkpilot-{environment.id[:8]}"
                )
            if not values["emr_virtual_cluster_id"]:
                values["emr_virtual_cluster_id"] = f"vc-dryrun-{environment.id[:8]}"
        else:
            missing_csv = ", ".join(missing)
            raise ValueError(
                "Full BYOC Terraform apply completed but required outputs are missing: "
                f"{missing_csv}. "
                "Define these outputs in infra/terraform/full-byoc and retry provisioning."
            )
    environment.eks_cluster_arn = values["eks_cluster_arn"]
    environment.emr_virtual_cluster_id = values["emr_virtual_cluster_id"]


# ---------------------------------------------------------------------------
# BYOC-Lite provisioning
# ---------------------------------------------------------------------------

def _run_byoc_lite_provisioning(
    db: Session,
    *,
    actor: str,
    environment: Environment,
    operation: ProvisioningOperation,
    emr: EmrEksClient,
) -> None:
    operation.state = "validating_runtime"
    operation.step = "validating_runtime"
    operation.message = "Validating BYOC-Lite runtime."
    prerequisites = _build_preflight(
        environment,
        require_environment_ready=False,
        require_virtual_cluster=False,
        db=db,
    )
    _audit_byoc_lite_event(
        db,
        actor=actor,
        environment=environment,
        action="environment.byoc_lite_prerequisites_evaluated",
        details={
            "ready": prerequisites["ready"],
            "summary": _preflight_summary(prerequisites["checks"], include_warnings=True),
            "checks": prerequisites["checks"],
        },
    )
    if not prerequisites["ready"]:
        raise ValueError(
            "BYOC-Lite prerequisites failed: "
            + _preflight_summary(prerequisites["checks"], include_remediation=True)
        )

    if environment.emr_virtual_cluster_id is None:
        _run_byoc_lite_oidc_and_trust_setup(db, actor=actor, environment=environment, emr=emr)

    if not environment.emr_virtual_cluster_id:
        _run_byoc_lite_virtual_cluster_creation(db, actor=actor, environment=environment, emr=emr)

    _set_provisioning_ready(
        db,
        actor=actor,
        environment=environment,
        operation=operation,
        action="environment.byoc_lite_provisioned",
        message="BYOC-Lite environment ready.",
        details={
            "eks_cluster_arn": environment.eks_cluster_arn,
            "eks_namespace": environment.eks_namespace,
            "emr_virtual_cluster_id": environment.emr_virtual_cluster_id,
        },
    )


def _run_byoc_lite_oidc_and_trust_setup(
    db: Session,
    *,
    actor: str,
    environment: Environment,
    emr: EmrEksClient,
) -> None:
    # Detect identity path: Pod Identity or IRSA (#52)
    identity_mode = "irsa"  # default fallback
    try:
        pod_id_result = emr.check_pod_identity_agent(environment)
        if pod_id_result.get("addon_installed") and pod_id_result.get("addon_status") == "ACTIVE":
            identity_mode = "pod_identity"
            _audit_byoc_lite_event(
                db,
                actor=actor,
                environment=environment,
                action="environment.byoc_lite_identity_detected",
                details={
                    "identity_mode": "pod_identity",
                    "addon_status": pod_id_result.get("addon_status"),
                    "addon_version": pod_id_result.get("addon_version", ""),
                },
            )
    except Exception:
        logger.warning(
            "Pod Identity agent check failed for environment %s; falling back to IRSA.",
            environment.id,
            exc_info=True,
        )

    if identity_mode == "irsa":
        _audit_byoc_lite_event(
            db,
            actor=actor,
            environment=environment,
            action="environment.byoc_lite_identity_detected",
            details={"identity_mode": "irsa", "reason": "Pod Identity agent not available"},
        )

    # Record identity mode on the environment
    environment.identity_mode = identity_mode
    db.flush()

    oidc_result = emr.check_oidc_provider_association(environment)
    _audit_byoc_lite_event(
        db,
        actor=actor,
        environment=environment,
        action="environment.byoc_lite_oidc_checked",
        details={
            "eks_cluster_arn": environment.eks_cluster_arn,
            "eks_namespace": environment.eks_namespace,
            "result": oidc_result,
        },
    )
    if not bool(oidc_result.get("associated")):
        cluster_name = oidc_result.get("cluster_name") or "<cluster-name>"
        raise ValueError(
            "OIDC provider is not associated for the target EKS cluster. "
            f"Remediation: run `eksctl utils associate-iam-oidc-provider --cluster {cluster_name} "
            f"--region {environment.region} --approve` in the customer account, then retry provisioning."
        )

    try:
        trust_policy_result = emr.update_execution_role_trust_policy(environment)
    except ValueError as exc:
        _audit_byoc_lite_event(
            db,
            actor=actor,
            environment=environment,
            action="environment.byoc_lite_trust_policy_failed",
            details={
                "eks_cluster_arn": environment.eks_cluster_arn,
                "eks_namespace": environment.eks_namespace,
                "error": str(exc),
            },
        )
        raise
    _audit_byoc_lite_event(
        db,
        actor=actor,
        environment=environment,
        action="environment.byoc_lite_trust_policy_updated",
        details={
            "eks_cluster_arn": environment.eks_cluster_arn,
            "eks_namespace": environment.eks_namespace,
            "result": trust_policy_result,
        },
    )


def _run_byoc_lite_virtual_cluster_creation(
    db: Session,
    *,
    actor: str,
    environment: Environment,
    emr: EmrEksClient,
) -> None:
    collision = emr.find_namespace_virtual_cluster_collision(environment)
    if collision:
        _audit_byoc_lite_event(
            db,
            actor=actor,
            environment=environment,
            action="environment.byoc_lite_namespace_collision",
            details={
                "eks_cluster_arn": environment.eks_cluster_arn,
                "eks_namespace": environment.eks_namespace,
                "collision_virtual_cluster_id": collision.get("id"),
                "collision_virtual_cluster_name": collision.get("name"),
                "collision_virtual_cluster_state": collision.get("state"),
            },
        )
        raise ValueError(
            "BYOC-Lite namespace collision detected: "
            f"namespace '{environment.eks_namespace}' on cluster '{environment.eks_cluster_arn}' "
            f"is already associated with virtual cluster '{collision.get('id')}' "
            f"(state={collision.get('state')}). "
            "Remediation: use a unique namespace for this environment or delete/retire the "
            "existing virtual cluster before retrying."
        )
    environment.emr_virtual_cluster_id = emr.create_virtual_cluster(environment)


# ---------------------------------------------------------------------------
# Full BYOC (Terraform) provisioning
# ---------------------------------------------------------------------------

def _record_full_byoc_stage_failure(
    db: Session,
    *,
    actor: str,
    environment: Environment,
    operation: ProvisioningOperation,
    step: str,
    stage_attempt: int,
    phase: str,
    failure_message: str,
    checkpoint: dict[str, Any],
    attempts: dict[str, int],
) -> None:
    attempts[step] = stage_attempt
    _write_full_byoc_checkpoint(
        db,
        actor=actor,
        env=environment,
        op_id=operation.id,
        checkpoint=_checkpoint_with_updates(
            checkpoint,
            attempts=attempts,
            last_successful_stage=checkpoint.get("last_successful_stage"),
        ),
    )
    operation.worker_claimed_at = _now()
    db.commit()
    raise ValueError(f"Full BYOC stage '{step}' {phase} failed: {failure_message}")


def _run_full_byoc_bootstrap_validation(
    *,
    environment: Environment,
    emr: EmrEksClient,
) -> dict[str, Any]:
    settings = get_settings()
    if settings.dry_run_mode and (not environment.eks_cluster_arn or not environment.emr_virtual_cluster_id):
        _assign_full_byoc_outputs(environment, {})

    missing_outputs: list[str] = []
    if not environment.eks_cluster_arn:
        missing_outputs.append("eks_cluster_arn")
    if not environment.emr_virtual_cluster_id:
        missing_outputs.append("emr_virtual_cluster_id")
    if missing_outputs:
        missing_csv = ", ".join(missing_outputs)
        raise ValueError(
            "Full BYOC bootstrap validation failed: required Terraform outputs are missing "
            f"({missing_csv}). Remediation: ensure provisioning_emr exports these outputs and rerun provisioning."
        )

    virtual_cluster = emr.validate_virtual_cluster_reference(environment, require_running=False)
    discovered_namespace = str(virtual_cluster.get("namespace") or "").strip()
    if discovered_namespace:
        environment.eks_namespace = discovered_namespace
    if not environment.eks_namespace:
        raise ValueError(
            "Full BYOC bootstrap validation failed: EKS namespace could not be inferred from the EMR virtual cluster. "
            "Remediation: ensure provisioning_emr creates a namespace-scoped virtual cluster and surfaces namespace output."
        )

    oidc_result = emr.check_oidc_provider_association(environment)
    if not bool(oidc_result.get("associated")):
        cluster_name = str(oidc_result.get("cluster_name") or "<cluster-name>")
        raise ValueError(
            "Full BYOC bootstrap validation failed: EKS OIDC provider association is missing. "
            f"Remediation: run `eksctl utils associate-iam-oidc-provider --cluster {cluster_name} "
            f"--region {environment.region} --approve` in the customer account."
        )

    trust_result = emr.check_execution_role_trust_policy(environment)
    return {
        "eks_cluster_arn": environment.eks_cluster_arn,
        "eks_namespace": environment.eks_namespace,
        "virtual_cluster": virtual_cluster,
        "oidc_association": oidc_result,
        "execution_role_trust": trust_result,
    }


def _run_full_byoc_runtime_validation(
    db: Session,
    *,
    environment: Environment,
    emr: EmrEksClient,
) -> dict[str, Any]:
    virtual_cluster = emr.validate_virtual_cluster_reference(environment, require_running=True)
    discovered_namespace = str(virtual_cluster.get("namespace") or "").strip()
    if discovered_namespace:
        environment.eks_namespace = discovered_namespace
    if not environment.eks_namespace:
        raise ValueError(
            "Full BYOC runtime validation failed: EKS namespace is missing. "
            "Remediation: ensure provisioning_emr outputs a namespace-bound EMR virtual cluster."
        )

    preflight = _build_preflight(
        environment,
        require_environment_ready=False,
        require_virtual_cluster=True,
        db=db,
    )
    runtime_checks = [
        check
        for check in preflight["checks"]
        if check.get("code") in FULL_BYOC_RUNTIME_PREFLIGHT_CODES
    ]
    failed_runtime_checks = [check for check in runtime_checks if check.get("status") == "fail"]
    if failed_runtime_checks:
        raise ValueError(
            "Full BYOC runtime validation failed: "
            + _preflight_summary(runtime_checks, include_remediation=True)
        )

    trust_result = emr.check_execution_role_trust_policy(environment)
    permissions = emr.check_customer_role_dispatch_permissions(environment)
    dispatch_allowed = bool(permissions.get("dispatch_actions_allowed"))
    pass_role_allowed = bool(permissions.get("pass_role_allowed"))
    if not dispatch_allowed or not pass_role_allowed:
        denied_dispatch_actions = str(permissions.get("denied_dispatch_actions") or "").strip()
        raise ValueError(
            "Full BYOC runtime validation failed: customer role dispatch readiness is incomplete. "
            f"Denied dispatch actions: {denied_dispatch_actions or 'none reported'}, "
            f"iam:PassRole allowed: {pass_role_allowed}. "
            "Remediation: grant customer_role_arn emr-containers:StartJobRun, "
            "emr-containers:DescribeJobRun, emr-containers:CancelJobRun, and iam:PassRole "
            "on SPARKPILOT_EMR_EXECUTION_ROLE_ARN."
        )

    return {
        "virtual_cluster": virtual_cluster,
        "runtime_preflight_summary": _preflight_summary(runtime_checks, include_warnings=True),
        "runtime_preflight_checks": runtime_checks,
        "execution_role_trust": trust_result,
        "dispatch_permissions": permissions,
    }


def _run_full_byoc_step(
    db: Session,
    *,
    actor: str,
    environment: Environment,
    operation: ProvisioningOperation,
    step: str,
    checkpoint: dict[str, Any],
    terraform: TerraformOrchestrator,
    emr: EmrEksClient,
) -> tuple[dict[str, Any], dict[str, Any]]:
    operation.state = step
    operation.step = step
    attempts = _checkpoint_attempts(checkpoint)
    if step not in FULL_BYOC_TERRAFORM_STAGES:
        stage_attempt = attempts.get(step, 0) + 1
        operation.message = f"{step}: running full-BYOC validation checks (attempt {stage_attempt})."
        try:
            if step == "validating_bootstrap":
                details = _run_full_byoc_bootstrap_validation(
                    environment=environment,
                    emr=emr,
                )
                summary = "bootstrap prerequisites validated (EKS/OIDC/trust + virtual cluster wiring)."
            elif step == "validating_runtime":
                details = _run_full_byoc_runtime_validation(
                    db,
                    environment=environment,
                    emr=emr,
                )
                summary = "runtime readiness validated (preflight + execution-role trust + dispatch permissions)."
            else:
                raise ValueError(f"Unsupported full-BYOC validation step '{step}'.")
        except ValueError as exc:
            checkpoint = _record_full_byoc_validation_artifact(
                checkpoint,
                step=step,
                attempt=stage_attempt,
                ok=False,
                summary=f"{step} validation failed.",
                error=str(exc),
            )
            _record_full_byoc_stage_failure(
                db,
                actor=actor,
                environment=environment,
                operation=operation,
                step=step,
                stage_attempt=stage_attempt,
                phase="validation",
                failure_message=str(exc),
                checkpoint=checkpoint,
                attempts=attempts,
            )

        attempts[step] = stage_attempt
        checkpoint = _record_full_byoc_validation_artifact(
            checkpoint,
            step=step,
            attempt=stage_attempt,
            ok=True,
            summary=summary,
            details=details,
        )
        operation.message = f"{step}: {summary}"
        return (
            _checkpoint_with_updates(
                checkpoint,
                attempts=attempts,
                last_successful_stage=step,
            ),
            {},
        )

    stage_attempt = attempts.get(step, 0) + 1
    context = terraform.build_stage_context(operation, environment, step, attempt=stage_attempt)
    operation.message = f"{step}: terraform plan/apply attempt {stage_attempt} (workspace={context.workspace})."

    plan_result = terraform.plan(context)
    checkpoint = _record_full_byoc_stage_artifact(
        checkpoint,
        step=step,
        attempt=stage_attempt,
        kind="plan",
        result=plan_result,
    )
    if not plan_result.ok:
        _record_full_byoc_stage_failure(
            db,
            actor=actor,
            environment=environment,
            operation=operation,
            step=step,
            stage_attempt=stage_attempt,
            phase="plan",
            failure_message=plan_result.error or plan_result.stderr_excerpt,
            checkpoint=checkpoint,
            attempts=attempts,
        )

    apply_result = terraform.apply(context, plan_result)
    checkpoint = _record_full_byoc_stage_artifact(
        checkpoint,
        step=step,
        attempt=stage_attempt,
        kind="apply",
        result=apply_result,
    )
    if not apply_result.ok:
        _record_full_byoc_stage_failure(
            db,
            actor=actor,
            environment=environment,
            operation=operation,
            step=step,
            stage_attempt=stage_attempt,
            phase="apply",
            failure_message=apply_result.error or apply_result.stderr_excerpt,
            checkpoint=checkpoint,
            attempts=attempts,
        )

    attempts[step] = stage_attempt
    return (
        _checkpoint_with_updates(
            checkpoint,
            attempts=attempts,
            last_successful_stage=step,
            workspace=context.workspace,
            state_key=context.state_key,
        ),
        dict(apply_result.outputs or {}),
    )


def _run_full_byoc_provisioning(
    db: Session,
    *,
    actor: str,
    environment: Environment,
    operation: ProvisioningOperation,
    terraform: TerraformOrchestrator,
    emr: EmrEksClient,
) -> None:
    checkpoint = _load_full_byoc_checkpoint(db, operation.id, environment.id)
    start_idx = _checkpoint_resume_index(checkpoint, operation)
    terraform_outputs: dict[str, Any] = {}
    for step in PROVISIONING_STEPS[start_idx:]:
        checkpoint, step_outputs = _run_full_byoc_step(
            db,
            actor=actor,
            environment=environment,
            operation=operation,
            step=step,
            checkpoint=checkpoint,
            terraform=terraform,
            emr=emr,
        )
        if step_outputs:
            terraform_outputs.update(step_outputs)
            _assign_full_byoc_outputs(environment, terraform_outputs)
        _write_full_byoc_checkpoint(
            db,
            actor=actor,
            env=environment,
            op_id=operation.id,
            checkpoint=checkpoint,
        )
        operation.worker_claimed_at = _now()
        db.commit()
    if not environment.eks_cluster_arn or not environment.emr_virtual_cluster_id:
        _assign_full_byoc_outputs(environment, terraform_outputs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_provisioning_once(db: Session, *, actor: str = "worker:provisioner") -> int:
    emr = EmrEksClient()
    terraform = TerraformOrchestrator()
    settings = get_settings()
    pending = _claim_provisioning_operations(db, actor=actor, provisioning_steps=PROVISIONING_STEPS)
    processed = 0
    for operation in pending:
        environment = operation.environment
        try:
            _validate_customer_role_arn(environment)
            if settings.dry_run_mode and environment.engine in {"emr_serverless", "emr_on_ec2"}:
                _set_provisioning_ready(
                    db,
                    actor=actor,
                    environment=environment,
                    operation=operation,
                    action="environment.dry_run_provisioned",
                    message=f"{environment.engine} dry-run environment ready.",
                    details={
                        "engine": environment.engine,
                        "dry_run_mode": True,
                        "preflight": "skipped",
                    },
                )
                continue
            if environment.provisioning_mode == "byoc_lite":
                _run_byoc_lite_provisioning(
                    db,
                    actor=actor,
                    environment=environment,
                    operation=operation,
                    emr=emr,
                )
            else:
                if environment.provisioning_mode == "full":
                    _run_full_byoc_provisioning(
                        db,
                        actor=actor,
                        environment=environment,
                        operation=operation,
                        terraform=terraform,
                        emr=emr,
                    )
                else:
                    raise ValueError(f"Unsupported provisioning_mode '{environment.provisioning_mode}'.")
                _set_provisioning_ready(
                    db,
                    actor=actor,
                    environment=environment,
                    operation=operation,
                    action="environment.provisioned",
                    message="Environment provisioning complete.",
                    details={
                        "eks_cluster_arn": environment.eks_cluster_arn,
                        "emr_virtual_cluster_id": environment.emr_virtual_cluster_id,
                        "validated_vpc_endpoints": KNOWN_GOOD_VPC_ENDPOINTS,
                    },
                )
        except (ClientError, BotoCoreError) as exc:
            logger.exception(
                "AWS error during provisioning environment_id=%s operation_id=%s error_type=%s",
                environment.id,
                operation.id,
                type(exc).__name__,
            )
            _set_provisioning_failed(
                db,
                actor=actor,
                environment=environment,
                operation=operation,
                exc=exc,
                include_error_type=True,
            )
        except (ValueError, ProvisioningPermanentError) as exc:
            logger.exception(
                "Provisioning validation/permanent failure environment_id=%s operation_id=%s error_type=%s",
                environment.id,
                operation.id,
                type(exc).__name__,
            )
            _set_provisioning_failed(
                db,
                actor=actor,
                environment=environment,
                operation=operation,
                exc=exc,
                include_error_type=True,
            )
        except Exception as exc:  # noqa: BLE001 — final fallback; prevents stuck operations on truly unexpected errors
            logger.exception(
                "Unexpected error during provisioning environment_id=%s operation_id=%s error_type=%s",
                environment.id,
                operation.id,
                type(exc).__name__,
            )
            _set_provisioning_failed(
                db,
                actor=actor,
                environment=environment,
                operation=operation,
                exc=exc,
                include_error_type=False,
            )
        finally:
            _release_operation_claim(operation)
            processed += 1
    if processed:
        db.commit()
    return processed
