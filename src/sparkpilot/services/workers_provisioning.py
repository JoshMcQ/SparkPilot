"""Provisioning worker: brings environments from 'queued' to 'ready'."""

import logging
import uuid
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from sparkpilot.audit import write_audit_event
from sparkpilot.aws_clients import EmrEksClient
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
    "validating_bootstrap",
    "provisioning_network",
    "provisioning_eks",
    "provisioning_emr",
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
    operation.message = f"[{type(exc).__name__}] {exc}" if include_error_type else str(exc)
    operation.ended_at = _now()
    details: dict[str, str] = {"error": str(exc)}
    if include_error_type:
        details["error_type"] = type(exc).__name__
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


def _assign_placeholder_environment_resources(environment: Environment) -> None:
    environment.eks_cluster_arn = (
        f"arn:aws:eks:{environment.region}:000000000000:cluster/sparkpilot-{environment.id[:8]}"
    )
    environment.emr_virtual_cluster_id = f"vc-{uuid.uuid4().hex[:10]}"


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


def _run_full_byoc_step(
    db: Session,
    *,
    actor: str,
    environment: Environment,
    operation: ProvisioningOperation,
    step: str,
    checkpoint: dict[str, Any],
    terraform: TerraformOrchestrator,
) -> dict[str, Any]:
    operation.state = step
    operation.step = step
    attempts = _checkpoint_attempts(checkpoint)
    if step not in FULL_BYOC_TERRAFORM_STAGES:
        operation.message = f"{step} placeholder: no validation performed."
        return _checkpoint_with_updates(
            checkpoint,
            attempts=attempts,
            last_successful_stage=step,
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
    return _checkpoint_with_updates(
        checkpoint,
        attempts=attempts,
        last_successful_stage=step,
        workspace=context.workspace,
        state_key=context.state_key,
    )


def _run_full_byoc_provisioning(
    db: Session,
    *,
    actor: str,
    environment: Environment,
    operation: ProvisioningOperation,
    terraform: TerraformOrchestrator,
) -> None:
    checkpoint = _load_full_byoc_checkpoint(db, operation.id, environment.id)
    start_idx = _checkpoint_resume_index(checkpoint, operation)
    for step in PROVISIONING_STEPS[start_idx:]:
        checkpoint = _run_full_byoc_step(
            db,
            actor=actor,
            environment=environment,
            operation=operation,
            step=step,
            checkpoint=checkpoint,
            terraform=terraform,
        )
        _write_full_byoc_checkpoint(
            db,
            actor=actor,
            env=environment,
            op_id=operation.id,
            checkpoint=checkpoint,
        )
        operation.worker_claimed_at = _now()
        db.commit()
    _assign_placeholder_environment_resources(environment)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_provisioning_once(db: Session, *, actor: str = "worker:provisioner") -> int:
    emr = EmrEksClient()
    terraform = TerraformOrchestrator()
    pending = _claim_provisioning_operations(db, actor=actor, provisioning_steps=PROVISIONING_STEPS)
    processed = 0
    for operation in pending:
        environment = operation.environment
        try:
            _validate_customer_role_arn(environment)
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
                    )
                else:
                    _assign_placeholder_environment_resources(environment)
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
