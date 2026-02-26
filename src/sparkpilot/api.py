from datetime import UTC, datetime, timedelta
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from sparkpilot.config import get_settings
from sparkpilot.db import get_db, init_db
from sparkpilot.idempotency import with_idempotency
from sparkpilot.schemas import (
    EnvironmentCreateRequest,
    EnvironmentResponse,
    JobCreateRequest,
    JobResponse,
    LogsResponse,
    ProvisioningOperationResponse,
    RunCreateRequest,
    RunResponse,
    TenantCreateRequest,
    TenantResponse,
    UsageItem,
    UsageResponse,
)
from sparkpilot.services import (
    cancel_run,
    create_environment,
    create_job,
    create_run,
    create_tenant,
    fetch_run_logs,
    get_environment,
    get_provisioning_operation,
    get_run,
    get_usage,
    list_environments,
    list_runs,
    model_to_dict,
)


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="SparkPilot API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _actor_and_ip(request: Request) -> tuple[str, str | None]:
    actor = request.headers.get("X-Actor", "anonymous")
    source_ip = request.client.host if request.client else None
    return actor, source_ip


def _require_idempotency_key(key: str | None) -> str:
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required.",
        )
    return key


def _tenant_response(payload: dict[str, Any]) -> TenantResponse:
    return TenantResponse(**payload)


def _environment_response(payload: dict[str, Any]) -> EnvironmentResponse:
    return EnvironmentResponse(**payload)


def _operation_response(payload: dict[str, Any]) -> ProvisioningOperationResponse:
    return ProvisioningOperationResponse(**payload)


def _job_response(payload: dict[str, Any]) -> JobResponse:
    converted = {
        "id": payload["id"],
        "environment_id": payload["environment_id"],
        "name": payload["name"],
        "artifact_uri": payload["artifact_uri"],
        "artifact_digest": payload["artifact_digest"],
        "entrypoint": payload["entrypoint"],
        "args": payload["args_json"],
        "spark_conf": payload["spark_conf_json"],
        "retry_max_attempts": payload["retry_max_attempts"],
        "timeout_seconds": payload["timeout_seconds"],
        "created_at": payload["created_at"],
        "updated_at": payload["updated_at"],
    }
    return JobResponse(**converted)


