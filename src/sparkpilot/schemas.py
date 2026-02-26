from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


EnvironmentState = Literal["provisioning", "ready", "degraded", "upgrading", "deleting", "deleted", "failed"]
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


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=255)


class TenantResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class EnvironmentQuotas(BaseModel):
    max_concurrent_runs: int = Field(default=10, ge=1, le=1000)
    max_vcpu: int = Field(default=256, ge=1, le=20000)
    max_run_seconds: int = Field(default=7200, ge=60, le=172800)


class EnvironmentCreateRequest(BaseModel):
    tenant_id: str
    provisioning_mode: Literal["full", "byoc_lite"] = "full"
    region: str = Field(default="us-east-1")
    customer_role_arn: str
    eks_cluster_arn: str | None = None
    eks_namespace: str | None = Field(default=None, max_length=255)
    warm_pool_enabled: bool = False
    quotas: EnvironmentQuotas = Field(default_factory=EnvironmentQuotas)


class EnvironmentResponse(BaseModel):
    id: str
    tenant_id: str
    cloud: str
    region: str
    engine: str
    provisioning_mode: Literal["full", "byoc_lite"]
    status: EnvironmentState
    customer_role_arn: str
    eks_cluster_arn: str | None
    eks_namespace: str | None
    emr_virtual_cluster_id: str | None
    warm_pool_enabled: bool
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
    requested_resources: RequestedResources = Field(default_factory=RequestedResources)
    timeout_seconds: int | None = Field(default=None, ge=60, le=172800)


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
    error_message: str | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LogsResponse(BaseModel):
    run_id: str
    log_group: str | None
    log_stream_prefix: str | None
    lines: list[str]


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
