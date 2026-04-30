from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, Field


EnvironmentState = Literal[
    "provisioning", "ready", "degraded", "upgrading", "deleting", "deleted", "failed"
]
ProvisioningState = Literal[
    "queued",
    "validating_bootstrap",
    "provisioning_network",
    "provisioning_eks",
    "provisioning_emr",
    "validating_runtime",
    "ready",
    "failed",
]
RunState = Literal[
    "queued",
    "dispatching",
    "accepted",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "timed_out",
]
PreflightCheckStatus = Literal["pass", "warning", "fail"]
UserRole = Literal["admin", "operator", "user"]
COGNITO_PASSWORD_FEDERATION: Final[str] = "cognito_password"  # pragma: allowlist secret
FederationType = Literal[COGNITO_PASSWORD_FEDERATION, "saml", "oidc"]


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    federation_type: FederationType = COGNITO_PASSWORD_FEDERATION
    idp_metadata: dict | None = None


class TenantResponse(BaseModel):
    id: str
    name: str
    federation_type: FederationType
    idp_metadata: dict | None = Field(
        default=None, validation_alias="idp_metadata_json"
    )
    created_at: datetime
    updated_at: datetime


class InternalTenantCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    admin_email: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    federation_type: FederationType = COGNITO_PASSWORD_FEDERATION
    idp_metadata: dict | None = None


class InternalTenantCreateResponse(BaseModel):
    tenant_id: str
    user_id: str
    invite_email_sent_to: str
    invite_email_provider: Literal["resend"]
    invite_email_provider_message_id: str | None = None


class InternalTenantUserResponse(BaseModel):
    id: str
    tenant_id: str
    email: str
    role: Literal["admin", "member"]
    invited_at: datetime | None
    invite_consumed_at: datetime | None
    invite_expires_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InternalTenantListItemResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    federation_type: FederationType
    admin_email: str | None
    created_at: datetime
    last_login_at: datetime | None


class InternalTenantDetailResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    federation_type: FederationType
    idp_metadata: dict | None
    created_at: datetime
    updated_at: datetime
    users: list[InternalTenantUserResponse]


class AuthCallbackResponse(BaseModel):
    status: Literal["ok"]
    actor: str
    invite_applied: bool
    user_id: str | None = None
    tenant_id: str | None = None


class TeamCreateRequest(BaseModel):
    tenant_id: str
    name: str = Field(min_length=1, max_length=255)


class TeamResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    created_at: datetime
    updated_at: datetime


class UserIdentityCreateRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=255)
    role: UserRole
    tenant_id: str | None = None
    team_id: str | None = None
    active: bool = True


class UserIdentityResponse(BaseModel):
    id: str
    actor: str
    role: UserRole
    tenant_id: str | None
    team_id: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


class AuthMeResponse(BaseModel):
    """Authenticated user context returned by GET /v1/auth/me (#75)."""

    actor: str
    role: UserRole
    tenant_id: str | None
    team_id: str | None
    scoped_environment_ids: list[str]
    email: str | None
    is_internal_admin: bool


class BootstrapStatusResponse(BaseModel):
    """Bootstrap readiness for the current authenticated subject."""

    actor: str
    bootstrap_required: bool
    actor_has_identity: bool
    actor_is_admin: bool


class AwsByocLiteClusterDiscoveryItem(BaseModel):
    name: str
    arn: str
    status: str
    version: str | None = None
    oidc_issuer: str | None = None
    has_oidc: bool


class AwsByocLiteDiscoveryResponse(BaseModel):
    customer_role_arn: str
    region: str
    account_id: str | None = None
    recommended_cluster_arn: str | None = None
    namespace_suggestion: str | None = None
    clusters: list[AwsByocLiteClusterDiscoveryItem]


class TeamEnvironmentScopeResponse(BaseModel):
    id: str
    team_id: str
    environment_id: str
    created_at: datetime


