import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_teams_tenant_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (CheckConstraint("role IN ('admin','operator','user')", name="ck_user_identities_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    actor: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True)
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class TeamEnvironmentScope(Base):
    __tablename__ = "team_environment_scopes"
    __table_args__ = (UniqueConstraint("team_id", "environment_id", name="uq_team_environment_scope"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id"), nullable=False)
    environment_id: Mapped[str] = mapped_column(String(36), ForeignKey("environments.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    cloud: Mapped[str] = mapped_column(String(32), default="aws", nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    engine: Mapped[str] = mapped_column(String(64), default="emr_on_eks", nullable=False)
    provisioning_mode: Mapped[str] = mapped_column(String(32), default="full", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="provisioning", nullable=False)
    instance_architecture: Mapped[str] = mapped_column(String(16), default="mixed", nullable=False)
    customer_role_arn: Mapped[str] = mapped_column(String(1024), nullable=False)
    eks_cluster_arn: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    eks_namespace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emr_virtual_cluster_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emr_serverless_application_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emr_on_ec2_cluster_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warm_pool_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_concurrent_runs: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_vcpu: Mapped[int] = mapped_column(Integer, default=256, nullable=False)
    max_run_seconds: Mapped[int] = mapped_column(Integer, default=7200, nullable=False)
    spark_history_server_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    event_log_s3_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    yunikorn_queue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    yunikorn_queue_guaranteed_vcpu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yunikorn_queue_max_vcpu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    databricks_workspace_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    databricks_cluster_policy_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    databricks_instance_pool_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lake_formation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lf_catalog_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lf_data_access_scope_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    identity_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    security_configuration_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class ProvisioningOperation(Base):
    __tablename__ = "provisioning_operations"
    __table_args__ = (
        Index("ix_provisioning_ops_environment_id", "environment_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    environment_id: Mapped[str] = mapped_column(String(36), ForeignKey("environments.id"), nullable=False)
    environment: Mapped["Environment"] = relationship(lazy="select")
    state: Mapped[str] = mapped_column(String(64), default="queued", nullable=False)
    step: Mapped[str] = mapped_column(String(64), default="queued", nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    worker_claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    worker_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class GoldenPath(Base):
    __tablename__ = "golden_paths"

    __table_args__ = (
        UniqueConstraint("environment_id", "name", name="uq_golden_paths_env_name"),
        Index(
            "uq_golden_paths_global_name",
            "name",
            unique=True,
            sqlite_where=text("environment_id IS NULL"),
            postgresql_where=text("environment_id IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    environment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("environments.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    spark_conf_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    requested_resources_json: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    instance_architecture: Mapped[str] = mapped_column(String(32), default="mixed", nullable=False)
    capacity_type: Mapped[str] = mapped_column(String(32), default="spot", nullable=False)
    max_runtime_minutes: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    tags_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    recommended_instance_types_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    data_access_scope_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class Run(Base):
    __tablename__ = "runs"

    __table_args__ = (
        UniqueConstraint("job_id", "idempotency_key", name="uq_runs_job_idempotency"),
        Index("ix_runs_state", "state"),
        Index("ix_runs_environment_id_state", "environment_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    environment_id: Mapped[str] = mapped_column(String(36), ForeignKey("environments.id"), nullable=False)
    job: Mapped["Job"] = relationship(lazy="select")
    environment: Mapped["Environment"] = relationship(lazy="select")
    state: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_resources_json: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    args_overrides_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    spark_conf_overrides_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=7200, nullable=False)
    job_template_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("job_templates.id"), nullable=True)
    emr_job_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    backend_job_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    log_group: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    log_stream_prefix: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    driver_log_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    spark_ui_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_by_actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    worker_claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    worker_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class RunDiagnostic(Base):
    __tablename__ = "run_diagnostics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    remediation: Mapped[str] = mapped_column(Text, nullable=False)
    log_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_records_tenant_recorded", "tenant_id", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), nullable=False, unique=True)
    vcpu_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_gb_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd_micros: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class CostAllocation(Base):
    __tablename__ = "cost_allocations"
    __table_args__ = (Index("ix_cost_allocations_team_period", "team", "billing_period"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), nullable=False, unique=True)
    environment_id: Mapped[str] = mapped_column(String(36), ForeignKey("environments.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    team: Mapped[str] = mapped_column(String(255), nullable=False)
    cost_center: Mapped[str] = mapped_column(String(255), nullable=False)
    billing_period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    estimated_vcpu_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_memory_gb_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd_micros: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actual_cost_usd_micros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cur_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    spot_cost_usd_micros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ondemand_cost_usd_micros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spot_savings_usd_micros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class TeamBudget(Base):
    __tablename__ = "team_budgets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    team: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    monthly_budget_usd_micros: Mapped[int] = mapped_column(Integer, nullable=False)
    warn_threshold_pct: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    block_threshold_pct: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class EmrRelease(Base):
    __tablename__ = "emr_releases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    release_label: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), default="current", nullable=False)
    graviton_supported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lake_formation_supported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    upgrade_target: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="emr-containers", nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


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


class JobTemplate(Base):
    __tablename__ = "job_templates"
    __table_args__ = (UniqueConstraint("environment_id", "name", name="uq_job_templates_env_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    environment_id: Mapped[str] = mapped_column(String(36), ForeignKey("environments.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    emr_template_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_driver_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    configuration_overrides_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    tags_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)


class InteractiveEndpoint(Base):
    __tablename__ = "interactive_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    environment_id: Mapped[str] = mapped_column(String(36), ForeignKey("environments.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    emr_endpoint_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    execution_role_arn: Mapped[str] = mapped_column(String(1024), nullable=False)
    release_label: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="creating", nullable=False)
    idle_timeout_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    certificate_arn: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    endpoint_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_by_actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)


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


# ---------------------------------------------------------------------------
# Policy Engine (R13 #39)
# ---------------------------------------------------------------------------

POLICY_RULE_TYPES = {
    "max_runtime_seconds",
    "max_vcpu",
    "max_memory_gb",
    "required_tags",
    "allowed_golden_paths",
    "allowed_release_labels",
    "allowed_instance_types",
    "allowed_security_configurations",
}

POLICY_ENFORCEMENT_MODES = {"hard", "soft"}

POLICY_SCOPES = {"global", "tenant", "environment"}


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (
        Index("ix_policies_scope", "scope", "scope_id"),
        CheckConstraint(
            "scope IN ('global', 'tenant', 'environment')",
            name="ck_policies_scope",
        ),
        CheckConstraint(
            "enforcement IN ('hard', 'soft')",
            name="ck_policies_enforcement",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="global")
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    enforcement: Mapped[str] = mapped_column(String(16), default="hard", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )
