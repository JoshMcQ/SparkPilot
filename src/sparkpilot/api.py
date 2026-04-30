from datetime import UTC, datetime, timedelta
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import lru_cache
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import uuid
from typing import Any, Literal, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import boto3
import httpx
import jwt
from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from botocore.exceptions import BotoCoreError, ClientError, ParamValidationError
from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from sparkpilot.aws_clients import parse_role_account_id_from_arn
from sparkpilot.audit import write_audit_event
from sparkpilot.config import (
    MIN_BOOTSTRAP_SECRET_LENGTH,
    get_settings,
    validate_runtime_settings,
)
from sparkpilot.db import get_db, init_db
from sparkpilot.exceptions import SparkPilotError
from sparkpilot.idempotency import with_idempotency
from sparkpilot.crm_webhook import emit_tenant_lifecycle_event
from sparkpilot.models import (
    AuditEvent,
    Environment,
    InteractiveEndpoint,
    Job,
    JobTemplate,
    MagicLinkToken,
    Run,
    Tenant,
    TeamEnvironmentScope,
    User,
    UserIdentity,
)
from sparkpilot.oidc import (
    OIDCIdentity,
    OIDCTokenVerifier,
    OIDCValidationError,
    OIDCKeyRotationError,
)
from sparkpilot.schemas import (
    AwsByocLiteDiscoveryResponse,
    AwsByocLiteClusterDiscoveryItem,
    AuthCallbackResponse,
    AuthMeResponse,
    BootstrapStatusResponse,
    CostShowbackResponse,
    DiagnosticItem,
    DiagnosticsResponse,
    EmrReleaseResponse,
    EnvironmentCreateRequest,
    EnvironmentResponse,
    GoldenPathCreate,
    GoldenPathResponse,
    InternalTenantCreateRequest,
    InternalTenantCreateResponse,
    InternalTenantDetailResponse,
    InternalTenantListItemResponse,
    InternalTenantUserResponse,
    InteractiveEndpointCreateRequest,
    InteractiveEndpointResponse,
    JobCreateRequest,
    JobResponse,
    JobTemplateCreateRequest,
    JobTemplateResponse,
    LogsResponse,
    PolicyCreateRequest,
    PolicyResponse,
    PreflightResponse,
    ProvisioningOperationResponse,
    QueueUtilizationResponse,
    RunCreateRequest,
    RunResponse,
    SecurityConfigurationCreateRequest,
    SecurityConfigurationResponse,
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
    apply_invite_identity_mapping,
    consume_invite_callback_state,
    consume_invite_token,
    remove_team_environment_scope,
    cancel_run,
    create_environment,
    delete_environment,
    create_golden_path,
    create_job,
    create_or_update_user_identity,
    create_or_update_team_budget,
    create_team,
    create_tenant_with_admin_invite,
    create_run,
    create_tenant,
    fetch_run_logs,
    get_cost_showback,
    get_environment,
    get_environment_preflight,
    get_golden_path,
    get_internal_tenant_detail,
    list_emr_releases,
    get_team_budget,
    get_provisioning_operation,
    get_run,
    get_usage,
    list_golden_paths,
    list_environments,
    list_jobs,
    list_internal_tenant_summaries,
    list_run_diagnostics,
    list_team_environment_scopes,
    list_teams,
    list_user_identities,
    list_runs,
    model_to_dict,
    regenerate_user_invite,
    retry_environment_provisioning,
    _golden_path_to_response_payload,
)


settings = get_settings()
logger = logging.getLogger(__name__)

_PRODUCTION_ENV_VALUES = {"production", "prod"}
_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "no", "n", "off", ""}
_INVITE_STATE_PREFIX = "sp_invite_v1"
_INVITE_STATE_TTL_SECONDS = 10 * 60
PoolSource = Literal["customer_pool", "internal_pool"]
InternalAuditAction = Literal[
    "tenant.create",
    "tenant.list_view",
    "tenant.detail_view",
    "tenant.invite_regenerate",
]


def _env_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value.strip()
    return default.strip()


def _parse_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return None


def _log_startup_check(name: str, passed: bool, detail: str) -> None:
    status = "PASS" if passed else "FAIL"
    level = logging.INFO if passed else logging.ERROR
    logger.log(level, "Production startup check [%s] %s: %s", status, name, detail)


