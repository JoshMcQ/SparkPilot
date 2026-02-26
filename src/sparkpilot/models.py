import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from sparkpilot.db import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    cloud: Mapped[str] = mapped_column(String(32), default="aws", nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    engine: Mapped[str] = mapped_column(String(64), default="emr_on_eks", nullable=False)
    provisioning_mode: Mapped[str] = mapped_column(String(32), default="full", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="provisioning", nullable=False)
    customer_role_arn: Mapped[str] = mapped_column(String(1024), nullable=False)
    eks_cluster_arn: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    eks_namespace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emr_virtual_cluster_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warm_pool_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_concurrent_runs: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_vcpu: Mapped[int] = mapped_column(Integer, default=256, nullable=False)
    max_run_seconds: Mapped[int] = mapped_column(Integer, default=7200, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class ProvisioningOperation(Base):
    __tablename__ = "provisioning_operations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    environment_id: Mapped[str] = mapped_column(String(36), ForeignKey("environments.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(64), default="queued", nullable=False)
    step: Mapped[str] = mapped_column(String(64), default="queued", nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    environment_id: Mapped[str] = mapped_column(String(36), ForeignKey("environments.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    artifact_digest: Mapped[str] = mapped_column(String(255), nullable=False)
    entrypoint: Mapped[str] = mapped_column(String(1024), nullable=False)
    args_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    spark_conf_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    retry_max_attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=7200, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class Run(Base):
    __tablename__ = "runs"

    __table_args__ = (UniqueConstraint("job_id", "idempotency_key", name="uq_runs_job_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    environment_id: Mapped[str] = mapped_column(String(36), ForeignKey("environments.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_resources_json: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    args_overrides_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    spark_conf_overrides_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=7200, nullable=False)
    emr_job_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    log_group: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    log_stream_prefix: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    driver_log_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    spark_ui_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), nullable=False, unique=True)
    vcpu_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_gb_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd_micros: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    source_ip: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    details_json: Mapped[dict[str, str] | dict[str, int] | dict[str, object]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    aws_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cloudtrail_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    scope: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