class EnvironmentQuotas(BaseModel):
    max_concurrent_runs: int = Field(default=10, ge=1, le=1000)
    max_vcpu: int = Field(default=256, ge=1, le=20000)
    max_run_seconds: int = Field(default=7200, ge=60, le=172800)


class EnvironmentCreateRequest(BaseModel):
    tenant_id: str
    engine: Literal["emr_on_eks", "emr_serverless", "emr_on_ec2"] = "emr_on_eks"
    provisioning_mode: Literal["full", "byoc_lite"] = "full"
    region: str = Field(default="us-east-1")
    instance_architecture: Literal["x86_64", "arm64", "mixed"] = "mixed"
    customer_role_arn: str
    assume_role_external_id: str | None = Field(default=None, max_length=1024)
    eks_cluster_arn: str | None = None
    eks_namespace: str | None = Field(default=None, max_length=255)
    warm_pool_enabled: bool = False
    lake_formation_enabled: bool = False
    lf_catalog_id: str | None = None
    lf_data_access_scope: dict | None = None
    security_configuration_id: str | None = None
    quotas: EnvironmentQuotas = Field(default_factory=EnvironmentQuotas)


class EnvironmentResponse(BaseModel):
    id: str
    tenant_id: str
    cloud: str
    region: str
    engine: str
    provisioning_mode: Literal["full", "byoc_lite"]
    instance_architecture: Literal["x86_64", "arm64", "mixed"]
    status: EnvironmentState
    customer_role_arn: str
    assume_role_external_id: str | None = None
    eks_cluster_arn: str | None
    eks_namespace: str | None
    emr_virtual_cluster_id: str | None
    warm_pool_enabled: bool
    lake_formation_enabled: bool
    lf_catalog_id: str | None
    lf_data_access_scope: dict | None = Field(
        default=None, validation_alias="lf_data_access_scope_json"
    )
    identity_mode: str | None
    security_configuration_id: str | None
    max_concurrent_runs: int
    max_vcpu: int
    max_run_seconds: int
    created_at: datetime
    updated_at: datetime


class ProvisioningOperationResponse(BaseModel):
    id: str
    environment_id: str
    state: ProvisioningState
    step: str
    started_at: datetime
    ended_at: datetime | None
    message: str | None
    logs_uri: str | None
    created_at: datetime
    updated_at: datetime


class JobCreateRequest(BaseModel):
    environment_id: str
    name: str = Field(min_length=1, max_length=255)
    artifact_uri: str = Field(min_length=3, max_length=2048)
    artifact_digest: str = Field(min_length=6, max_length=255)
    entrypoint: str = Field(min_length=1, max_length=1024)
    args: list[str] = Field(default_factory=list)
    spark_conf: dict[str, str] = Field(default_factory=dict)
    retry_max_attempts: int = Field(default=1, ge=1, le=10)
    timeout_seconds: int = Field(default=7200, ge=60, le=172800)


class JobResponse(BaseModel):
    id: str
    environment_id: str
    name: str
    artifact_uri: str
    artifact_digest: str
    entrypoint: str
    args: list[str]
    spark_conf: dict[str, str]
    retry_max_attempts: int
    timeout_seconds: int
    created_at: datetime
    updated_at: datetime


class ResourceSpec(BaseModel):
    vcpu: int = Field(ge=1, le=64)
    memory_gb: int = Field(ge=1, le=512)


class GoldenPathCreate(BaseModel):
    environment_id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2000)
    spark_config: dict[str, str] = Field(default_factory=dict)
    driver_resources: ResourceSpec
    executor_resources: ResourceSpec
    executor_count: int = Field(ge=0, le=1000)
    instance_architecture: Literal["x86_64", "arm64", "mixed"] = "mixed"
    capacity_type: Literal["spot", "on_demand", "mixed"] = "spot"
    max_runtime_minutes: int = Field(default=120, ge=1, le=10080)
    tags: dict[str, str] = Field(default_factory=dict)
    recommended_instance_types: list[str] = Field(default_factory=list)
    data_access_scope: dict | None = None


