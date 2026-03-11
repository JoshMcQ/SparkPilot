from datetime import UTC, datetime, timedelta
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import lru_cache
import hmac
from typing import Any, TypeVar

import boto3
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from sparkpilot.config import get_settings, validate_runtime_settings
from sparkpilot.db import get_db, init_db
from sparkpilot.exceptions import SparkPilotError
from sparkpilot.idempotency import with_idempotency
from sparkpilot.models import Environment, Job, Run, TeamEnvironmentScope, UserIdentity
from sparkpilot.oidc import OIDCTokenVerifier, OIDCValidationError
from sparkpilot.schemas import (
    CostShowbackResponse,
    DiagnosticItem,
    DiagnosticsResponse,
    EmrReleaseResponse,
    EnvironmentCreateRequest,
    EnvironmentResponse,
    GoldenPathCreate,
    GoldenPathResponse,
    JobCreateRequest,
    JobResponse,
    LogsResponse,
    PreflightResponse,
    ProvisioningOperationResponse,
    RunCreateRequest,
    RunResponse,
    TeamCreateRequest,
    TeamEnvironmentScopeResponse,
    TenantCreateRequest,
    TenantResponse,
    TeamBudgetCreateRequest,
    TeamBudgetResponse,
    TeamResponse,
    UserIdentityCreateRequest,
    UserIdentityResponse,
    UsageItem,
    UsageResponse,
)
from sparkpilot.services import (
    add_team_environment_scope,
    remove_team_environment_scope,
    cancel_run,
    create_environment,
    create_golden_path,
    create_job,
    create_or_update_user_identity,
    create_or_update_team_budget,
    create_team,
    create_run,
    create_tenant,
    fetch_run_logs,
    get_cost_showback,
    get_environment,
    get_environment_preflight,
    get_golden_path,
    list_emr_releases,
    get_team_budget,
    get_provisioning_operation,
    get_run,
    get_usage,
    list_golden_paths,
    list_environments,
    list_jobs,
    list_run_diagnostics,
    list_team_environment_scopes,
    list_teams,
    list_user_identities,
    list_runs,
    model_to_dict,
    _golden_path_to_response_payload,
)


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_runtime_settings(get_settings())
    init_db()
    yield