def _fetch_jwks_json(jwks_uri: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
    response = httpx.get(jwks_uri, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("JWKS response must be a JSON object.")
    return payload


def _validate_production_startup() -> None:
    active_env = _env_value(
        "SPARKPILOT_ENV", "SPARKPILOT_ENVIRONMENT", default="dev"
    ).lower()
    if active_env not in _PRODUCTION_ENV_VALUES:
        return

    failures: list[str] = []

    def _record(name: str, passed: bool, detail: str) -> None:
        _log_startup_check(name, passed, detail)
        if not passed:
            failures.append(f"{name}: {detail}")

    auth_mode = _env_value("SPARKPILOT_AUTH_MODE", "AUTH_MODE", default="oidc").lower()
    _record(
        "auth_mode_oidc",
        auth_mode == "oidc",
        "SPARKPILOT_AUTH_MODE must be 'oidc'.",
    )

    customer_oidc_issuer = _env_value(
        "SPARKPILOT_CUSTOMER_OIDC_ISSUER",
        "CUSTOMER_OIDC_ISSUER",
        "SPARKPILOT_OIDC_ISSUER",
        "OIDC_ISSUER",
    )
    customer_oidc_audience = _env_value(
        "SPARKPILOT_CUSTOMER_OIDC_AUDIENCE",
        "CUSTOMER_OIDC_AUDIENCE",
        "SPARKPILOT_OIDC_AUDIENCE",
        "OIDC_AUDIENCE",
    )
    customer_oidc_jwks_uri = _env_value(
        "SPARKPILOT_CUSTOMER_OIDC_JWKS_URI",
        "CUSTOMER_OIDC_JWKS_URI",
        "SPARKPILOT_OIDC_JWKS_URI",
        "OIDC_JWKS_URI",
    )
    internal_oidc_issuer = _env_value(
        "SPARKPILOT_INTERNAL_OIDC_ISSUER",
        "INTERNAL_OIDC_ISSUER",
    )
    internal_oidc_audience = _env_value(
        "SPARKPILOT_INTERNAL_OIDC_AUDIENCE",
        "INTERNAL_OIDC_AUDIENCE",
    )
    internal_oidc_jwks_uri = _env_value(
        "SPARKPILOT_INTERNAL_OIDC_JWKS_URI",
        "INTERNAL_OIDC_JWKS_URI",
    )

    def _check_oidc_pool(
        pool_key: str, issuer: str, audience: str, jwks_uri: str
    ) -> None:
        _record(
            f"{pool_key}_oidc_issuer_present",
            bool(issuer),
            f"{pool_key} OIDC issuer must be set.",
        )
        _record(
            f"{pool_key}_oidc_audience_present",
            bool(audience),
            f"{pool_key} OIDC audience must be set.",
        )
        _record(
            f"{pool_key}_oidc_jwks_uri_present",
            bool(jwks_uri),
            f"{pool_key} OIDC JWKS URI must be set.",
        )
        jwks_check_ok = False
        jwks_detail = f"{pool_key} JWKS endpoint must be reachable and return JSON."
        if jwks_uri:
            try:
                _fetch_jwks_json(jwks_uri)
                jwks_check_ok = True
                jwks_detail = f"{pool_key} JWKS endpoint reachable and JSON parsed."
            except (httpx.HTTPError, ValueError) as exc:
                jwks_detail = f"JWKS check failed: {exc}"
        _record(
            f"{pool_key}_oidc_jwks_reachable_json",
            jwks_check_ok,
            jwks_detail,
        )

    _check_oidc_pool(
        "customer_pool",
        customer_oidc_issuer,
        customer_oidc_audience,
        customer_oidc_jwks_uri,
    )
    _check_oidc_pool(
        "internal_pool",
        internal_oidc_issuer,
        internal_oidc_audience,
        internal_oidc_jwks_uri,
    )

    resend_api_key = _env_value("SPARKPILOT_RESEND_API_KEY", "RESEND_API_KEY")
    invite_email_from = _env_value(
        "SPARKPILOT_INVITE_EMAIL_FROM",
        "INVITE_EMAIL_FROM",
    )
    _record(
        "resend_api_key_present",
        bool(resend_api_key),
        "SPARKPILOT_RESEND_API_KEY must be set for invite email delivery.",
    )
    _record(
        "invite_email_from_present",
        bool(invite_email_from),
        "SPARKPILOT_INVITE_EMAIL_FROM must be set for invite email delivery.",
    )

    bootstrap_secret = _env_value("SPARKPILOT_BOOTSTRAP_SECRET", "BOOTSTRAP_SECRET")
    _record(
        "bootstrap_secret_min_length",
        len(bootstrap_secret) >= MIN_BOOTSTRAP_SECRET_LENGTH,
        f"BOOTSTRAP_SECRET must be at least {MIN_BOOTSTRAP_SECRET_LENGTH} characters.",
    )

    cors_raw = _env_value(
        "SPARKPILOT_CORS_ORIGINS",
        default="http://localhost:3000,http://127.0.0.1:3000",
    )
    cors_entries = [entry.strip() for entry in cors_raw.split(",") if entry.strip()]
    local_origins = [
        entry
        for entry in cors_entries
        if "localhost" in entry.lower() or "127.0.0.1" in entry.lower()
    ]
    _record(
        "cors_no_localhost",
        not local_origins,
        "SPARKPILOT_CORS_ORIGINS must not contain localhost or 127.0.0.1.",
    )

    dry_run_raw = _env_value("SPARKPILOT_DRY_RUN_MODE", default="false")
    dry_run_value = _parse_bool(dry_run_raw)
    _record(
        "dry_run_disabled",
        dry_run_value is False,
        "SPARKPILOT_DRY_RUN_MODE must be false in production.",
    )

    full_byoc_raw = _env_value("SPARKPILOT_ENABLE_FULL_BYOC_MODE", default="false")
    full_byoc_value = _parse_bool(full_byoc_raw)
    _record(
        "full_byoc_disabled",
        full_byoc_value is False,
        "SPARKPILOT_ENABLE_FULL_BYOC_MODE must be false in production for this cut.",
    )

    if failures:
        raise RuntimeError(
            "Production startup validation failed: " + "; ".join(failures)
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    _validate_production_startup()
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


def _custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    components = schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["bearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "OIDC access token",
    }
    public_paths = {"/healthz", "/v1/invite/accept"}
    for path, operations in schema.get("paths", {}).items():
        if path in public_paths:
            continue
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if method.lower() not in {
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "head",
                "options",
                "trace",
            }:
                continue
            if isinstance(operation, dict):
                operation.setdefault("security", [{"bearerAuth": []}])
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _custom_openapi


@app.exception_handler(SparkPilotError)
async def _sparkpilot_error_handler(
    _request: Request, exc: SparkPilotError
) -> Response:
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
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "X-Bootstrap-Secret",
    ],
)


def _actor_and_ip(request: Request) -> tuple[str, str | None]:
    actor = _require_api_auth(request)
    source_ip = request.client.host if request.client else None
    return actor, source_ip


@lru_cache
def _oidc_verifiers() -> dict[PoolSource, OIDCTokenVerifier]:
    runtime_settings = get_settings()
    return {
        "customer_pool": OIDCTokenVerifier(
            issuer=runtime_settings.customer_oidc_issuer_effective,
            audience=runtime_settings.customer_oidc_audience_effective,
            jwks_uri=runtime_settings.customer_oidc_jwks_uri_effective,
        ),
        "internal_pool": OIDCTokenVerifier(
            issuer=runtime_settings.internal_oidc_issuer_effective,
            audience=runtime_settings.internal_oidc_audience_effective,
            jwks_uri=runtime_settings.internal_oidc_jwks_uri_effective,
        ),
    }


@lru_cache
def _oidc_verifier() -> OIDCTokenVerifier:
    # Backward-compatible alias used by existing tests and helpers.
    return _oidc_verifiers()["customer_pool"]


@dataclass(frozen=True)
class VerifiedOIDCIdentity:
    identity: OIDCIdentity
    pool_source: PoolSource


def _unverified_token_issuer(token: str) -> str | None:
    try:
        claims = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_exp": False,
            },
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
        )
    except jwt.PyJWTError:
        return None
    if not isinstance(claims, dict):
        return None
    issuer = str(claims.get("iss") or "").strip()
    return issuer or None


def _require_verified_identity(
    request: Request, *, allowed_pools: set[PoolSource] | None = None
) -> VerifiedOIDCIdentity:
    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    verifiers = _oidc_verifiers()
    expected_pools = allowed_pools or {"customer_pool"}
    unverified_issuer = _unverified_token_issuer(token)
    candidate_pools: list[PoolSource] = []
    if unverified_issuer:
        for pool_source, verifier in verifiers.items():
            if verifier.issuer == unverified_issuer:
                candidate_pools.append(pool_source)
    if not candidate_pools:
        candidate_pools = list(verifiers.keys())

    last_error: Exception | None = None
    for pool_source in candidate_pools:
        verifier = verifiers[pool_source]
        try:
            identity = verifier.verify_access_token(token)
        except (OIDCValidationError, OIDCKeyRotationError) as exc:
            last_error = exc
            continue
        if pool_source not in expected_pools:
            raise _forbidden("Token issuer is not permitted for this endpoint.")
        request.state.auth_pool_source = pool_source
        request.state.auth_email = _normalized_email_from_identity(identity)
        return VerifiedOIDCIdentity(identity=identity, pool_source=pool_source)

    if isinstance(last_error, OIDCKeyRotationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(last_error),
            headers={
                "WWW-Authenticate": "Bearer",
                "X-SparkPilot-Auth-Hint": "key-rotation",
            },
        ) from last_error
    if isinstance(last_error, OIDCValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(last_error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from last_error
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _require_api_identity(request: Request) -> OIDCIdentity:
    verified = _require_verified_identity(
        request, allowed_pools={"customer_pool"}
    )
    return verified.identity


def _require_api_auth(request: Request) -> str:
    return _require_api_identity(request).subject


@dataclass(frozen=True)
class AccessContext:
    actor: str
    role: str
    tenant_id: str | None
    team_id: str | None
    scoped_environment_ids: set[str]


@dataclass(frozen=True)
class InternalAdminContext:
    actor: str
    email: str


@dataclass(frozen=True)
class ApiIdentityContext:
    actor: str
    email: str | None
    pool_source: PoolSource
    is_internal_admin: bool


@dataclass(frozen=True)
class InviteStatePayload:
    tenant_id: str
    user_id: str
    token_id: str
    exp: int


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _bootstrap_flow_disabled_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "Bootstrap secret flow is disabled. "
            "Use internal admin invite provisioning instead."
        ),
    )


def _require_bootstrap_flow_enabled() -> None:
    if not get_settings().bootstrap_flow_enabled:
        raise _bootstrap_flow_disabled_error()