class GoldenPathResponse(BaseModel):
    id: str
    environment_id: str | None
    name: str
    description: str
    spark_config: dict[str, str]
    driver_resources: ResourceSpec
    executor_resources: ResourceSpec
    executor_count: int
    instance_architecture: Literal["x86_64", "arm64", "mixed"]
    capacity_type: Literal["spot", "on_demand", "mixed"]
    max_runtime_minutes: int
    tags: dict[str, str]
    recommended_instance_types: list[str]
    data_access_scope: dict | None
    created_at: datetime
    updated_at: datetime


class RequestedResources(BaseModel):
    driver_vcpu: int = Field(default=1, ge=1, le=64)
    driver_memory_gb: int = Field(default=4, ge=1, le=512)
    executor_vcpu: int = Field(default=2, ge=1, le=64)
    executor_memory_gb: int = Field(default=8, ge=1, le=512)
    executor_instances: int = Field(default=2, ge=0, le=1000)

    def total_vcpu(self) -> int:
        return self.driver_vcpu + (self.executor_vcpu * self.executor_instances)


class RunCreateRequest(BaseModel):
    args: list[str] | None = None
    spark_conf: dict[str, str] | None = None
    golden_path: str | None = None
    requested_resources: RequestedResources = Field(default_factory=RequestedResources)
    timeout_seconds: int | None = Field(default=None, ge=60, le=172800)


class RunPreflightResult(BaseModel):
    ready: bool
    summary: str | None = None
    generated_at: datetime | None = None
    checks: list[dict[str, object]] = Field(default_factory=list)


class RunResponse(BaseModel):
    id: str
    job_id: str
    environment_id: str
    state: RunState
    attempt: int
    requested_resources: RequestedResources
    args: list[str]
    spark_conf: dict[str, str]
    timeout_seconds: int
    emr_job_run_id: str | None
    cancellation_requested: bool
    log_group: str | None
    log_stream_prefix: str | None
    driver_log_uri: str | None
    spark_ui_uri: str | None
    spark_history_url: str | None = None
    preflight: RunPreflightResult | None = None
    created_by_actor: str | None
    error_message: str | None
    started_at: datetime | None
    last_heartbeat_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LogsResponse(BaseModel):
    run_id: str
    log_group: str | None
    log_stream_prefix: str | None
    lines: list[str]


class DiagnosticItem(BaseModel):
    id: str
    run_id: str
    category: str
    description: str
    remediation: str
    log_snippet: str | None
    created_at: datetime


class DiagnosticsResponse(BaseModel):
    run_id: str
    items: list[DiagnosticItem]


class PreflightCheck(BaseModel):
    code: str
    status: PreflightCheckStatus
    message: str
    remediation: str | None = None
    details: dict[str, str | int | bool] = Field(default_factory=dict)


class PreflightResponse(BaseModel):
    environment_id: str
    run_id: str | None = None
    ready: bool
    generated_at: datetime
    checks: list[PreflightCheck]


class UsageItem(BaseModel):
    run_id: str
    vcpu_seconds: int
    memory_gb_seconds: int
    estimated_cost_usd_micros: int
    recorded_at: datetime


class UsageResponse(BaseModel):
    tenant_id: str
    from_ts: datetime
    to_ts: datetime
    items: list[UsageItem]


class TeamBudgetCreateRequest(BaseModel):
    team: str = Field(min_length=1, max_length=255)
    monthly_budget_usd_micros: int = Field(ge=1)
    warn_threshold_pct: int = Field(default=80, ge=1, le=100)
    block_threshold_pct: int = Field(default=100, ge=1, le=100)


class TeamBudgetResponse(BaseModel):
    id: str
    team: str
    monthly_budget_usd_micros: int
    warn_threshold_pct: int
    block_threshold_pct: int
    created_at: datetime
    updated_at: datetime


