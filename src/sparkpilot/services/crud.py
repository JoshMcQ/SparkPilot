"""Entity CRUD operations: tenants, teams, users, environments, jobs, runs."""

from datetime import UTC, datetime
import logging
import uuid
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from sparkpilot.config import get_settings
from sparkpilot.exceptions import ConflictError, EntityNotFoundError, ValidationError

from sparkpilot.audit import write_audit_event
from sparkpilot.aws_clients import CloudWatchLogsProxy
from sparkpilot.models import (
    Environment,
    GoldenPath,
    Job,
    ProvisioningOperation,
    Run,
    Team,
    TeamEnvironmentScope,
    Tenant,
    UserIdentity,
    UsageRecord,
)
from sparkpilot.quota import enforce_quota_for_run, lock_environment_for_quota
from sparkpilot.schemas import (
    EnvironmentCreateRequest,
    JobCreateRequest,
    RunCreateRequest,
    TeamCreateRequest,
    TenantCreateRequest,
    UserIdentityCreateRequest,
)
from sparkpilot.terraform_orchestrator import FULL_BYOC_TERRAFORM_ROOT
from sparkpilot.services._helpers import (
    ACTIVE_RUN_STATES,
    TERMINAL_RUN_STATES,
    _now,
    _require_environment,
    _require_job,
    _require_run,
    _require_team,
    _require_tenant,
    _validate_custom_spark_conf_policy,
)
from sparkpilot.services.golden_paths import _resolve_golden_path_for_run
from sparkpilot.services.preflight import _build_preflight


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------

def create_tenant(
    db: Session,
    req: "TenantCreateRequest",
    actor: str,
    source_ip: str | None,
    *,
    commit: bool = True,
) -> Tenant:
    existing = db.execute(select(Tenant).where(Tenant.name == req.name)).scalar_one_or_none()
    if existing:
        raise ConflictError("Tenant name already exists.")
    tenant = Tenant(name=req.name)
    db.add(tenant)
    db.flush()
    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action="tenant.create",
        entity_type="tenant",
        entity_id=tenant.id,
        tenant_id=tenant.id,
        details={"name": tenant.name},
    )
    if commit:
        db.commit()
        db.refresh(tenant)
    else:
        db.flush()
    return tenant


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

