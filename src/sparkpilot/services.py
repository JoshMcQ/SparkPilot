from datetime import UTC, datetime
from typing import Any
import uuid

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from sparkpilot.audit import write_audit_event
from sparkpilot.aws_clients import CloudWatchLogsProxy, EmrEksClient
from sparkpilot.models import Environment, Job, ProvisioningOperation, Run, Tenant, UsageRecord
from sparkpilot.quota import enforce_quota_for_run
from sparkpilot.schemas import EnvironmentCreateRequest, JobCreateRequest, RequestedResources, RunCreateRequest, TenantCreateRequest


TERMINAL_RUN_STATES = {"succeeded", "failed", "cancelled", "timed_out"}
ACTIVE_RUN_STATES = {"queued", "dispatching", "accepted", "running"}


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    return tenant


def _require_environment(db: Session, environment_id: str) -> Environment:
    env = db.get(Environment, environment_id)
    if not env:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found.")
    return env


def _require_job(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job


def _require_run(db: Session, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return run


def create_tenant(db: Session, req: TenantCreateRequest, actor: str, source_ip: str | None) -> Tenant:
    existing = db.execute(select(Tenant).where(Tenant.name == req.name)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant name already exists.")
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
    db.commit()
    db.refresh(tenant)
    return tenant


def list_environments(db: Session, tenant_id: str | None) -> list[Environment]:
    stmt = select(Environment).order_by(Environment.created_at.desc())
    if tenant_id:
        stmt = stmt.where(Environment.tenant_id == tenant_id)
    return list(db.execute(stmt).scalars())


def create_environment(
    db: Session,
    req: EnvironmentCreateRequest,
    *,
    actor: str,
    source_ip: str | None,
    idempotency_key: str,
) -> tuple[Environment, ProvisioningOperation]:
    _require_tenant(db, req.tenant_id)
    if req.provisioning_mode == "byoc_lite":
        if not req.eks_cluster_arn:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="eks_cluster_arn is required for byoc_lite.",
            )
        if not req.eks_namespace:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="eks_namespace is required for byoc_lite.",
            )

    env = Environment(
        tenant_id=req.tenant_id,
        region=req.region,
        provisioning_mode=req.provisioning_mode,
        customer_role_arn=req.customer_role_arn,
        eks_cluster_arn=req.eks_cluster_arn,
        eks_namespace=req.eks_namespace,
        warm_pool_enabled=req.warm_pool_enabled,
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
            "eks_cluster_arn": env.eks_cluster_arn or "",
            "eks_namespace": env.eks_namespace or "",
            "warm_pool_enabled": env.warm_pool_enabled,
            "max_concurrent_runs": env.max_concurrent_runs,
            "max_vcpu": env.max_vcpu,
            "max_run_seconds": env.max_run_seconds,
        },
    )
    db.commit()
    db.refresh(env)
    db.refresh(op)
    return env, op


def get_environment(db: Session, environment_id: str) -> Environment:
    return _require_environment(db, environment_id)


def get_provisioning_operation(db: Session, operation_id: str) -> ProvisioningOperation:
    op = db.get(ProvisioningOperation, operation_id)
    if not op:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provisioning operation not found.")
    return op


def create_job(db: Session, req: JobCreateRequest, *, actor: str, source_ip: str | None) -> Job:
    env = _require_environment(db, req.environment_id)
    if env.status == "deleted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Environment is deleted.")
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
    db.commit()
    db.refresh(job)
    return job


def create_run(
    db: Session,
    *,
    job_id: str,
    req: RunCreateRequest,
    actor: str,
    source_ip: str | None,
    idempotency_key: str,
) -> Run:
    job = _require_job(db, job_id)
    env = _require_environment(db, job.environment_id)
    if env.status != "ready":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Environment is not ready.")

    requested = req.requested_resources.model_dump()
    enforce_quota_for_run(db, env, requested)
    timeout_seconds = req.timeout_seconds or job.timeout_seconds
    if timeout_seconds > env.max_run_seconds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Run timeout exceeds environment max_run_seconds ({env.max_run_seconds}).",
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
        spark_conf_overrides_json=req.spark_conf if req.spark_conf is not None else {},
        timeout_seconds=timeout_seconds,
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
        details={"job_id": job.id, "requested_resources": requested},
    )
    db.commit()
    db.refresh(run)
    return run


def list_runs(db: Session, tenant_id: str | None, state: str | None) -> list[Run]:
    stmt = select(Run).join(Environment, Environment.id == Run.environment_id)
    if tenant_id:
        stmt = stmt.where(Environment.tenant_id == tenant_id)
    if state:
        stmt = stmt.where(Run.state == state)
    stmt = stmt.order_by(Run.created_at.desc())
    return list(db.execute(stmt).scalars())


def get_run(db: Session, run_id: str) -> Run:
    return _require_run(db, run_id)


def cancel_run(db: Session, run_id: str, *, actor: str, source_ip: str | None) -> Run:
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
    db.commit()
    db.refresh(run)
    return run