def _normalized_email_from_identity(identity: OIDCIdentity) -> str | None:
    raw = identity.claims.get("email")
    if raw is None:
        return None
    value = str(raw).strip().lower()
    return value or None


def _identity_context_for_request(
    request: Request, *, allowed_pools: set[PoolSource]
) -> ApiIdentityContext:
    verified = _require_verified_identity(request, allowed_pools=allowed_pools)
    identity = verified.identity
    email = _normalized_email_from_identity(identity)
    allowed = get_settings().internal_admin_email_set
    is_internal_admin = (
        verified.pool_source == "internal_pool"
        and email is not None
        and email in allowed
    )
    return ApiIdentityContext(
        actor=identity.subject,
        email=email,
        pool_source=verified.pool_source,
        is_internal_admin=is_internal_admin,
    )


def require_internal_admin(request: Request) -> InternalAdminContext:
    context = _identity_context_for_request(request, allowed_pools={"internal_pool"})
    if not context.email or not context.is_internal_admin:
        raise _forbidden("Internal admin access required")
    return InternalAdminContext(actor=context.actor, email=context.email)


def _request_id(request: Request) -> str:
    raw = request.headers.get("X-Request-Id", "").strip()
    if raw:
        return raw
    return str(uuid.uuid4())


def _write_internal_admin_audit_event(
    db: Session,
    *,
    request: Request,
    internal_admin: InternalAdminContext,
    action: InternalAuditAction,
    target_tenant_id: str | None,
    target_user_id: str | None,
) -> None:
    request_id = _request_id(request)
    source_ip = request.client.host if request.client else None
    write_audit_event(
        db,
        actor=internal_admin.email,
        action=action,
        entity_type="internal_tenant",
        entity_id=target_user_id or target_tenant_id or request_id,
        tenant_id=target_tenant_id,
        source_ip=source_ip,
        details={
            "actor_email": internal_admin.email,
            "actor_pool": "internal_pool",
            "target_tenant_id": target_tenant_id,
            "target_user_id": target_user_id,
            "request_id": request_id,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def _state_signing_key() -> bytes:
    return get_settings().invite_state_signing_secret.encode("utf-8")


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _urlsafe_b64decode(raw: str) -> bytes:
    pad = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(f"{raw}{pad}".encode("ascii"))


def _encode_invite_state(payload: InviteStatePayload) -> str:
    body = json.dumps(
        {
            "kind": "invite",
            "tenant_id": payload.tenant_id,
            "user_id": payload.user_id,
            "token_id": payload.token_id,
            "exp": payload.exp,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    body_enc = _urlsafe_b64encode(body)
    mac = hmac.new(
        _state_signing_key(), body_enc.encode("ascii"), hashlib.sha256
    ).digest()
    sig_enc = _urlsafe_b64encode(mac)
    return f"{_INVITE_STATE_PREFIX}.{body_enc}.{sig_enc}"


def _decode_invite_state(state: str | None) -> InviteStatePayload | None:
    if not state:
        return None
    prefix, dot, remainder = state.partition(".")
    if prefix != _INVITE_STATE_PREFIX or not dot:
        return None
    body_enc, dot2, sig_enc = remainder.partition(".")
    if not dot2 or not body_enc or not sig_enc:
        return None
    expected = hmac.new(
        _state_signing_key(),
        body_enc.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        provided = _urlsafe_b64decode(sig_enc)
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(provided, expected):
        return None
    try:
        payload = json.loads(_urlsafe_b64decode(body_enc).decode("utf-8"))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("kind") != "invite":
        return None
    tenant_id = str(payload.get("tenant_id") or "").strip()
    user_id = str(payload.get("user_id") or "").strip()
    token_id = str(payload.get("token_id") or "").strip()
    raw_exp = payload.get("exp")
    try:
        exp = int(raw_exp)
    except (TypeError, ValueError):
        return None
    now_ts = int(datetime.now(UTC).timestamp())
    if exp <= now_ts:
        return None
    if not tenant_id or not user_id or not token_id:
        return None
    return InviteStatePayload(
        tenant_id=tenant_id,
        user_id=user_id,
        token_id=token_id,
        exp=exp,
    )


def _append_query_params(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    existing = dict(parse_qsl(parts.query, keep_blank_values=True))
    existing.update(params)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(existing), parts.fragment)
    )


def _has_any_identities(db: Session) -> bool:
    return db.execute(select(UserIdentity.id).limit(1)).first() is not None


def _resolve_access_context(db: Session, actor: str) -> AccessContext:
    identity = db.execute(
        select(UserIdentity).where(
            UserIdentity.actor == actor, UserIdentity.active.is_(True)
        )
    ).scalar_one_or_none()
    if identity is None:
        raise _forbidden("Unknown or inactive actor.")
    if identity.role not in {"admin", "operator", "user"}:
        raise _forbidden("Actor role is invalid.")
    if identity.role in {"operator", "user"} and (
        not identity.tenant_id or not identity.team_id
    ):
        raise _forbidden("Actor is missing tenant/team assignment.")
    scoped_environment_ids: set[str] = set()
    if identity.team_id:
        scoped_environment_ids = {
            row[0]
            for row in db.execute(
                select(TeamEnvironmentScope.environment_id).where(
                    TeamEnvironmentScope.team_id == identity.team_id
                )
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


def _create_bootstrap_admin_identity(
    db: Session,
    *,
    actor: str,
    source_ip: str | None,
    bootstrap_secret: str | None,
    req: UserIdentityCreateRequest | None = None,
) -> UserIdentity:
    _require_bootstrap_secret(bootstrap_secret)
    bootstrap_req = req or UserIdentityCreateRequest(
        actor=actor, role="admin", active=True
    )
    if bootstrap_req.actor != actor:
        raise _forbidden("Bootstrap identity actor must match authenticated subject.")
    if bootstrap_req.role != "admin" or not bootstrap_req.active:
        raise _forbidden("First identity must be an active admin.")
    if bootstrap_req.tenant_id is not None or bootstrap_req.team_id is not None:
        raise _forbidden("First admin identity cannot include tenant/team assignments.")
    return create_or_update_user_identity(
        db, bootstrap_req, actor=actor, source_ip=source_ip
    )


_NAMESPACE_INVALID_CHARS = re.compile(r"[^a-z0-9-]+")
_NAMESPACE_MULTI_DASH = re.compile(r"-{2,}")


def _namespace_fragment(raw: str) -> str:
    value = _NAMESPACE_INVALID_CHARS.sub("-", raw.strip().lower())
    value = _NAMESPACE_MULTI_DASH.sub("-", value)
    value = value.strip("-")
    return value or "sparkpilot"


def _suggest_namespace(
    *, tenant_id: str | None, actor: str, cluster_name: str | None
) -> str:
    tenant_part = _namespace_fragment((tenant_id or actor).replace("_", "-"))[:20]
    cluster_part = _namespace_fragment(cluster_name or "cluster")[:20]
    namespace = f"sparkpilot-{tenant_part}-{cluster_part}".strip("-")
    if len(namespace) > 63:
        namespace = namespace[:63].strip("-")
    return namespace or "sparkpilot"


def _recommended_cluster(
    clusters: list[AwsByocLiteClusterDiscoveryItem],
) -> AwsByocLiteClusterDiscoveryItem | None:
    if not clusters:
        return None
    preferred = [
        item for item in clusters if item.status.upper() == "ACTIVE" and item.has_oidc
    ]
    if preferred:
        return preferred[0]
    active = [item for item in clusters if item.status.upper() == "ACTIVE"]
    if active:
        return active[0]
    return clusters[0]


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


def _latest_run_preflight_snapshot(db: Session, run_id: str) -> dict[str, Any] | None:
    event = db.execute(
        select(AuditEvent)
        .where(
            and_(
                AuditEvent.entity_type == "run",
                AuditEvent.entity_id == run_id,
                AuditEvent.action.in_(
                    [
                        "run.preflight_passed",
                        "run.preflight_failed",
                        "run.preflight_diagnostic",
                    ]
                ),
            )
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if event is None:
        return None

    details = event.details_json if isinstance(event.details_json, dict) else {}
    ready = details.get("ready")
    if not isinstance(ready, bool):
        ready = event.action != "run.preflight_failed"

    summary = details.get("summary")
    summary_text = str(summary) if summary is not None else None

    checks_raw = details.get("checks")
    checks: list[dict[str, object]] = []
    if isinstance(checks_raw, list):
        for item in checks_raw:
            if isinstance(item, dict):
                checks.append(item)

    return {
        "ready": ready,
        "summary": summary_text,
        "generated_at": event.created_at,
        "checks": checks,
    }


def _run_response(
    payload: dict[str, Any],
    env: Environment | None = None,
    *,
    preflight: dict[str, Any] | None = None,
) -> RunResponse:
    spark_ui_uri = payload["spark_ui_uri"]
    spark_history_url: str | None = None
    if spark_ui_uri:
        spark_history_url = spark_ui_uri
    elif (
        env is not None
        and env.spark_history_server_url
        and payload.get("emr_job_run_id")
    ):
        spark_history_url = f"{env.spark_history_server_url.rstrip('/')}/history/{payload['emr_job_run_id']}"
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
        spark_ui_uri=spark_ui_uri,
        spark_history_url=spark_history_url,
        preflight=preflight,
        created_by_actor=payload.get("created_by_actor"),
        error_message=payload["error_message"],
        started_at=payload["started_at"],
        last_heartbeat_at=payload["last_heartbeat_at"],
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
            caller = boto3.client(
                "sts", region_name=runtime_settings.aws_region
            ).get_caller_identity()
            aws_status = {
                "status": "ok",
                "account_id": caller.get("Account"),
                "caller_arn": caller.get("Arn"),
            }
        except (ClientError, BotoCoreError, ValueError) as exc:
            aws_status = {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}

    is_healthy = (
        database_status.get("status") == "ok" and aws_status.get("status") != "error"
    )
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if is_healthy else "degraded",
        "checks": {
            "database": database_status,
            "aws": aws_status,
        },
    }


@app.post(
    "/v1/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED
)
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


@app.get("/v1/bootstrap/status", response_model=BootstrapStatusResponse)
def get_bootstrap_status(
    request: Request,
    db: Session = Depends(get_db),
) -> BootstrapStatusResponse:
    actor, _ = _actor_and_ip(request)
    has_identities = _has_any_identities(db)
    active_identity = db.execute(
        select(UserIdentity).where(
            UserIdentity.actor == actor, UserIdentity.active.is_(True)
        )
    ).scalar_one_or_none()
    return BootstrapStatusResponse(
        actor=actor,
        bootstrap_required=not has_identities,
        actor_has_identity=active_identity is not None,
        actor_is_admin=bool(active_identity and active_identity.role == "admin"),
    )


@app.post(
    "/v1/bootstrap/user-identities",
    response_model=UserIdentityResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_bootstrap_user_identity(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    bootstrap_secret: str | None = Header(default=None, alias="X-Bootstrap-Secret"),
) -> UserIdentityResponse:
    _require_bootstrap_flow_enabled()
    actor, source_ip = _actor_and_ip(request)
    if _has_any_identities(db):
        active_identity = db.execute(
            select(UserIdentity).where(
                UserIdentity.actor == actor, UserIdentity.active.is_(True)
            )
        ).scalar_one_or_none()
        if active_identity and active_identity.role == "admin":
            response.status_code = status.HTTP_200_OK
            return _response(model_to_dict(active_identity), UserIdentityResponse)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bootstrap already completed. Sign in with an invited admin identity.",
        )
    row = _create_bootstrap_admin_identity(
        db,
        actor=actor,
        source_ip=source_ip,
        bootstrap_secret=bootstrap_secret,
    )
    return _response(model_to_dict(row), UserIdentityResponse)


def _invite_accept_base_url(request: Request) -> str:
    return str(request.url_for("accept_invite"))


def _configured_cognito_hosted_ui_url() -> str:
    runtime_settings = get_settings()
    hosted_ui_url = runtime_settings.cognito_hosted_ui_url.strip()
    if not hosted_ui_url:
        logger.error(
            "Cognito hosted UI URL is not configured; invite accept cannot redirect."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cognito hosted UI URL is not configured.",
        )
    return hosted_ui_url


def _cognito_invite_redirect_url(state: str) -> str:
    hosted_ui_url = _configured_cognito_hosted_ui_url()
    return _append_query_params(hosted_ui_url, {"state": state})


@app.post(
    "/v1/internal/tenants",
    response_model=InternalTenantCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_internal_tenant(
    req: InternalTenantCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    internal_admin: InternalAdminContext = Depends(require_internal_admin),
) -> InternalTenantCreateResponse:
    source_ip = request.client.host if request.client else None
    result = create_tenant_with_admin_invite(
        db,
        req=req,
        created_by=internal_admin.email,
        source_ip=source_ip,
        invite_accept_base_url=_invite_accept_base_url(request),
        ttl_hours=get_settings().magic_link_ttl_hours,
    )
    _write_internal_admin_audit_event(
        db,
        request=request,
        internal_admin=internal_admin,
        action="tenant.create",
        target_tenant_id=result.tenant.id,
        target_user_id=result.user.id,
    )
    db.commit()
    return InternalTenantCreateResponse(
        tenant_id=result.tenant.id,
        user_id=result.user.id,
        invite_email_sent_to=result.invite_email.recipient_email,
        invite_email_provider=result.invite_email.provider,
        invite_email_provider_message_id=result.invite_email.provider_message_id,
    )


@app.post(
    "/v1/internal/tenants/{tenant_id}/users/{user_id}/regenerate-invite",
    response_model=InternalTenantCreateResponse,
)
def post_internal_regenerate_invite(
    tenant_id: str,
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    internal_admin: InternalAdminContext = Depends(require_internal_admin),
) -> InternalTenantCreateResponse:
    source_ip = request.client.host if request.client else None
    result = regenerate_user_invite(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        created_by=internal_admin.email,
        source_ip=source_ip,
        invite_accept_base_url=_invite_accept_base_url(request),
        ttl_hours=get_settings().magic_link_ttl_hours,
    )
    _write_internal_admin_audit_event(
        db,
        request=request,
        internal_admin=internal_admin,
        action="tenant.invite_regenerate",
        target_tenant_id=tenant_id,
        target_user_id=user_id,
    )
    db.commit()
    return InternalTenantCreateResponse(
        tenant_id=result.tenant.id,
        user_id=result.user.id,
        invite_email_sent_to=result.invite_email.recipient_email,
        invite_email_provider=result.invite_email.provider,
        invite_email_provider_message_id=result.invite_email.provider_message_id,
    )


@app.get("/v1/internal/tenants", response_model=list[InternalTenantListItemResponse])
def get_internal_tenants(
    request: Request,
    internal_admin: InternalAdminContext = Depends(require_internal_admin),
    db: Session = Depends(get_db),
) -> list[InternalTenantListItemResponse]:
    summaries = list_internal_tenant_summaries(db)
    _write_internal_admin_audit_event(
        db,
        request=request,
        internal_admin=internal_admin,
        action="tenant.list_view",
        target_tenant_id=None,
        target_user_id=None,
    )
    db.commit()
    return [
        InternalTenantListItemResponse(
            tenant_id=item.tenant.id,
            tenant_name=item.tenant.name,
            federation_type=item.tenant.federation_type,
            admin_email=item.admin_email,
            created_at=item.tenant.created_at,
            last_login_at=item.admin_last_login_at,
        )
        for item in summaries
    ]


@app.get(
    "/v1/internal/tenants/{tenant_id}", response_model=InternalTenantDetailResponse
)
def get_internal_tenant_by_id(
    tenant_id: str,
    request: Request,
    internal_admin: InternalAdminContext = Depends(require_internal_admin),
    db: Session = Depends(get_db),
) -> InternalTenantDetailResponse:
    detail = get_internal_tenant_detail(db, tenant_id=tenant_id)
    invite_expires_by_user_id = dict(
        db.execute(
            select(MagicLinkToken.user_id, func.max(MagicLinkToken.expires_at))
            .where(
                and_(
                    MagicLinkToken.tenant_id == tenant_id,
                    MagicLinkToken.purpose == "invite_accept",
                    MagicLinkToken.consumed_at.is_(None),
                )
            )
            .group_by(MagicLinkToken.user_id)
        ).all()
    )
    _write_internal_admin_audit_event(
        db,
        request=request,
        internal_admin=internal_admin,
        action="tenant.detail_view",
        target_tenant_id=tenant_id,
        target_user_id=None,
    )
    db.commit()
    return InternalTenantDetailResponse(
        tenant_id=detail.tenant.id,
        tenant_name=detail.tenant.name,
        federation_type=detail.tenant.federation_type,
        idp_metadata=detail.tenant.idp_metadata_json,
        created_at=detail.tenant.created_at,
        updated_at=detail.tenant.updated_at,
        users=[
            InternalTenantUserResponse(
                **model_to_dict(user),
                invite_expires_at=invite_expires_by_user_id.get(user.id),
            )
            for user in detail.users
        ],
    )


@app.get("/v1/invite/accept", name="accept_invite")
def accept_invite(
    token: str = Query(min_length=10),
    db: Session = Depends(get_db),
) -> Response:
    _configured_cognito_hosted_ui_url()
    consumed = consume_invite_token(db, token=token)
    state = _encode_invite_state(
        InviteStatePayload(
            tenant_id=consumed.user.tenant_id,
            user_id=consumed.user.id,
            token_id=consumed.token.id,
            exp=int(
                (
                    datetime.now(UTC) + timedelta(seconds=_INVITE_STATE_TTL_SECONDS)
                ).timestamp()
            ),
        )
    )
    redirect_url = _cognito_invite_redirect_url(state)
    return RedirectResponse(
        url=redirect_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )


@app.get("/auth/callback", response_model=AuthCallbackResponse)
def get_auth_callback(
    request: Request,
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AuthCallbackResponse:
    identity_context = _identity_context_for_request(
        request, allowed_pools={"customer_pool"}
    )
    invite_payload = _decode_invite_state(state)
    if invite_payload is None:
        if state and state.partition(".")[0] == _INVITE_STATE_PREFIX:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid invite state.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return AuthCallbackResponse(
            status="ok",
            actor=identity_context.actor,
            invite_applied=False,
        )

    identity_email = identity_context.email
    invited_user = db.get(User, invite_payload.user_id)
    if invited_user is None or invited_user.tenant_id != invite_payload.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite user not found.",
        )
    invited_email = invited_user.email.strip().lower()
    if not identity_email or identity_email != invited_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invite email does not match authenticated identity.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    consume_invite_callback_state(
        db,
        token_id=invite_payload.token_id,
        tenant_id=invite_payload.tenant_id,
        user_id=invite_payload.user_id,
    )
    source_ip = request.client.host if request.client else None
    apply_invite_identity_mapping(
        db,
        tenant_id=invite_payload.tenant_id,
        user_id=invite_payload.user_id,
        actor=identity_context.actor,
        source_ip=source_ip,
        commit=False,
    )
    db.commit()
    tenant_name = (
        db.execute(
            select(Tenant.name).where(Tenant.id == invite_payload.tenant_id)
        ).scalar_one_or_none()
        or ""
    )
    emit_tenant_lifecycle_event(
        event_type="tenant.admin_invite_consumed",
        tenant_id=invite_payload.tenant_id,
        tenant_name=tenant_name,
        admin_email=invited_user.email,
        actor_email=identity_email,
    )
    return AuthCallbackResponse(
        status="ok",
        actor=identity_context.actor,
        invite_applied=True,
        user_id=invite_payload.user_id,
        tenant_id=invite_payload.tenant_id,
    )


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


@app.post(
    "/v1/user-identities",
    response_model=UserIdentityResponse,
    status_code=status.HTTP_201_CREATED,
)
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
        row = create_or_update_user_identity(db, req, actor=actor, source_ip=source_ip)
    else:
        _require_bootstrap_flow_enabled()
        row = _create_bootstrap_admin_identity(
            db,
            actor=actor,
            source_ip=source_ip,
            bootstrap_secret=bootstrap_secret,
            req=req,
        )
    return _response(model_to_dict(row), UserIdentityResponse)


@app.get("/v1/auth/me", response_model=AuthMeResponse)
def get_auth_me(
    request: Request,
    db: Session = Depends(get_db),
) -> AuthMeResponse:
    """Return the authenticated user's identity context (#75).

    Allows the UI to resolve role, tenant, team, and environment access
    from the OIDC subject without requiring the user to provide tenant UUIDs
    manually.
    """
    identity_context = _identity_context_for_request(
        request,
        allowed_pools={"customer_pool", "internal_pool"},
    )
    actor = identity_context.actor
    access: AccessContext | None = None
    try:
        access = _resolve_access_context(db, actor)
    except HTTPException:
        if identity_context.pool_source != "internal_pool":
            raise
    return AuthMeResponse(
        actor=actor,
        role=(
            access.role
            if access is not None
            else ("admin" if identity_context.is_internal_admin else "user")
        ),
        tenant_id=access.tenant_id if access is not None else None,
        team_id=access.team_id if access is not None else None,
        scoped_environment_ids=(
            sorted(access.scoped_environment_ids) if access is not None else []
        ),
        email=identity_context.email,
        is_internal_admin=identity_context.is_internal_admin,
    )


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
    row = add_team_environment_scope(
        db, team_id, environment_id, actor=actor, source_ip=source_ip
    )
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
    remove_team_environment_scope(
        db, team_id, environment_id, actor=actor, source_ip=source_ip
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/v1/teams/{team_id}/environments",
    response_model=list[TeamEnvironmentScopeResponse],
)
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
    rows = [
        env
        for env in list_environments(db, tenant_id, limit=limit, offset=offset)
        if _can_access_environment(access, env)
    ]
    return [_response(model_to_dict(env), EnvironmentResponse) for env in rows]


def _authorize_discovery(
    db: Session,
    access: "AccessContext",
    customer_role_arn: str,
) -> None:
    """Enforce discovery authorization.

    - Admin: allowed unconditionally.
    - Operator: allowed only if the account_id embedded in customer_role_arn is already
      associated with an environment in the caller's tenant, OR the caller's tenant has no
      environments yet (first-time setup grace).
    - All other roles: forbidden.

    This prevents tenant-scoped operators from probing arbitrary cross-account roles while
    still supporting the onboarding path (initial environment creation).
    """
    if access.role == "admin":
        return

    if access.role not in {"operator"}:
        raise _forbidden("Admin or operator role is required for BYOC-Lite discovery.")

    requested_account_id = parse_role_account_id_from_arn(customer_role_arn)
    if not requested_account_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="customer_role_arn must be a valid IAM role ARN.",
        )

    tenant_envs = (
        db.execute(
            select(Environment).where(
                Environment.tenant_id == access.tenant_id,
                Environment.status != "deleted",
            )
        )
        .scalars()
        .all()
    )

    if not tenant_envs:
        # First-time setup: no environments yet in this tenant — allow discovery.
        return

    allowed_account_ids = {
        parse_role_account_id_from_arn(env.customer_role_arn)
        for env in tenant_envs
        if env.customer_role_arn
    }
    allowed_account_ids.discard(None)

    if requested_account_id not in allowed_account_ids:
        raise _forbidden(
            f"Operator discovery is restricted to AWS accounts already associated with your tenant "
            f"({', '.join(sorted(allowed_account_ids)) or 'none'}). "
            f"Requested account {requested_account_id} is not in the allowed set. "
            f"Contact your SparkPilot admin to add a new account."
        )


@app.get("/v1/aws/byoc-lite/discovery", response_model=AwsByocLiteDiscoveryResponse)
def get_byoc_lite_discovery(
    request: Request,
    customer_role_arn: str = Query(..., min_length=20, max_length=1024),
    region: str = Query(default="us-east-1", min_length=2, max_length=64),
    tenant_id: str | None = Query(default=None, min_length=1, max_length=128),
    db: Session = Depends(get_db),
) -> AwsByocLiteDiscoveryResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    normalized_role_arn = customer_role_arn.strip()
    _authorize_discovery(db, access, normalized_role_arn)

    from sparkpilot.aws_clients import discover_eks_clusters_for_role

    normalized_region = region.strip() or "us-east-1"
    if not normalized_role_arn:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="customer_role_arn is required.",
        )

    try:
        discovered = discover_eks_clusters_for_role(
            customer_role_arn=normalized_role_arn,
            region=normalized_region,
        )
    except ParamValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid BYOC-Lite discovery parameters. {exc}",
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = str(error.get("Code") or "ClientError")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AWS service error during BYOC-Lite discovery ({code}). Retry and verify IAM permissions.",
        ) from None
    except BotoCoreError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Unable to complete BYOC-Lite discovery due to an AWS SDK/transport error. "
                "Retry and verify region + IAM permissions if this persists."
            ),
        ) from None

    clusters = [
        AwsByocLiteClusterDiscoveryItem(
            name=str(item.get("name") or ""),
            arn=str(item.get("arn") or ""),
            status=str(item.get("status") or "UNKNOWN"),
            version=str(item.get("version") or "").strip() or None,
            oidc_issuer=str(item.get("oidc_issuer") or "").strip() or None,
            has_oidc=bool(item.get("has_oidc")),
        )
        for item in discovered.get("clusters", [])
    ]
    clusters = [item for item in clusters if item.name and item.arn]
    recommended = _recommended_cluster(clusters)
    target_tenant = (tenant_id or access.tenant_id or "").strip() or None
    namespace_suggestion = (
        _suggest_namespace(
            tenant_id=target_tenant,
            actor=target_tenant,
            cluster_name=recommended.name if recommended else None,
        )
        if target_tenant
        else None
    )

    return AwsByocLiteDiscoveryResponse(
        customer_role_arn=normalized_role_arn,
        region=normalized_region,
        account_id=str(discovered.get("account_id") or "").strip() or None,
        recommended_cluster_arn=recommended.arn if recommended else None,
        namespace_suggestion=namespace_suggestion,
        clusters=clusters,
    )


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
        return (
            status.HTTP_201_CREATED,
            model_to_dict(op),
            "provisioning_operation",
            op.id,
        )

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


@app.post(
    "/v1/environments/{environment_id}/retry",
    response_model=ProvisioningOperationResponse,
)
def post_environment_retry(
    environment_id: str,
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ProvisioningOperationResponse:
    key = _require_idempotency_key(idempotency_key)
    actor, source_ip = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_role(
        access, {"admin", "operator"}, "Only admin/operator can retry provisioning."
    )
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    op = retry_environment_provisioning(
        db,
        environment_id,
        actor=actor,
        source_ip=source_ip,
        idempotency_key=key,
    )
    return _response(model_to_dict(op), ProvisioningOperationResponse)


@app.delete("/v1/environments/{environment_id}", response_model=EnvironmentResponse)
def delete_environment_by_id(
    environment_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> EnvironmentResponse:
    actor, source_ip = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_role(
        access, {"admin", "operator"}, "Only admin/operator can delete environments."
    )
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    deleted = delete_environment(db, environment_id, actor=actor, source_ip=source_ip)
    return _response(model_to_dict(deleted), EnvironmentResponse)


@app.get(
    "/v1/environments/{environment_id}/preflight", response_model=PreflightResponse
)
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
    db.commit()  # persist audit events from policy evaluation
    return PreflightResponse(**payload)


@app.get(
    "/v1/provisioning-operations/{operation_id}",
    response_model=ProvisioningOperationResponse,
)
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
    _require_role(
        access, {"admin", "operator", "user"}, "Only admin/operator/user can list jobs."
    )
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
        db,
        environment_id=environment_id,
        limit=limit,
        offset=offset,
        allowed_environment_ids=allowed_env_ids,
    )
    return [
        _response(_golden_path_to_response_payload(row), GoldenPathResponse)
        for row in rows
    ]


@app.post(
    "/v1/golden-paths",
    response_model=GoldenPathResponse,
    status_code=status.HTTP_201_CREATED,
)
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
        db,
        tenant_id,
        state,
        limit=limit,
        offset=offset,
        actor=actor_filter,
        environment_ids=env_ids_filter,
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


@app.post(
    "/v1/jobs/{job_id}/runs",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
)
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
    _require_role(
        access,
        {"admin", "operator", "user"},
        "Only admin/operator/user can submit runs.",
    )
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found."
        )
    env = get_environment(db, job.environment_id)
    # Jobs are environment-scoped resources. Users can submit runs against any job
    # within environments they are explicitly authorized to access.
    _require_environment_access(access, env)

    result = with_idempotency(
        db,
        scope=f"POST:/v1/jobs/{job_id}/runs",
        key=key,
        payload=req.model_dump(),
        execute=lambda: _create_run_result_with_preflight(
            db, job_id, req, actor, source_ip, key
        ),
    )
    response.status_code = result.status_code
    if result.replayed:
        response.headers["X-Idempotent-Replay"] = "true"
    preflight = (
        result.body.get("preflight")
        if isinstance(result.body.get("preflight"), dict)
        else None
    )
    return _run_response(result.body, preflight=preflight)


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
    preflight = _latest_run_preflight_snapshot(db, run.id)
    return _run_response(model_to_dict(run), env, preflight=preflight)


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
        execute=lambda: _cancel_run_result_with_preflight(db, run_id, actor, source_ip),
    )
    response.status_code = result.status_code
    if result.replayed:
        response.headers["X-Idempotent-Replay"] = "true"
    preflight = (
        result.body.get("preflight")
        if isinstance(result.body.get("preflight"), dict)
        else None
    )
    return _run_response(result.body, preflight=preflight)


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
    items = get_usage(
        db, tenant_id, effective_from, effective_to, limit=limit, offset=offset
    )
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


@app.post(
    "/v1/team-budgets",
    response_model=TeamBudgetResponse,
    status_code=status.HTTP_201_CREATED,
)
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
    _require_role(
        access, {"admin", "operator"}, "Only admin/operator can view team budgets."
    )
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
    _require_role(
        access, {"admin", "operator"}, "Only admin/operator can view showback costs."
    )
    if access.role != "admin" and access.tenant_id != team:
        raise _forbidden("Operator can only view showback for assigned tenant key.")
    return get_cost_showback(db, team=team, period=period, limit=limit, offset=offset)


@app.post(
    "/v1/environments/{environment_id}/job-templates",
    response_model=JobTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_job_template(
    environment_id: str,
    req: JobTemplateCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> JobTemplateResponse:
    from sparkpilot.aws_clients import EmrEksClient

    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_role(
        access, {"admin", "operator"}, "Only admin/operator can create job templates."
    )
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    emr_client = EmrEksClient()
    emr_template_id: str | None = None
    if not emr_client.settings.dry_run_mode:
        emr_template_id = emr_client.create_job_template(
            env,
            name=req.name,
            job_driver=req.job_driver,
            configuration_overrides=req.configuration_overrides,
            tags=req.tags,
        )
    template = JobTemplate(
        environment_id=environment_id,
        tenant_id=env.tenant_id,
        name=req.name,
        description=req.description,
        emr_template_id=emr_template_id,
        job_driver_json=req.job_driver,
        configuration_overrides_json=req.configuration_overrides,
        tags_json=req.tags,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _job_template_response(template)


@app.get(
    "/v1/environments/{environment_id}/job-templates",
    response_model=list[JobTemplateResponse],
)
def get_job_templates(
    environment_id: str,
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[JobTemplateResponse]:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    rows = (
        db.execute(
            select(JobTemplate)
            .where(JobTemplate.environment_id == environment_id)
            .order_by(JobTemplate.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return [_job_template_response(t) for t in rows]


@app.get(
    "/v1/environments/{environment_id}/job-templates/{template_id}",
    response_model=JobTemplateResponse,
)
def get_job_template_by_id(
    environment_id: str,
    template_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> JobTemplateResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    template = db.get(JobTemplate, template_id)
    if template is None or template.environment_id != environment_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job template not found."
        )
    return _job_template_response(template)


@app.delete(
    "/v1/environments/{environment_id}/job-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_job_template(
    environment_id: str,
    template_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    from sparkpilot.aws_clients import EmrEksClient

    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_role(
        access, {"admin", "operator"}, "Only admin/operator can delete job templates."
    )
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    template = db.get(JobTemplate, template_id)
    if template is None or template.environment_id != environment_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job template not found."
        )
    _emr_del = EmrEksClient()
    if template.emr_template_id and not _emr_del.settings.dry_run_mode:
        _emr_del.delete_job_template(env, template.emr_template_id)
    db.delete(template)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/v1/environments/{environment_id}/queue-utilization",
    response_model=QueueUtilizationResponse,
)
def get_queue_utilization(
    environment_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> QueueUtilizationResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    active_states = {"queued", "dispatching", "accepted", "running"}
    active_runs = (
        db.execute(
            select(Run).where(
                Run.environment_id == environment_id,
                Run.state.in_(active_states),
            )
        )
        .scalars()
        .all()
    )
    used_vcpu = _compute_active_vcpu(list(active_runs))
    utilization_pct: float | None = None
    if env.yunikorn_queue_max_vcpu:
        utilization_pct = round(used_vcpu / env.yunikorn_queue_max_vcpu * 100, 2)
    return QueueUtilizationResponse(
        environment_id=environment_id,
        yunikorn_queue=env.yunikorn_queue,
        active_run_count=len(active_runs),
        used_vcpu=used_vcpu,
        guaranteed_vcpu=env.yunikorn_queue_guaranteed_vcpu,
        max_vcpu=env.yunikorn_queue_max_vcpu,
        utilization_pct=utilization_pct,
    )


@app.post(
    "/v1/environments/{environment_id}/endpoints",
    response_model=InteractiveEndpointResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_interactive_endpoint(
    environment_id: str,
    req: InteractiveEndpointCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> InteractiveEndpointResponse:
    from sparkpilot.aws_clients import EmrEksClient

    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_role(
        access, {"admin", "operator"}, "Only admin/operator can create endpoints."
    )
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    _emr_ep = EmrEksClient()
    emr_endpoint_id: str | None = None
    if not _emr_ep.settings.dry_run_mode:
        emr_endpoint_id = _emr_ep.create_managed_endpoint(
            env,
            name=req.name,
            execution_role_arn=req.execution_role_arn,
            release_label=req.release_label,
            certificate_arn=req.certificate_arn,
        )
    endpoint = InteractiveEndpoint(
        environment_id=environment_id,
        tenant_id=env.tenant_id,
        name=req.name,
        emr_endpoint_id=emr_endpoint_id,
        execution_role_arn=req.execution_role_arn,
        release_label=req.release_label,
        idle_timeout_minutes=req.idle_timeout_minutes,
        certificate_arn=req.certificate_arn,
        status="creating",
        created_by_actor=actor,
    )
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    return _interactive_endpoint_response(endpoint)


@app.get(
    "/v1/environments/{environment_id}/endpoints",
    response_model=list[InteractiveEndpointResponse],
)
def get_interactive_endpoints(
    environment_id: str,
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[InteractiveEndpointResponse]:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    rows = (
        db.execute(
            select(InteractiveEndpoint)
            .where(InteractiveEndpoint.environment_id == environment_id)
            .order_by(InteractiveEndpoint.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return [_interactive_endpoint_response(ep) for ep in rows]


@app.get(
    "/v1/environments/{environment_id}/endpoints/{endpoint_id}",
    response_model=InteractiveEndpointResponse,
)
def get_interactive_endpoint_by_id(
    environment_id: str,
    endpoint_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> InteractiveEndpointResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    endpoint = db.get(InteractiveEndpoint, endpoint_id)
    if endpoint is None or endpoint.environment_id != environment_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interactive endpoint not found.",
        )
    return _interactive_endpoint_response(endpoint)


@app.delete(
    "/v1/environments/{environment_id}/endpoints/{endpoint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_interactive_endpoint(
    environment_id: str,
    endpoint_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    from sparkpilot.aws_clients import EmrEksClient

    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_role(
        access, {"admin", "operator"}, "Only admin/operator can delete endpoints."
    )
    env = get_environment(db, environment_id)
    _require_environment_access(access, env)
    endpoint = db.get(InteractiveEndpoint, endpoint_id)
    if endpoint is None or endpoint.environment_id != environment_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interactive endpoint not found.",
        )
    _emr_ep_del = EmrEksClient()
    if endpoint.emr_endpoint_id and not _emr_ep_del.settings.dry_run_mode:
        _emr_ep_del.delete_managed_endpoint(env, endpoint.emr_endpoint_id)
    db.delete(endpoint)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


def _create_run_result_with_preflight(
    db: Session,
    job_id: str,
    req: RunCreateRequest,
    actor: str,
    source_ip: str | None,
    key: str,
) -> tuple[int, dict[str, Any], str | None, str | None]:
    status_code, body, entity_type, entity_id = _create_run_result(
        db,
        job_id,
        req,
        actor,
        source_ip,
        key,
    )
    body_with_preflight = dict(body)
    body_with_preflight["preflight"] = _latest_run_preflight_snapshot(db, body["id"])
    return status_code, body_with_preflight, entity_type, entity_id


def _cancel_run_result(
    db: Session,
    run_id: str,
    actor: str,
    source_ip: str | None,
) -> tuple[int, dict[str, Any], str | None, str | None]:
    run = cancel_run(db, run_id, actor=actor, source_ip=source_ip, commit=False)
    return status.HTTP_200_OK, model_to_dict(run), "run", run.id


def _cancel_run_result_with_preflight(
    db: Session,
    run_id: str,
    actor: str,
    source_ip: str | None,
) -> tuple[int, dict[str, Any], str | None, str | None]:
    status_code, body, entity_type, entity_id = _cancel_run_result(
        db, run_id, actor, source_ip
    )
    body_with_preflight = dict(body)
    body_with_preflight["preflight"] = _latest_run_preflight_snapshot(db, body["id"])
    return status_code, body_with_preflight, entity_type, entity_id


def _job_template_response(t: JobTemplate) -> JobTemplateResponse:
    return JobTemplateResponse(
        id=t.id,
        environment_id=t.environment_id,
        tenant_id=t.tenant_id,
        name=t.name,
        description=t.description,
        emr_template_id=t.emr_template_id,
        job_driver=t.job_driver_json,
        configuration_overrides=t.configuration_overrides_json,
        tags=t.tags_json,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _interactive_endpoint_response(
    ep: InteractiveEndpoint,
) -> InteractiveEndpointResponse:
    return InteractiveEndpointResponse(
        id=ep.id,
        environment_id=ep.environment_id,
        tenant_id=ep.tenant_id,
        name=ep.name,
        emr_endpoint_id=ep.emr_endpoint_id,
        execution_role_arn=ep.execution_role_arn,
        release_label=ep.release_label,
        status=ep.status,
        idle_timeout_minutes=ep.idle_timeout_minutes,
        certificate_arn=ep.certificate_arn,
        endpoint_url=ep.endpoint_url,
        created_by_actor=ep.created_by_actor,
        created_at=ep.created_at,
        updated_at=ep.updated_at,
    )


def _compute_active_vcpu(runs: list[Run]) -> int:
    total = 0
    for run in runs:
        resources = run.requested_resources_json or {}
        total += resources.get("driver_vcpu", 0) + resources.get(
            "executor_vcpu", 0
        ) * resources.get("executor_instances", 0)
    return total


@app.get("/v1/metrics/kpis")
def get_kpi_metrics(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return operational KPI metrics. Admin-only."""
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    from sparkpilot.metrics import collect_all_kpis

    return collect_all_kpis(db)


# ---------------------------------------------------------------------------
# Policy Engine endpoints (R13 #39)
# ---------------------------------------------------------------------------


@app.post(
    "/v1/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED
)
def post_policy(
    req: PolicyCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PolicyResponse:
    actor, source_ip = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    from sparkpilot.policy_engine import create_policy, policy_to_dict

    policy = create_policy(
        db,
        name=req.name,
        scope=req.scope,
        scope_id=req.scope_id,
        rule_type=req.rule_type,
        config=req.config,
        enforcement=req.enforcement,
        active=req.active,
        actor=actor,
        source_ip=source_ip,
    )
    return _response(policy_to_dict(policy), PolicyResponse)


@app.get("/v1/policies", response_model=list[PolicyResponse])
def get_policies(
    request: Request,
    scope: str | None = Query(default=None),
    scope_id: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[PolicyResponse]:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    from sparkpilot.policy_engine import list_policies, policy_to_dict

    rows = list_policies(
        db,
        scope=scope,
        scope_id=scope_id,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    return [_response(policy_to_dict(p), PolicyResponse) for p in rows]


@app.get("/v1/policies/{policy_id}", response_model=PolicyResponse)
def get_policy_by_id(
    policy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> PolicyResponse:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    from sparkpilot.policy_engine import get_policy, policy_to_dict

    policy = get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found."
        )
    return _response(policy_to_dict(policy), PolicyResponse)


@app.delete("/v1/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy_endpoint(
    policy_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    actor, source_ip = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    from sparkpilot.policy_engine import delete_policy

    if not delete_policy(db, policy_id, actor=actor, source_ip=source_ip):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found."
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Security Configuration endpoints (#53)
# ---------------------------------------------------------------------------


@app.post(
    "/v1/environments/{environment_id}/security-configurations",
    response_model=SecurityConfigurationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_security_configuration_endpoint(
    environment_id: str,
    req: SecurityConfigurationCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    actor, source_ip = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    env = db.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found.")
    from sparkpilot.aws_clients import EmrEksClient
    from sparkpilot.audit import write_audit_event

    emr = EmrEksClient()
    result = emr.create_security_configuration(
        env,
        name=req.name,
        encryption_config=req.encryption_config,
        authorization_config=req.authorization_config,
    )
    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action="security_configuration.created",
        entity_type="security_configuration",
        entity_id=result.get("id", ""),
        details={
            "environment_id": environment_id,
            "name": req.name,
            "result": result,
        },
    )
    db.commit()
    return _response(
        {
            "id": result.get("id", ""),
            "name": result.get("name", req.name),
            "virtual_cluster_id": req.virtual_cluster_id,
            "encryption_config": req.encryption_config,
            "authorization_config": req.authorization_config,
            "created_at": datetime.now(UTC).isoformat(),
        },
        SecurityConfigurationResponse,
    )


@app.get(
    "/v1/environments/{environment_id}/security-configurations",
    response_model=list[SecurityConfigurationResponse],
)
def list_security_configurations_endpoint(
    environment_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_role(access, {"admin", "operator"}, "Operator or admin role required.")
    env = db.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found.")
    from sparkpilot.aws_clients import EmrEksClient

    emr = EmrEksClient()
    configs = emr.list_security_configurations(env)
    return [
        _response(
            {
                "id": c.get("id", ""),
                "name": c.get("name", ""),
                "virtual_cluster_id": env.emr_virtual_cluster_id or "",
                "encryption_config": c.get("securityConfigurationData", {}).get(
                    "encryptionConfiguration"
                ),
                "authorization_config": c.get("securityConfigurationData", {}).get(
                    "authorizationConfiguration"
                ),
                "created_at": str(c.get("createdAt", "")),
            },
            SecurityConfigurationResponse,
        )
        for c in configs
    ]


@app.get(
    "/v1/environments/{environment_id}/security-configurations/{config_id}",
    response_model=SecurityConfigurationResponse,
)
def describe_security_configuration_endpoint(
    environment_id: str,
    config_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_role(access, {"admin", "operator"}, "Operator or admin role required.")
    env = db.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found.")
    from sparkpilot.aws_clients import EmrEksClient

    emr = EmrEksClient()
    try:
        result = emr.describe_security_configuration(env, config_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    sc_data = result.get("securityConfigurationData", {})
    return _response(
        {
            "id": result.get("id", config_id),
            "name": result.get("name", ""),
            "virtual_cluster_id": env.emr_virtual_cluster_id or "",
            "encryption_config": sc_data.get("encryptionConfiguration"),
            "authorization_config": sc_data.get("authorizationConfiguration"),
            "created_at": result.get("createdAt"),
        },
        SecurityConfigurationResponse,
    )


# ---------------------------------------------------------------------------
# IAM credential chain validation (#76)
# ---------------------------------------------------------------------------


@app.get("/v1/environments/{environment_id}/iam-validation")
def validate_iam_credential_chain(
    environment_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    env = db.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found.")
    from sparkpilot.services.iam_validation import validate_full_credential_chain

    result = validate_full_credential_chain(
        customer_role_arn=env.customer_role_arn,
        region=env.region,
    )
    result["environment_id"] = environment_id
    return result


@app.get("/v1/iam-validation")
def validate_runtime_iam_identity(
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """Validate runtime identity without customer role assumption."""
    actor, _ = _actor_and_ip(request)
    access = _resolve_access_context(db, actor)
    _require_admin(access)
    from sparkpilot.services.iam_validation import validate_full_credential_chain

    return validate_full_credential_chain()