def _run_response(payload: dict[str, Any]) -> RunResponse:
    converted = {
        "id": payload["id"],
        "job_id": payload["job_id"],
        "environment_id": payload["environment_id"],
        "state": payload["state"],
        "attempt": payload["attempt"],
        "requested_resources": payload["requested_resources_json"],
        "args": payload["args_overrides_json"],
        "spark_conf": payload["spark_conf_overrides_json"],
        "timeout_seconds": payload["timeout_seconds"],
        "emr_job_run_id": payload["emr_job_run_id"],
        "cancellation_requested": payload["cancellation_requested"],
        "log_group": payload["log_group"],
        "log_stream_prefix": payload["log_stream_prefix"],
        "driver_log_uri": payload["driver_log_uri"],
        "spark_ui_uri": payload["spark_ui_uri"],
        "error_message": payload["error_message"],
        "started_at": payload["started_at"],
        "ended_at": payload["ended_at"],
        "created_at": payload["created_at"],
        "updated_at": payload["updated_at"],
    }
    return RunResponse(**converted)


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def post_tenant(
    req: TenantCreateRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TenantResponse:
    key = _require_idempotency_key(idempotency_key)
    actor, source_ip = _actor_and_ip(request)

    result = with_idempotency(
        db,
        scope="POST:/v1/tenants",
        key=key,
        payload=req.model_dump(),
        execute=lambda: _create_tenant_result(db, req, actor, source_ip),
    )
    response.status_code = result.status_code
    if result.replayed:
        response.headers["X-Idempotent-Replay"] = "true"
    return _tenant_response(result.body)


@app.get("/v1/environments", response_model=list[EnvironmentResponse])
def get_environments(
    tenant_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[EnvironmentResponse]:
    return [_environment_response(model_to_dict(env)) for env in list_environments(db, tenant_id)]


@app.post(
    "/v1/environments",
    response_model=ProvisioningOperationResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_environment(
    req: EnvironmentCreateRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ProvisioningOperationResponse:
    key = _require_idempotency_key(idempotency_key)
    actor, source_ip = _actor_and_ip(request)

    def _create() -> tuple[int, dict[str, Any], str | None, str | None]:
        _, op = create_environment(db, req, actor=actor, source_ip=source_ip, idempotency_key=key)
        return status.HTTP_201_CREATED, model_to_dict(op), "provisioning_operation", op.id

    result = with_idempotency(
        db,
        scope="POST:/v1/environments",
        key=key,
        payload=req.model_dump(),
        execute=_create,
    )
    response.status_code = result.status_code
    if result.replayed:
        response.headers["X-Idempotent-Replay"] = "true"
    return _operation_response(result.body)


@app.get("/v1/environments/{environment_id}", response_model=EnvironmentResponse)
def get_environment_by_id(environment_id: str, db: Session = Depends(get_db)) -> EnvironmentResponse:
    return _environment_response(model_to_dict(get_environment(db, environment_id)))


@app.get("/v1/provisioning-operations/{operation_id}", response_model=ProvisioningOperationResponse)
def get_provisioning_operation_by_id(operation_id: str, db: Session = Depends(get_db)) -> ProvisioningOperationResponse:
    return _operation_response(model_to_dict(get_provisioning_operation(db, operation_id)))


@app.post("/v1/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def post_job(
    req: JobCreateRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JobResponse:
    key = _require_idempotency_key(idempotency_key)
    actor, source_ip = _actor_and_ip(request)

    result = with_idempotency(
        db,
        scope="POST:/v1/jobs",
        key=key,
        payload=req.model_dump(),
        execute=lambda: _create_job_result(db, req, actor, source_ip),
    )
    response.status_code = result.status_code
    if result.replayed:
        response.headers["X-Idempotent-Replay"] = "true"
    return _job_response(result.body)


@app.get("/v1/runs", response_model=list[RunResponse])
def get_runs(
    tenant_id: str | None = Query(default=None),
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[RunResponse]:
    return [_run_response(model_to_dict(run)) for run in list_runs(db, tenant_id, state)]


@app.post("/v1/jobs/{job_id}/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
def post_run(
    job_id: str,
    req: RunCreateRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RunResponse:
    key = _require_idempotency_key(idempotency_key)
    actor, source_ip = _actor_and_ip(request)

    result = with_idempotency(
        db,
        scope=f"POST:/v1/jobs/{job_id}/runs",
        key=key,
        payload=req.model_dump(),
        execute=lambda: _create_run_result(db, job_id, req, actor, source_ip, key),
    )
    response.status_code = result.status_code
    if result.replayed:
        response.headers["X-Idempotent-Replay"] = "true"
    return _run_response(result.body)


@app.get("/v1/runs/{run_id}", response_model=RunResponse)
def get_run_by_id(run_id: str, db: Session = Depends(get_db)) -> RunResponse:
    return _run_response(model_to_dict(get_run(db, run_id)))


@app.post("/v1/runs/{run_id}/cancel", response_model=RunResponse)
def post_cancel_run(
    run_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RunResponse:
    key = _require_idempotency_key(idempotency_key)
    actor, source_ip = _actor_and_ip(request)
    result = with_idempotency(
        db,
        scope=f"POST:/v1/runs/{run_id}/cancel",
        key=key,
        payload={"run_id": run_id},
        execute=lambda: _cancel_run_result(db, run_id, actor, source_ip),
    )
    response.status_code = result.status_code
    if result.replayed:
        response.headers["X-Idempotent-Replay"] = "true"
    return _run_response(result.body)


@app.get("/v1/runs/{run_id}/logs", response_model=LogsResponse)
def get_run_logs(
    run_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> LogsResponse:
    run, lines = fetch_run_logs(db, run_id, limit=limit)
    return LogsResponse(
        run_id=run.id,
        log_group=run.log_group,
        log_stream_prefix=run.log_stream_prefix,
        lines=lines,
    )


@app.get("/v1/usage", response_model=UsageResponse)
def get_usage_for_tenant(
    tenant_id: str,
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> UsageResponse:
    now = datetime.now(UTC)
    effective_to = to_ts or now
    effective_from = from_ts or (effective_to - timedelta(days=30))
    items = get_usage(db, tenant_id, effective_from, effective_to)
    return UsageResponse(
        tenant_id=tenant_id,
        from_ts=effective_from,
        to_ts=effective_to,
        items=[
            UsageItem(
                run_id=item.run_id,
                vcpu_seconds=item.vcpu_seconds,
                memory_gb_seconds=item.memory_gb_seconds,
                estimated_cost_usd_micros=item.estimated_cost_usd_micros,
                recorded_at=item.recorded_at,
            )
            for item in items
        ],
    )


def _create_tenant_result(
    db: Session,
    req: TenantCreateRequest,
    actor: str,
    source_ip: str | None,
) -> tuple[int, dict[str, Any], str | None, str | None]:
    tenant = create_tenant(db, req, actor, source_ip)
    return status.HTTP_201_CREATED, model_to_dict(tenant), "tenant", tenant.id


def _create_job_result(
    db: Session,
    req: JobCreateRequest,
    actor: str,
    source_ip: str | None,
) -> tuple[int, dict[str, Any], str | None, str | None]:
    job = create_job(db, req, actor=actor, source_ip=source_ip)
    return status.HTTP_201_CREATED, model_to_dict(job), "job", job.id


def _create_run_result(
    db: Session,
    job_id: str,
    req: RunCreateRequest,
    actor: str,
    source_ip: str | None,
    key: str,
) -> tuple[int, dict[str, Any], str | None, str | None]:
    run = create_run(
        db,
        job_id=job_id,
        req=req,
        actor=actor,
        source_ip=source_ip,
        idempotency_key=key,
    )
    return status.HTTP_201_CREATED, model_to_dict(run), "run", run.id


def _cancel_run_result(
    db: Session,
    run_id: str,
    actor: str,
    source_ip: str | None,
) -> tuple[int, dict[str, Any], str | None, str | None]:
    run = cancel_run(db, run_id, actor=actor, source_ip=source_ip)
    return status.HTTP_200_OK, model_to_dict(run), "run", run.id