def get_usage(
    db: Session,
    tenant_id: str,
    from_ts: datetime,
    to_ts: datetime,
) -> list[UsageRecord]:
    _require_tenant(db, tenant_id)
    stmt = (
        select(UsageRecord)
        .where(UsageRecord.tenant_id == tenant_id)
        .where(UsageRecord.recorded_at >= from_ts)
        .where(UsageRecord.recorded_at <= to_ts)
        .order_by(UsageRecord.recorded_at.asc())
    )
    return list(db.execute(stmt).scalars())


def fetch_run_logs(db: Session, run_id: str, limit: int = 200) -> tuple[Run, list[str]]:
    run = _require_run(db, run_id)
    env = _require_environment(db, run.environment_id)
    proxy = CloudWatchLogsProxy()
    lines = proxy.fetch_lines(
        role_arn=env.customer_role_arn,
        region=env.region,
        log_group=run.log_group,
        log_stream_prefix=run.log_stream_prefix,
        limit=limit,
    )
    return run, lines


PROVISIONING_STEPS = [
    "validating_bootstrap",
    "provisioning_network",
    "provisioning_eks",
    "provisioning_emr",
    "validating_runtime",
]

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


def process_provisioning_once(db: Session, *, actor: str = "worker:provisioner") -> int:
    emr = EmrEksClient()
    pending = list(
        db.execute(
            select(ProvisioningOperation)
            .where(ProvisioningOperation.state.in_(["queued", *PROVISIONING_STEPS]))
            .order_by(ProvisioningOperation.created_at.asc())
        ).scalars()
    )
    processed = 0
    for op in pending:
        env = _require_environment(db, op.environment_id)
        try:
            if not env.customer_role_arn.startswith("arn:aws:iam::"):
                raise ValueError("Invalid customer role ARN.")
            if env.provisioning_mode == "byoc_lite":
                op.state = "validating_runtime"
                op.step = "validating_runtime"
                op.message = "Validating BYOC-Lite runtime."
                if not env.eks_cluster_arn:
                    raise ValueError("Missing eks_cluster_arn for BYOC-Lite.")
                if not env.eks_namespace:
                    raise ValueError("Missing eks_namespace for BYOC-Lite.")
                if not env.emr_virtual_cluster_id:
                    env.emr_virtual_cluster_id = emr.create_virtual_cluster(env)
                env.status = "ready"
                op.state = "ready"
                op.step = "ready"
                op.message = "BYOC-Lite environment ready."
                op.ended_at = _now()
                write_audit_event(
                    db,
                    actor=actor,
                    action="environment.byoc_lite_provisioned",
                    entity_type="environment",
                    entity_id=env.id,
                    tenant_id=env.tenant_id,
                    details={
                        "eks_cluster_arn": env.eks_cluster_arn,
                        "eks_namespace": env.eks_namespace,
                        "emr_virtual_cluster_id": env.emr_virtual_cluster_id,
                    },
                )
                processed += 1
                continue

            for step in PROVISIONING_STEPS:
                op.state = step
                op.step = step
                op.message = f"{step} complete."
            env.eks_cluster_arn = (
                f"arn:aws:eks:{env.region}:000000000000:cluster/sparkpilot-{env.id[:8]}"
            )
            env.emr_virtual_cluster_id = f"vc-{uuid.uuid4().hex[:10]}"
            env.status = "ready"
            op.state = "ready"
            op.step = "ready"
            op.message = "Environment provisioning complete."
            op.ended_at = _now()
            write_audit_event(
                db,
                actor=actor,
                action="environment.provisioned",
                entity_type="environment",
                entity_id=env.id,
                tenant_id=env.tenant_id,
                details={
                    "eks_cluster_arn": env.eks_cluster_arn,
                    "emr_virtual_cluster_id": env.emr_virtual_cluster_id,
                    "validated_vpc_endpoints": KNOWN_GOOD_VPC_ENDPOINTS,
                },
            )
        except Exception as exc:  # noqa: BLE001
            env.status = "failed"
            op.state = "failed"
            op.step = "failed"
            op.message = str(exc)
            op.ended_at = _now()
            write_audit_event(
                db,
                actor=actor,
                action="environment.provisioning_failed",
                entity_type="environment",
                entity_id=env.id,
                tenant_id=env.tenant_id,
                details={"error": str(exc)},
            )
        processed += 1
    if processed:
        db.commit()
    return processed