_is_production = settings.environment.strip().lower() == "production"
app = FastAPI(
    title="SparkPilot API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)


@app.exception_handler(SparkPilotError)
async def _sparkpilot_error_handler(_request: Request, exc: SparkPilotError) -> Response:
    """Map domain exceptions to JSON HTTP responses."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Bootstrap-Secret"],
)


def _actor_and_ip(request: Request) -> tuple[str, str | None]:
    actor = _require_api_auth(request)
    source_ip = request.client.host if request.client else None
    return actor, source_ip


@lru_cache
def _oidc_verifier() -> OIDCTokenVerifier:
    runtime_settings = get_settings()
    return OIDCTokenVerifier(
        issuer=runtime_settings.oidc_issuer,
        audience=runtime_settings.oidc_audience,
        jwks_uri=runtime_settings.oidc_jwks_uri,
    )


def _require_api_auth(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        identity = _oidc_verifier().verify_access_token(token)
    except OIDCValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return identity.subject


@dataclass(frozen=True)
class AccessContext:
    actor: str
    role: str
    tenant_id: str | None
    team_id: str | None
    scoped_environment_ids: set[str]


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _has_any_identities(db: Session) -> bool:
    return db.execute(select(UserIdentity.id).limit(1)).first() is not None


def _resolve_access_context(db: Session, actor: str) -> AccessContext:
    identity = db.execute(
        select(UserIdentity).where(UserIdentity.actor == actor, UserIdentity.active.is_(True))
    ).scalar_one_or_none()
    if identity is None:
        raise _forbidden("Unknown or inactive actor.")
    if identity.role not in {"admin", "operator", "user"}:
        raise _forbidden("Actor role is invalid.")
    if identity.role in {"operator", "user"} and (not identity.tenant_id or not identity.team_id):
        raise _forbidden("Actor is missing tenant/team assignment.")
    scoped_environment_ids: set[str] = set()
    if identity.team_id:
        scoped_environment_ids = {
            row[0]
            for row in db.execute(
                select(TeamEnvironmentScope.environment_id).where(TeamEnvironmentScope.team_id == identity.team_id)
            ).all()
        }
    return AccessContext(
        actor=actor,
        role=identity.role,
        tenant_id=identity.tenant_id,
        team_id=identity.team_id,
        scoped_environment_ids=scoped_environment_ids,
    )


def _require_admin(access: AccessContext) -> None:
    if access.role != "admin":
        raise _forbidden("Admin role is required for this operation.")


def _require_role(access: AccessContext, allowed_roles: set[str], detail: str) -> None:
    if access.role not in allowed_roles:
        raise _forbidden(detail)


def _can_access_environment(access: AccessContext, env: Environment) -> bool:
    if access.role == "admin":
        return True
    if access.role not in {"operator", "user"}:
        return False
    if access.tenant_id != env.tenant_id:
        return False
    # Team-scoped roles require explicit environment scope membership.
    return env.id in access.scoped_environment_ids


def _require_environment_access(access: AccessContext, env: Environment) -> None:
    if not _can_access_environment(access, env):
        raise _forbidden("Actor is not authorized for this environment.")


def _can_access_run(access: AccessContext, run: Run, env: Environment) -> bool:
    if not _can_access_environment(access, env):
        return False
    if access.role == "user" and run.created_by_actor != access.actor:
        return False
    return True


def _require_run_access(access: AccessContext, run: Run, env: Environment) -> None:
    if not _can_access_run(access, run, env):
        raise _forbidden("Actor is not authorized for this run.")


def _require_idempotency_key(key: str | None) -> str:
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required.",
        )
    return key


def _require_bootstrap_secret(bootstrap_secret: str | None) -> None:
    expected_secret = get_settings().bootstrap_secret.strip()
    provided = (bootstrap_secret or "").strip()
    if not provided or not hmac.compare_digest(provided, expected_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bootstrap secret.",
        )


ResponseModelT = TypeVar("ResponseModelT")


def _response(payload: dict[str, Any], model: type[ResponseModelT]) -> ResponseModelT:
    return model(**payload)


def _job_response(payload: dict[str, Any]) -> JobResponse:
    return JobResponse(
        id=payload["id"],
        environment_id=payload["environment_id"],
        name=payload["name"],
        artifact_uri=payload["artifact_uri"],
        artifact_digest=payload["artifact_digest"],
        entrypoint=payload["entrypoint"],
        args=payload["args_json"],
        spark_conf=payload["spark_conf_json"],
        retry_max_attempts=payload["retry_max_attempts"],
        timeout_seconds=payload["timeout_seconds"],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
    )


def _run_response(payload: dict[str, Any]) -> RunResponse:
    return RunResponse(
        id=payload["id"],
        job_id=payload["job_id"],
        environment_id=payload["environment_id"],
        state=payload["state"],
        attempt=payload["attempt"],
        requested_resources=payload["requested_resources_json"],
        args=payload["args_overrides_json"],
        spark_conf=payload["spark_conf_overrides_json"],
        timeout_seconds=payload["timeout_seconds"],
        emr_job_run_id=payload["emr_job_run_id"],
        cancellation_requested=payload["cancellation_requested"],
        log_group=payload["log_group"],
        log_stream_prefix=payload["log_stream_prefix"],
        driver_log_uri=payload["driver_log_uri"],
        spark_ui_uri=payload["spark_ui_uri"],
        created_by_actor=payload.get("created_by_actor"),
        error_message=payload["error_message"],
        started_at=payload["started_at"],
        ended_at=payload["ended_at"],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
    )


@app.get("/healthz")
def healthcheck(
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    database_status: dict[str, Any]
    aws_status: dict[str, Any]

    try:
        db.execute(text("SELECT 1"))
        database_status = {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 - health endpoint must degrade gracefully
        database_status = {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}

    runtime_settings = get_settings()
    if runtime_settings.dry_run_mode:
        aws_status = {"status": "skipped", "detail": "dry_run_mode=true"}
    else:
        try:
            caller = boto3.client("sts", region_name=runtime_settings.aws_region).get_caller_identity()
            aws_status = {
                "status": "ok",
                "account_id": caller.get("Account"),
                "caller_arn": caller.get("Arn"),
            }
        except (ClientError, BotoCoreError, ValueError) as exc:
            aws_status = {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}

    is_healthy = database_status.get("status") == "ok" and aws_status.get("status") != "error"
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if is_healthy else "degraded",
        "checks": {
            "database": database_status,
            "aws": aws_status,
        },
    }


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
    access = _resolve_access_context(db, actor)
    _require_admin(access)

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
    return _response(result.body, TenantResponse)


@app.get("/v1/teams", response_model=list[TeamResponse])
def get_teams(
    request: Request,
    tenant_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[TeamResponse]:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    if access.role == "admin":
        rows = list_teams(db, tenant_id=tenant_id, limit=limit, offset=offset)
    else:
        if tenant_id and tenant_id != access.tenant_id:
            raise _forbidden("Actor cannot access a different tenant.")
        rows = list_teams(db, tenant_id=access.tenant_id, limit=limit, offset=offset)
    return [_response(model_to_dict(row), TeamResponse) for row in rows]


@app.post("/v1/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def post_team(
    req: TeamCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TeamResponse:
    actor, source_ip = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    row = create_team(db, req, actor=actor, source_ip=source_ip)
    return _response(model_to_dict(row), TeamResponse)


@app.get("/v1/user-identities", response_model=list[UserIdentityResponse])
def get_user_identities(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[UserIdentityResponse]:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    rows = list_user_identities(db, limit=limit, offset=offset)
    return [_response(model_to_dict(row), UserIdentityResponse) for row in rows]


@app.post("/v1/user-identities", response_model=UserIdentityResponse, status_code=status.HTTP_201_CREATED)
def post_user_identity(
    req: UserIdentityCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    bootstrap_secret: str | None = Header(default=None, alias="X-Bootstrap-Secret"),
) -> UserIdentityResponse:
    actor, source_ip = _actor_and_ip(request)
    if _has_any_identities(db):
        access = _resolve_access_context(db, actor)
        _require_admin(access)
    else:
        _require_bootstrap_secret(bootstrap_secret)
        if req.actor != actor:
            raise _forbidden("Bootstrap identity actor must match authenticated subject.")
        if req.role != "admin" or not req.active:
            raise _forbidden("First identity must be an active admin.")
        if req.tenant_id is not None or req.team_id is not None:
            raise _forbidden("First admin identity cannot include tenant/team assignments.")
    row = create_or_update_user_identity(db, req, actor=actor, source_ip=source_ip)
    return _response(model_to_dict(row), UserIdentityResponse)


@app.post(
    "/v1/teams/{team_id}/environments/{environment_id}",
    response_model=TeamEnvironmentScopeResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_team_environment_scope(
    team_id: str,
    environment_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> TeamEnvironmentScopeResponse:
    actor, source_ip = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    row = add_team_environment_scope(db, team_id, environment_id, actor=actor, source_ip=source_ip)
    return _response(model_to_dict(row), TeamEnvironmentScopeResponse)


@app.delete(
    "/v1/teams/{team_id}/environments/{environment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_team_environment_scope(
    team_id: str,
    environment_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    actor, source_ip = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    remove_team_environment_scope(db, team_id, environment_id, actor=actor, source_ip=source_ip)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/v1/teams/{team_id}/environments", response_model=list[TeamEnvironmentScopeResponse])
def get_team_environment_scope(
    team_id: str,
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[TeamEnvironmentScopeResponse]:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    rows = list_team_environment_scopes(db, team_id, limit=limit, offset=offset)
    return [_response(model_to_dict(row), TeamEnvironmentScopeResponse) for row in rows]


@app.get("/v1/environments", response_model=list[EnvironmentResponse])
def get_environments(
    request: Request,
    tenant_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[EnvironmentResponse]:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    if access.role != "admin":
        if tenant_id and tenant_id != access.tenant_id:
            raise _forbidden("Actor cannot access a different tenant.")
        tenant_id = access.tenant_id
    rows = [env for env in list_environments(db, tenant_id, limit=limit, offset=offset) if _can_access_environment(access, env)]
    return [_response(model_to_dict(env), EnvironmentResponse) for env in rows]


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
    access = _resolve_access_context(db, actor)
    _require_admin(access)

    def _create() -> tuple[int, dict[str, Any], str | None, str | None]:
        _, op = create_environment(
            db,
            req,
            actor=actor,
            source_ip=source_ip,
            idempotency_key=key,
            commit=False,
        )
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
    return _response(result.body, ProvisioningOperationResponse)


@app.get("/v1/environments/{environment_id}", response_model=EnvironmentResponse)
def get_environment_by_id(
    environment_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> EnvironmentResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    return _response(model_to_dict(env), EnvironmentResponse)


@app.get("/v1/environments/{environment_id}/preflight", response_model=PreflightResponse)
def get_environment_preflight_by_id(
    environment_id: str,
    request: Request,
    run_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PreflightResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    if run_id:
        run = get_run(db, run_id)
        _require_run_access(access, run, env)
    payload = get_environment_preflight(db, environment_id, run_id=run_id)
    return PreflightResponse(**payload)


@app.get("/v1/provisioning-operations/{operation_id}", response_model=ProvisioningOperationResponse)
def get_provisioning_operation_by_id(
    operation_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> ProvisioningOperationResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    op = get_provisioning_operation(db, operation_id)
    env = get_environment(db, op.environment_id)
    _require_environment_access(access, env)
    return _response(model_to_dict(op), ProvisioningOperationResponse)


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
    access = _resolve_access_context(db, actor)
    _require_role(access, {"admin", "operator"}, "Only admin/operator can create jobs.")
    env = get_environment(db, req.environment_id)
    _require_environment_access(access, env)

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


@app.get("/v1/jobs", response_model=list[JobResponse])
def get_jobs(
    request: Request,
    environment_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[JobResponse]:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_role(access, {"admin", "operator", "user"}, "Only admin/operator/user can list jobs.")
    if environment_id:
        env = get_environment(db, environment_id)
        _require_environment_access(access, env)
    env_ids_filter = None if access.role == "admin" else access.scoped_environment_ids
    rows = list_jobs(
        db,
        environment_id=environment_id,
        limit=limit,
        offset=offset,
        environment_ids=env_ids_filter,
    )
    return [_job_response(model_to_dict(row)) for row in rows]


@app.get("/v1/golden-paths", response_model=list[GoldenPathResponse])
def get_golden_paths(
    request: Request,
    environment_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[GoldenPathResponse]:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    if environment_id:
        env = get_environment(db, environment_id)
        _require_environment_access(access, env)
    allowed_env_ids = None if access.role == "admin" else access.scoped_environment_ids
    rows = list_golden_paths(
        db, environment_id=environment_id, limit=limit, offset=offset, allowed_environment_ids=allowed_env_ids
    )
    return [_response(_golden_path_to_response_payload(row), GoldenPathResponse) for row in rows]


@app.post("/v1/golden-paths", response_model=GoldenPathResponse, status_code=status.HTTP_201_CREATED)
def post_golden_path(
    req: GoldenPathCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> GoldenPathResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    if req.environment_id:
        env = get_environment(db, req.environment_id)
        _require_environment_access(access, env)
    row = create_golden_path(db, req)
    return _response(_golden_path_to_response_payload(row), GoldenPathResponse)


@app.get("/v1/golden-paths/{golden_path_id}", response_model=GoldenPathResponse)
def get_golden_path_by_id(
    golden_path_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> GoldenPathResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    row = get_golden_path(db, golden_path_id)
    if row.environment_id:
        env = get_environment(db, row.environment_id)
        _require_environment_access(access, env)
    return _response(_golden_path_to_response_payload(row), GoldenPathResponse)


@app.get("/v1/runs", response_model=list[RunResponse])
def get_runs(
    request: Request,
    tenant_id: str | None = Query(default=None),
    state: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[RunResponse]:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    if access.role != "admin":
        if tenant_id and tenant_id != access.tenant_id:
            raise _forbidden("Actor cannot access a different tenant.")
        tenant_id = access.tenant_id
    actor_filter = access.actor if access.role == "user" else None
    env_ids_filter = None if access.role == "admin" else access.scoped_environment_ids
    run_rows = list_runs(
        db, tenant_id, state, limit=limit, offset=offset,
        actor=actor_filter, environment_ids=env_ids_filter,
    )
    return [_run_response(model_to_dict(run)) for run in run_rows]


@app.get("/v1/emr-releases", response_model=list[EmrReleaseResponse])
def get_emr_releases(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[EmrReleaseResponse]:
    actor, _ = _actor_and_ip(request)
    _resolve_access_context(db, actor)
    rows = list_emr_releases(db, limit=limit, offset=offset)
    return [_response(model_to_dict(item), EmrReleaseResponse) for item in rows]


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
    access = _resolve_access_context(db, actor)
    _require_role(access, {"admin", "operator", "user"}, "Only admin/operator/user can submit runs.")
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    env = get_environment(db, job.environment_id)
    # Jobs are environment-scoped resources. Users can submit runs against any job
    # within environments they are explicitly authorized to access.
    _require_environment_access(access, env)

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
def get_run_by_id(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> RunResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    run = get_run(db, run_id)
    env = get_environment(db, run.environment_id)
    _require_run_access(access, run, env)
    return _run_response(model_to_dict(run))


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
    access = _resolve_access_context(db, actor)
    run = get_run(db, run_id)
    env = get_environment(db, run.environment_id)
    _require_run_access(access, run, env)
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
    request: Request,
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> LogsResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    run = get_run(db, run_id)
    env = get_environment(db, run.environment_id)
    _require_run_access(access, run, env)
    run, lines = fetch_run_logs(db, run_id, limit=limit)
    return LogsResponse(
        run_id=run.id,
        log_group=run.log_group,
        log_stream_prefix=run.log_stream_prefix,
        lines=lines,
    )


@app.get("/v1/runs/{run_id}/diagnostics", response_model=DiagnosticsResponse)
def get_run_diagnostics(
    run_id: str,
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> DiagnosticsResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    run = get_run(db, run_id)
    env = get_environment(db, run.environment_id)
    _require_run_access(access, run, env)
    items = list_run_diagnostics(db, run_id, limit=limit, offset=offset)
    return DiagnosticsResponse(
        run_id=run_id,
        items=[_response(model_to_dict(item), DiagnosticItem) for item in items],
    )


@app.get("/v1/usage", response_model=UsageResponse)
def get_usage_for_tenant(
    tenant_id: str,
    request: Request,
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> UsageResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_role(access, {"admin", "operator"}, "Only admin/operator can view usage.")
    if access.role != "admin" and tenant_id != access.tenant_id:
        raise _forbidden("Actor cannot access usage for a different tenant.")
    now = datetime.now(UTC)
    effective_to = to_ts or now
    effective_from = from_ts or (effective_to - timedelta(days=30))
    items = get_usage(db, tenant_id, effective_from, effective_to, limit=limit, offset=offset)
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


@app.post("/v1/team-budgets", response_model=TeamBudgetResponse, status_code=status.HTTP_201_CREATED)
def post_team_budget(
    req: TeamBudgetCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TeamBudgetResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    item = create_or_update_team_budget(db, req)
    return _response(model_to_dict(item), TeamBudgetResponse)


@app.get("/v1/team-budgets/{team}", response_model=TeamBudgetResponse)
def get_team_budget_by_team(
    team: str,
    request: Request,
    db: Session = Depends(get_db),
) -> TeamBudgetResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_role(access, {"admin", "operator"}, "Only admin/operator can view team budgets.")
    if access.role != "admin" and access.tenant_id != team:
        raise _forbidden("Operator can only view budget for assigned tenant key.")
    item = get_team_budget(db, team)
    return _response(model_to_dict(item), TeamBudgetResponse)


@app.get("/v1/costs", response_model=CostShowbackResponse)
def get_costs_showback(
    team: str,
    request: Request,
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CostShowbackResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_role(access, {"admin", "operator"}, "Only admin/operator can view showback costs.")
    if access.role != "admin" and access.tenant_id != team:
        raise _forbidden("Operator can only view showback for assigned tenant key.")
    return get_cost_showback(db, team=team, period=period, limit=limit, offset=offset)


def _create_tenant_result(
    db: Session,
    req: TenantCreateRequest,
    actor: str,
    source_ip: str | None,
) -> tuple[int, dict[str, Any], str | None, str | None]:
    tenant = create_tenant(db, req, actor, source_ip, commit=False)
    return status.HTTP_201_CREATED, model_to_dict(tenant), "tenant", tenant.id


def _create_job_result(
    db: Session,
    req: JobCreateRequest,
    actor: str,
    source_ip: str | None,
) -> tuple[int, dict[str, Any], str | None, str | None]:
    job = create_job(db, req, actor=actor, source_ip=source_ip, commit=False)
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
        commit=False,
    )
    return status.HTTP_201_CREATED, model_to_dict(run), "run", run.id


def _cancel_run_result(
    db: Session,
    run_id: str,
    actor: str,
    source_ip: str | None,
) -> tuple[int, dict[str, Any], str | None, str | None]:
    run = cancel_run(db, run_id, actor=actor, source_ip=source_ip, commit=False)
    return status.HTTP_200_OK, model_to_dict(run), "run", run.id