def create_team(
    db: Session,
    req: "TeamCreateRequest",
    *,
    actor: str,
    source_ip: str | None,
) -> Team:
    _require_tenant(db, req.tenant_id)
    existing = db.execute(
        select(Team).where(
            and_(
                Team.tenant_id == req.tenant_id,
                Team.name == req.name,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("Team name already exists for tenant.")
    row = Team(tenant_id=req.tenant_id, name=req.name)
    db.add(row)
    db.flush()
    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action="team.create",
        entity_type="team",
        entity_id=row.id,
        tenant_id=req.tenant_id,
        details={"team_name": row.name},
    )
    db.commit()
    db.refresh(row)
    return row


def list_teams(db: Session, tenant_id: str | None = None, *, limit: int = 200, offset: int = 0) -> list[Team]:
    stmt = select(Team).order_by(Team.created_at.desc())
    if tenant_id:
        stmt = stmt.where(Team.tenant_id == tenant_id)
    stmt = stmt.limit(limit).offset(offset)
    return list(db.execute(stmt).scalars())


# ---------------------------------------------------------------------------
# User identity
# ---------------------------------------------------------------------------

def create_or_update_user_identity(
    db: Session,
    req: "UserIdentityCreateRequest",
    *,
    actor: str,
    source_ip: str | None,
) -> UserIdentity:
    if req.role in {"operator", "user"}:
        if not req.tenant_id or not req.team_id:
            raise ValidationError("tenant_id and team_id are required for operator/user roles.")
    if req.tenant_id:
        _require_tenant(db, req.tenant_id)
    team: Team | None = None
    if req.team_id:
        team = _require_team(db, req.team_id)
    if req.tenant_id and team and team.tenant_id != req.tenant_id:
        raise ValidationError("team_id must belong to tenant_id.")
    row = db.execute(select(UserIdentity).where(UserIdentity.actor == req.actor)).scalar_one_or_none()
    action = "user_identity.update"
    if row is None:
        row = UserIdentity(actor=req.actor, role=req.role)
        db.add(row)
        action = "user_identity.create"
    db.flush()
    row.role = req.role
    row.tenant_id = req.tenant_id
    row.team_id = req.team_id
    row.active = req.active
    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action=action,
        entity_type="user_identity",
        entity_id=row.id,
        tenant_id=req.tenant_id,
        details={
            "actor": row.actor,
            "role": row.role,
            "tenant_id": row.tenant_id,
            "team_id": row.team_id,
            "active": row.active,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def list_user_identities(db: Session, *, limit: int = 200, offset: int = 0) -> list[UserIdentity]:
    return list(
        db.execute(
            select(UserIdentity).order_by(UserIdentity.created_at.desc()).limit(limit).offset(offset)
        ).scalars()
    )


# ---------------------------------------------------------------------------
# Team ↔ Environment scoping
# ---------------------------------------------------------------------------

def add_team_environment_scope(
    db: Session,
    team_id: str,
    environment_id: str,
    *,
    actor: str,
    source_ip: str | None,
) -> TeamEnvironmentScope:
    team = _require_team(db, team_id)
    env = _require_environment(db, environment_id)
    if team.tenant_id != env.tenant_id:
        raise ValidationError("Team and environment must belong to the same tenant.")
    row = db.execute(
        select(TeamEnvironmentScope).where(
            and_(
                TeamEnvironmentScope.team_id == team_id,
                TeamEnvironmentScope.environment_id == environment_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = TeamEnvironmentScope(team_id=team_id, environment_id=environment_id)
        db.add(row)
        db.flush()
        write_audit_event(
            db,
            actor=actor,
            source_ip=source_ip,
            action="team_environment_scope.create",
            entity_type="team_environment_scope",
            entity_id=row.id,
            tenant_id=team.tenant_id,
            details={
                "team_id": team.id,
                "team_name": team.name,
                "environment_id": env.id,
            },
        )
        db.commit()
        db.refresh(row)
    return row


def remove_team_environment_scope(
    db: Session,
    team_id: str,
    environment_id: str,
    *,
    actor: str,
    source_ip: str | None,
) -> None:
    """Remove a team-environment scope (unassign an environment from a team)."""
    team = _require_team(db, team_id)
    row = db.execute(
        select(TeamEnvironmentScope).where(
            and_(
                TeamEnvironmentScope.team_id == team_id,
                TeamEnvironmentScope.environment_id == environment_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise EntityNotFoundError("TeamEnvironmentScope", f"{team_id}/{environment_id}")
    scope_id = row.id
    db.delete(row)
    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action="team_environment_scope.delete",
        entity_type="team_environment_scope",
        entity_id=scope_id,
        tenant_id=team.tenant_id,
        details={
            "team_id": team_id,
            "team_name": team.name,
            "environment_id": environment_id,
        },
    )
    db.commit()


def list_team_environment_scopes(
    db: Session,
    team_id: str,
    *,
    limit: int = 200,
    offset: int = 0,
) -> list[TeamEnvironmentScope]:
    _require_team(db, team_id)
    return list(
        db.execute(
            select(TeamEnvironmentScope)
            .where(TeamEnvironmentScope.team_id == team_id)
            .order_by(TeamEnvironmentScope.created_at.asc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def list_environments(db: Session, tenant_id: str | None, *, limit: int = 200, offset: int = 0) -> list[Environment]:
    stmt = select(Environment).order_by(Environment.created_at.desc())
    if tenant_id:
        stmt = stmt.where(Environment.tenant_id == tenant_id)
    stmt = stmt.limit(limit).offset(offset)
    return list(db.execute(stmt).scalars())


def create_environment(
    db: Session,
    req: EnvironmentCreateRequest,
    *,
    actor: str,
    source_ip: str | None,
    idempotency_key: str,
    commit: bool = True,
) -> tuple[Environment, ProvisioningOperation]:
    _require_tenant(db, req.tenant_id)
    runtime_settings = get_settings()
    if req.provisioning_mode == "byoc_lite":
        if not req.eks_cluster_arn:
            raise ValidationError("eks_cluster_arn is required for byoc_lite.")
        if not req.eks_namespace:
            raise ValidationError("eks_namespace is required for byoc_lite.")
    if req.provisioning_mode == "full":
        if not runtime_settings.enable_full_byoc_mode:
            raise ValidationError(
                "Full provisioning mode is disabled for this deployment. "
                "Set SPARKPILOT_ENABLE_FULL_BYOC_MODE=true only after full-BYOC infrastructure is deployed."
            )
        if not FULL_BYOC_TERRAFORM_ROOT.is_dir():
            raise ValidationError(
                "Full provisioning mode is unavailable for this deployment: "
                f"missing Terraform modules at '{FULL_BYOC_TERRAFORM_ROOT}'. "
                "Use provisioning_mode=byoc_lite or deploy full-BYOC Terraform modules."
            )

    env = Environment(
        tenant_id=req.tenant_id,
        region=req.region,
        provisioning_mode=req.provisioning_mode,
        instance_architecture=req.instance_architecture,
        customer_role_arn=req.customer_role_arn,
        assume_role_external_id=req.assume_role_external_id or None,
        eks_cluster_arn=req.eks_cluster_arn,
        eks_namespace=req.eks_namespace,
        warm_pool_enabled=req.warm_pool_enabled,
        lake_formation_enabled=req.lake_formation_enabled,
        lf_catalog_id=req.lf_catalog_id,
        lf_data_access_scope_json=req.lf_data_access_scope,
        security_configuration_id=req.security_configuration_id,
        max_concurrent_runs=req.quotas.max_concurrent_runs,
        max_vcpu=req.quotas.max_vcpu,
        max_run_seconds=req.quotas.max_run_seconds,
        status="provisioning",
    )
    db.add(env)
    db.flush()
    op = ProvisioningOperation(
        environment_id=env.id,
        idempotency_key=idempotency_key,
        state="queued",
        step="queued",
        message="Queued for provisioning.",
        logs_uri=f"s3://sparkpilot-ops/provisioning/{env.id}/{uuid.uuid4()}.log",
    )
    db.add(op)
    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action="environment.create",
        entity_type="environment",
        entity_id=env.id,
        tenant_id=env.tenant_id,
        details={
            "region": env.region,
            "provisioning_mode": env.provisioning_mode,
            "instance_architecture": env.instance_architecture,
            "eks_cluster_arn": env.eks_cluster_arn or "",
            "eks_namespace": env.eks_namespace or "",
            "warm_pool_enabled": env.warm_pool_enabled,
            "max_concurrent_runs": env.max_concurrent_runs,
            "max_vcpu": env.max_vcpu,
            "max_run_seconds": env.max_run_seconds,
        },
    )
    if commit:
        db.commit()
        db.refresh(env)
        db.refresh(op)
    else:
        db.flush()
    return env, op


def get_environment(db: Session, environment_id: str) -> Environment:
    return _require_environment(db, environment_id)


def get_environment_preflight(db: Session, environment_id: str, *, run_id: str | None = None) -> dict[str, Any]:
    env = _require_environment(db, environment_id)
    spark_conf: dict[str, str] | None = None
    if run_id:
        run = _require_run(db, run_id)
        if run.environment_id != environment_id:
            raise EntityNotFoundError("Run not found for this environment.")
        job = _require_job(db, run.job_id)
        spark_conf = {**(job.spark_conf_json or {}), **(run.spark_conf_overrides_json or {})}
    return _build_preflight(env, run_id=run_id, spark_conf=spark_conf, db=db)


def get_provisioning_operation(db: Session, operation_id: str) -> ProvisioningOperation:
    op = db.get(ProvisioningOperation, operation_id)
    if not op:
        raise EntityNotFoundError("Provisioning operation not found.")
    return op


def retry_environment_provisioning(
    db: Session,
    environment_id: str,
    *,
    actor: str,
    source_ip: str | None,
    idempotency_key: str,
    commit: bool = True,
) -> ProvisioningOperation:
    env = _require_environment(db, environment_id)
    if env.status == "deleted":
        raise ConflictError("Environment is deleted and cannot be retried.")
    active_operation_states = {
        "queued",
        "validating_bootstrap",
        "provisioning_network",
        "provisioning_eks",
        "provisioning_emr",
        "validating_runtime",
    }
    existing_active_operation = db.execute(
        select(ProvisioningOperation.id).where(
            ProvisioningOperation.environment_id == environment_id,
            ProvisioningOperation.state.in_(active_operation_states),
        )
    ).first()
    if existing_active_operation:
        raise ConflictError("An active provisioning operation already exists for this environment.")

    env.status = "provisioning"
    env.updated_at = _now()
    op = ProvisioningOperation(
        environment_id=env.id,
        idempotency_key=idempotency_key,
        state="queued",
        step="queued",
        message="Queued for provisioning retry.",
        logs_uri=f"s3://sparkpilot-ops/provisioning/{env.id}/{uuid.uuid4()}.log",
    )
    db.add(op)
    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action="environment.retry_provisioning",
        entity_type="environment",
        entity_id=env.id,
        tenant_id=env.tenant_id,
        details={"operation_id": op.id},
    )
    if commit:
        db.commit()
        db.refresh(op)
    else:
        db.flush()
    return op


def delete_environment(
    db: Session,
    environment_id: str,
    *,
    actor: str,
    source_ip: str | None,
    commit: bool = True,
) -> Environment:
    env = _require_environment(db, environment_id)
    if env.status == "deleted":
        return env

    active_run_states = {"queued", "dispatching", "accepted", "running"}
    active_run = db.execute(
        select(Run.id).where(
            Run.environment_id == environment_id,
            Run.state.in_(active_run_states),
        )
    ).first()
    if active_run:
        raise ConflictError(
            "Environment has active or in-flight runs. Cancel/wait for completion before delete."
        )

    active_operation_states = {
        "queued",
        "validating_bootstrap",
        "provisioning_network",
        "provisioning_eks",
        "provisioning_emr",
        "validating_runtime",
    }
    active_operation = db.execute(
        select(ProvisioningOperation.id).where(
            ProvisioningOperation.environment_id == environment_id,
            ProvisioningOperation.state.in_(active_operation_states),
        )
    ).first()
    if active_operation:
        raise ConflictError("Environment has an active provisioning operation. Retry later.")

    env.status = "deleted"
    env.updated_at = _now()
    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action="environment.delete",
        entity_type="environment",
        entity_id=env.id,
        tenant_id=env.tenant_id,
        details={"status": env.status},
    )
    if commit:
        db.commit()
        db.refresh(env)
    else:
        db.flush()
    return env


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

def create_job(
    db: Session,
    req: JobCreateRequest,
    *,
    actor: str,
    source_ip: str | None,
    commit: bool = True,
) -> Job:
    env = _require_environment(db, req.environment_id)
    if env.status == "deleted":
        raise ConflictError("Environment is deleted.")
    job = Job(
        environment_id=req.environment_id,
        name=req.name,
        artifact_uri=req.artifact_uri,
        artifact_digest=req.artifact_digest,
        entrypoint=req.entrypoint,
        args_json=req.args,
        spark_conf_json=req.spark_conf,
        retry_max_attempts=req.retry_max_attempts,
        timeout_seconds=req.timeout_seconds,
    )
    db.add(job)
    db.flush()
    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action="job.create",
        entity_type="job",
        entity_id=job.id,
        tenant_id=env.tenant_id,
        details={"name": job.name, "artifact_uri": job.artifact_uri, "artifact_digest": job.artifact_digest},
    )
    if commit:
        db.commit()
        db.refresh(job)
    else:
        db.flush()
    return job


def list_jobs(
    db: Session,
    environment_id: str | None = None,
    *,
    limit: int = 200,
    offset: int = 0,
    environment_ids: set[str] | None = None,
) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc())
    if environment_id:
        stmt = stmt.where(Job.environment_id == environment_id)
    if environment_ids is not None:
        stmt = stmt.where(Job.environment_id.in_(environment_ids))
    stmt = stmt.limit(limit).offset(offset)
    return list(db.execute(stmt).scalars())


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def _resolve_run_configuration(
    db: Session,
    *,
    environment: Environment,
    req: RunCreateRequest,
) -> tuple[GoldenPath | None, dict[str, int], dict[str, str]]:
    if req.golden_path and req.spark_conf is not None:
        raise ValidationError("Provide either golden_path or spark_conf overrides, not both.")

    if not req.golden_path:
        requested = req.requested_resources.model_dump()
        spark_conf = req.spark_conf if req.spark_conf is not None else {}
        return None, requested, spark_conf

    selected_golden_path = _resolve_golden_path_for_run(db, environment, req.golden_path)
    requested = dict(selected_golden_path.requested_resources_json or {})
    run_spark_conf = dict(selected_golden_path.spark_conf_json or {})
    if selected_golden_path.instance_architecture == "arm64":
        run_spark_conf["spark.kubernetes.executor.node.selector.kubernetes.io/arch"] = "arm64"
        run_spark_conf["spark.kubernetes.driver.node.selector.kubernetes.io/arch"] = "arm64"
    elif selected_golden_path.instance_architecture == "x86_64":
        run_spark_conf["spark.kubernetes.executor.node.selector.kubernetes.io/arch"] = "amd64"
        run_spark_conf["spark.kubernetes.driver.node.selector.kubernetes.io/arch"] = "amd64"
    return selected_golden_path, requested, run_spark_conf


def _resolve_timeout_seconds(
    *,
    req: RunCreateRequest,
    job: Job,
    environment: Environment,
    selected_golden_path: GoldenPath | None,
) -> int:
    timeout_seconds = req.timeout_seconds or job.timeout_seconds
    if selected_golden_path:
        timeout_seconds = min(timeout_seconds, selected_golden_path.max_runtime_minutes * 60)
    if timeout_seconds > environment.max_run_seconds:
        raise ValidationError(
            f"Run timeout exceeds environment max_run_seconds ({environment.max_run_seconds})."
        )
    return timeout_seconds


def create_run(
    db: Session,
    *,
    job_id: str,
    req: RunCreateRequest,
    actor: str,
    source_ip: str | None,
    idempotency_key: str,
    commit: bool = True,
) -> Run:
    job = _require_job(db, job_id)
    env = lock_environment_for_quota(db, job.environment_id)
    if env.status != "ready":
        raise ConflictError("Environment is not ready.")

    selected_golden_path, requested, run_spark_conf = _resolve_run_configuration(
        db,
        environment=env,
        req=req,
    )

    policy_violations = _validate_custom_spark_conf_policy(run_spark_conf)
    if policy_violations:
        raise ValidationError(
            "Spark config violates environment policy. Blocked keys: "
            + ", ".join(policy_violations)
        )

    # Policy engine evaluation before quota checks (#39)
    from sparkpilot.policy_engine import evaluate_policies
    policy_results = evaluate_policies(
        db,
        env,
        timeout_seconds=req.timeout_seconds,
        requested_resources=requested,
        spark_conf=run_spark_conf,
        golden_path=req.golden_path,
        actor=actor,
        source_ip=source_ip,
    )
    hard_failures = [r for r in policy_results if not r["passed"] and r["enforcement"] == "hard"]
    if hard_failures:
        messages = "; ".join(f"[{f['policy_name']}] {f['message']}" for f in hard_failures)
        raise ValidationError(f"Policy violation(s): {messages}")

    enforce_quota_for_run(db, env, requested)
    timeout_seconds = _resolve_timeout_seconds(
        req=req,
        job=job,
        environment=env,
        selected_golden_path=selected_golden_path,
    )

    existing = db.execute(
        select(Run).where(and_(Run.job_id == job_id, Run.idempotency_key == idempotency_key))
    ).scalar_one_or_none()
    if existing:
        return existing

    run = Run(
        job_id=job.id,
        environment_id=env.id,
        state="queued",
        attempt=1,
        idempotency_key=idempotency_key,
        requested_resources_json=requested,
        args_overrides_json=req.args if req.args is not None else job.args_json,
        spark_conf_overrides_json=run_spark_conf,
        timeout_seconds=timeout_seconds,
        created_by_actor=actor,
    )
    db.add(run)
    db.flush()
    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action="run.create",
        entity_type="run",
        entity_id=run.id,
        tenant_id=env.tenant_id,
        details={
            "job_id": job.id,
            "requested_resources": requested,
            "golden_path": selected_golden_path.name if selected_golden_path else None,
        },
    )

    # Record LF permission context for audit trail (#38)
    if getattr(env, "lake_formation_enabled", False):
        try:
            from sparkpilot.services.lake_formation import get_lf_permission_context
            lf_context = get_lf_permission_context(
                env.region,
                runtime_settings.emr_execution_role_arn,
                catalog_id=getattr(env, "lf_catalog_id", None),
            )
            write_audit_event(
                db,
                actor=actor,
                source_ip=source_ip,
                action="run.lf_permission_context",
                entity_type="run",
                entity_id=run.id,
                tenant_id=env.tenant_id,
                details=lf_context,
            )
        except Exception:
            logger.warning("Failed to record LF permission context for run %s", run.id, exc_info=True)

    if commit:
        db.commit()
        db.refresh(run)
    else:
        db.flush()
    return run


def list_runs(
    db: Session,
    tenant_id: str | None,
    state: str | None,
    *,
    limit: int = 200,
    offset: int = 0,
    actor: str | None = None,
    environment_ids: set[str] | None = None,
) -> list[Run]:
    stmt = select(Run).join(Environment, Environment.id == Run.environment_id)
    if tenant_id:
        stmt = stmt.where(Environment.tenant_id == tenant_id)
    if state:
        stmt = stmt.where(Run.state == state)
    if actor:
        stmt = stmt.where(Run.created_by_actor == actor)
    if environment_ids is not None:
        stmt = stmt.where(Environment.id.in_(environment_ids))
    stmt = stmt.order_by(Run.created_at.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars())


def get_run(db: Session, run_id: str) -> Run:
    return _require_run(db, run_id)


def cancel_run(
    db: Session,
    run_id: str,
    *,
    actor: str,
    source_ip: str | None,
    commit: bool = True,
) -> Run:
    run = _require_run(db, run_id)
    env = _require_environment(db, run.environment_id)
    if run.state in TERMINAL_RUN_STATES:
        return run

    if run.state in {"queued", "dispatching"}:
        run.state = "cancelled"
        run.ended_at = _now()
    else:
        run.cancellation_requested = True

    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action="run.cancel.request",
        entity_type="run",
        entity_id=run.id,
        tenant_id=env.tenant_id,
    )
    if commit:
        db.commit()
        db.refresh(run)
    else:
        db.flush()
    return run


# ---------------------------------------------------------------------------
# Usage / logs
# ---------------------------------------------------------------------------

def get_usage(
    db: Session,
    tenant_id: str,
    from_ts: datetime,
    to_ts: datetime,
    *,
    limit: int = 200,
    offset: int = 0,
) -> list[UsageRecord]:
    _require_tenant(db, tenant_id)
    stmt = (
        select(UsageRecord)
        .where(UsageRecord.tenant_id == tenant_id)
        .where(UsageRecord.recorded_at >= from_ts)
        .where(UsageRecord.recorded_at <= to_ts)
        .order_by(UsageRecord.recorded_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars())


# For active or recently finished runs, restrict CloudWatch query to a rolling window
# to avoid paginating from the beginning of the log stream (which exhausts the page
# budget before reaching current output on long-running or slow-starting jobs).
_LOG_TAIL_WINDOW_SECONDS = 1800  # 30 minutes


def fetch_run_logs(db: Session, run_id: str, limit: int = 200) -> tuple[Run, list[str]]:
    run = _require_run(db, run_id)
    env = _require_environment(db, run.environment_id)

    start_time_ms: int | None = None
    if run.state in ACTIVE_RUN_STATES:
        # Active run: look back from now so pagination starts near the tail.
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        start_time_ms = now_ms - (_LOG_TAIL_WINDOW_SECONDS * 1000)
    elif run.ended_at:
        # Recently finished: anchor window at (ended_at - window) to capture
        # late-arriving CloudWatch events without scanning the whole stream.
        finished_ms = int(run.ended_at.timestamp() * 1000)
        start_time_ms = finished_ms - (_LOG_TAIL_WINDOW_SECONDS * 1000)

    proxy = CloudWatchLogsProxy()
    lines = proxy.fetch_lines(
        role_arn=env.customer_role_arn,
        region=env.region,
        log_group=run.log_group,
        log_stream_prefix=run.log_stream_prefix,
        limit=limit,
        start_time_ms=start_time_ms,
    )
    return run, lines