class CostShowbackItem(BaseModel):
    run_id: str
    environment_id: str
    team: str
    cost_center: str
    estimated_cost_usd_micros: int
    actual_cost_usd_micros: int | None
    effective_cost_usd_micros: int
    billing_period: str
    cur_reconciled_at: datetime | None


class CostShowbackResponse(BaseModel):
    team: str
    period: str
    total_estimated_cost_usd_micros: int
    total_actual_cost_usd_micros: int
    total_effective_cost_usd_micros: int
    items: list[CostShowbackItem]


class EmrReleaseResponse(BaseModel):
    id: str
    release_label: str
    lifecycle_status: Literal["current", "deprecated", "end_of_life"]
    graviton_supported: bool
    lake_formation_supported: bool
    upgrade_target: str | None
    source: str
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime


class JobTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    job_driver: dict = Field(default_factory=dict)
    configuration_overrides: dict = Field(default_factory=dict)
    tags: dict[str, str] = Field(default_factory=dict)


class JobTemplateResponse(BaseModel):
    id: str
    environment_id: str
    tenant_id: str
    name: str
    description: str
    emr_template_id: str | None
    job_driver: dict
    configuration_overrides: dict
    tags: dict
    created_at: datetime
    updated_at: datetime


class InteractiveEndpointCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    execution_role_arn: str = Field(min_length=20, max_length=1024)
    release_label: str = Field(min_length=1, max_length=64)
    idle_timeout_minutes: int = Field(default=60, ge=1, le=10080)
    certificate_arn: str | None = None


class InteractiveEndpointResponse(BaseModel):
    id: str
    environment_id: str
    tenant_id: str
    name: str
    emr_endpoint_id: str | None
    execution_role_arn: str
    release_label: str
    status: str
    idle_timeout_minutes: int
    certificate_arn: str | None
    endpoint_url: str | None
    created_by_actor: str | None
    created_at: datetime
    updated_at: datetime


class QueueUtilizationResponse(BaseModel):
    environment_id: str
    yunikorn_queue: str | None
    active_run_count: int
    used_vcpu: int
    guaranteed_vcpu: int | None
    max_vcpu: int | None
    utilization_pct: float | None


# ---------------------------------------------------------------------------
# Policy Engine (R13 #39)
# ---------------------------------------------------------------------------

PolicyRuleType = Literal[
    "max_runtime_seconds",
    "max_vcpu",
    "max_memory_gb",
    "required_tags",
    "allowed_golden_paths",
    "allowed_release_labels",
    "allowed_instance_types",
    "allowed_security_configurations",
]

PolicyScope = Literal["global", "tenant", "environment"]
PolicyEnforcement = Literal["hard", "soft"]


class PolicyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scope: PolicyScope = "global"
    scope_id: str | None = None
    rule_type: PolicyRuleType
    config: dict = Field(default_factory=dict)
    enforcement: PolicyEnforcement = "hard"
    active: bool = True


class PolicyResponse(BaseModel):
    id: str
    name: str
    scope: str
    scope_id: str | None
    rule_type: str
    config: dict
    enforcement: str
    active: bool
    created_by_actor: str | None
    created_at: datetime
    updated_at: datetime


class PolicyEvaluationResult(BaseModel):
    policy_id: str
    policy_name: str
    rule_type: str
    enforcement: str
    passed: bool
    message: str


# ---------------------------------------------------------------------------
# Security Configuration schemas (#53)
# ---------------------------------------------------------------------------


class SecurityConfigurationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    virtual_cluster_id: str
    encryption_config: dict | None = None
    authorization_config: dict | None = None


class SecurityConfigurationResponse(BaseModel):
    id: str
    name: str
    virtual_cluster_id: str
    encryption_config: dict | None
    authorization_config: dict | None
    created_at: datetime | None
    remediation: str | None = None