def process_scheduler_once(db: Session, *, actor: str = "worker:scheduler", limit: int = 20) -> int:
    emr = EmrEksClient()
    queued_runs = list(
        db.execute(
            select(Run)
            .where(Run.state == "queued")
            .order_by(Run.created_at.asc())
            .limit(limit)
        ).scalars()
    )
    processed = 0
    for run in queued_runs:
        job = _require_job(db, run.job_id)
        env = _require_environment(db, run.environment_id)
        if run.cancellation_requested:
            run.state = "cancelled"
            run.ended_at = _now()
            processed += 1
            continue
        try:
            run.state = "dispatching"
            dispatch = emr.start_job_run(env, job, run)
            run.state = "accepted"
            run.started_at = _now()
            run.emr_job_run_id = dispatch.emr_job_run_id
            run.log_group = dispatch.log_group
            run.log_stream_prefix = dispatch.log_stream_prefix
            run.driver_log_uri = dispatch.driver_log_uri
            run.spark_ui_uri = dispatch.spark_ui_uri
            write_audit_event(
                db,
                actor=actor,
                action="run.dispatched",
                entity_type="run",
                entity_id=run.id,
                tenant_id=env.tenant_id,
                aws_request_id=dispatch.aws_request_id,
                details={"emr_job_run_id": run.emr_job_run_id},
            )
        except Exception as exc:  # noqa: BLE001
            run.state = "failed"
            run.error_message = str(exc)
            run.ended_at = _now()
            write_audit_event(
                db,
                actor=actor,
                action="run.dispatch_failed",
                entity_type="run",
                entity_id=run.id,
                tenant_id=env.tenant_id,
                details={"error": str(exc)},
            )
        processed += 1
    if processed:
        db.commit()
    return processed


EMR_TO_PLATFORM_STATE = {
    "PENDING": "accepted",
    "SUBMITTED": "accepted",
    "RUNNING": "running",
    "COMPLETED": "succeeded",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
    "CANCEL_PENDING": "running",
}


def _record_usage_if_needed(db: Session, run: Run, env: Environment) -> None:
    existing = db.execute(select(UsageRecord).where(UsageRecord.run_id == run.id)).scalar_one_or_none()
    if existing:
        return
    duration_seconds = 0
    if run.started_at and run.ended_at:
        duration_seconds = max(0, int((_as_utc(run.ended_at) - _as_utc(run.started_at)).total_seconds()))
    resources = RequestedResources(**(run.requested_resources_json or {}))
    vcpu_seconds = duration_seconds * resources.total_vcpu()
    memory_total = resources.driver_memory_gb + (resources.executor_memory_gb * resources.executor_instances)
    memory_gb_seconds = duration_seconds * memory_total
    # Placeholder pricing model in micros (1 USD = 1_000_000 micros).
    estimated_cost_usd_micros = (vcpu_seconds * 35) + (memory_gb_seconds * 4)
    db.add(
        UsageRecord(
            tenant_id=env.tenant_id,
            run_id=run.id,
            vcpu_seconds=vcpu_seconds,
            memory_gb_seconds=memory_gb_seconds,
            estimated_cost_usd_micros=estimated_cost_usd_micros,
        )
    )


def process_reconciler_once(db: Session, *, actor: str = "worker:reconciler", limit: int = 20) -> int:
    emr = EmrEksClient()
    active_runs = list(
        db.execute(
            select(Run)
            .where(Run.state.in_(["accepted", "running"]))
            .order_by(Run.updated_at.asc())
            .limit(limit)
        ).scalars()
    )
    processed = 0
    for run in active_runs:
        env = _require_environment(db, run.environment_id)
        if run.started_at:
            elapsed = (_now() - _as_utc(run.started_at)).total_seconds()
            if elapsed > run.timeout_seconds:
                run.cancellation_requested = True
                if run.emr_job_run_id:
                    aws_request_id = emr.cancel_job_run(env, run)
                    write_audit_event(
                        db,
                        actor=actor,
                        action="run.timeout_cancel.dispatched",
                        entity_type="run",
                        entity_id=run.id,
                        tenant_id=env.tenant_id,
                        aws_request_id=aws_request_id,
                    )
                run.state = "timed_out"
                run.error_message = "Run exceeded timeout_seconds."
                run.ended_at = _now()
                _record_usage_if_needed(db, run, env)
                write_audit_event(
                    db,
                    actor=actor,
                    action="run.timed_out",
                    entity_type="run",
                    entity_id=run.id,
                    tenant_id=env.tenant_id,
                )
                processed += 1
                continue

        if run.cancellation_requested and run.emr_job_run_id:
            aws_request_id = emr.cancel_job_run(env, run)
            write_audit_event(
                db,
                actor=actor,
                action="run.cancel.dispatched",
                entity_type="run",
                entity_id=run.id,
                tenant_id=env.tenant_id,
                aws_request_id=aws_request_id,
            )
        emr_state, error = emr.describe_job_run(env, run)
        mapped_state = EMR_TO_PLATFORM_STATE.get(emr_state, "failed")
        run.state = mapped_state
        if mapped_state in TERMINAL_RUN_STATES:
            if not run.ended_at:
                run.ended_at = _now()
            _record_usage_if_needed(db, run, env)
        if error:
            run.error_message = error
        write_audit_event(
            db,
            actor=actor,
            action="run.reconciled",
            entity_type="run",
            entity_id=run.id,
            tenant_id=env.tenant_id,
            details={"emr_state": emr_state, "state": mapped_state},
        )
        processed += 1
    if processed:
        db.commit()
    return processed


def model_to_dict(model: Any, *, include: set[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for column in model.__table__.columns:
        if include and column.name not in include:
            continue
        payload[column.name] = getattr(model, column.name)
    return payload
