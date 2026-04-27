"""Internal-admin tenant provisioning and invite lifecycle operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import logging
import secrets

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from sparkpilot.audit import write_audit_event
from sparkpilot.exceptions import (
    ConflictError,
    EntityNotFoundError,
    GoneError,
    ValidationError,
)
from sparkpilot.models import MagicLinkLog, MagicLinkToken, Tenant, User, UserIdentity
from sparkpilot.schemas import InternalTenantCreateRequest, TenantCreateRequest
from sparkpilot.services.crud import create_tenant

logger = logging.getLogger(__name__)

INVITE_ACCEPT_PURPOSE = "invite_accept"


@dataclass(frozen=True)
class InternalTenantProvisionResult:
    tenant: Tenant
    user: User
    magic_link_url: str


@dataclass(frozen=True)
class InternalTenantSummary:
    tenant: Tenant
    admin_email: str | None
    admin_last_login_at: datetime | None


@dataclass(frozen=True)
class InternalTenantDetail:
    tenant: Tenant
    users: list[User]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not email or "@" not in email:
        raise ValidationError("admin_email must be a valid email address.")
    return email


def hash_magic_link_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_magic_link_token(
    db: Session,
    *,
    user_id: str,
    tenant_id: str,
    created_by: str,
    expires_at: datetime,
) -> tuple[MagicLinkToken, str]:
    plain_token = secrets.token_urlsafe(32)
    token_hash = hash_magic_link_token(plain_token)
    row = MagicLinkToken(
        token_hash=token_hash,
        user_id=user_id,
        tenant_id=tenant_id,
        purpose=INVITE_ACCEPT_PURPOSE,
        expires_at=expires_at,
        consumed_at=None,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row, plain_token


def _log_magic_link_stub(
    db: Session,
    *,
    user_id: str,
    tenant_id: str,
    created_by: str,
    magic_link_url: str,
) -> None:
    # Stubbed sender for this session: log full URL for manual testing.
    logger.info("Magic link (stub): %s", magic_link_url)
    print(f"[magic-link-stub] {magic_link_url}")
    db.add(
        MagicLinkLog(
            user_id=user_id,
            tenant_id=tenant_id,
            purpose=INVITE_ACCEPT_PURPOSE,
            magic_link_url=magic_link_url,
            created_by=created_by,
        )
    )


def _invalidate_unconsumed_user_invites(
    db: Session, *, user_id: str, now: datetime
) -> None:
    rows = db.execute(
        select(MagicLinkToken).where(
            and_(
                MagicLinkToken.user_id == user_id,
                MagicLinkToken.purpose == INVITE_ACCEPT_PURPOSE,
                MagicLinkToken.consumed_at.is_(None),
            )
        )
    ).scalars()
    for row in rows:
        row.consumed_at = now


def create_tenant_with_admin_invite(
    db: Session,
    *,
    req: InternalTenantCreateRequest,
    created_by: str,
    source_ip: str | None,
    invite_accept_base_url: str,
    ttl_hours: int,
) -> InternalTenantProvisionResult:
    tenant = create_tenant(
        db,
        TenantCreateRequest(
            name=req.name,
            federation_type=req.federation_type,
            idp_metadata=req.idp_metadata,
        ),
        actor=created_by,
        source_ip=source_ip,
        commit=False,
    )
    now = _utc_now()
    admin_email = _normalize_email(req.admin_email)
    existing_admin = db.execute(
        select(User).where(
            and_(
                User.tenant_id == tenant.id,
                User.email == admin_email,
            )
        )
    ).scalar_one_or_none()
    if existing_admin is not None:
        raise ConflictError("Admin email already exists for tenant.")

    user = User(
        tenant_id=tenant.id,
        email=admin_email,
        role="admin",
        invited_at=now,
    )
    db.add(user)
    db.flush()
    expires_at = now + timedelta(hours=ttl_hours)
    _, plain_token = _create_magic_link_token(
        db,
        user_id=user.id,
        tenant_id=tenant.id,
        created_by=created_by,
        expires_at=expires_at,
    )
    magic_link_url = f"{invite_accept_base_url}?token={plain_token}"
    _log_magic_link_stub(
        db,
        user_id=user.id,
        tenant_id=tenant.id,
        created_by=created_by,
        magic_link_url=magic_link_url,
    )
    write_audit_event(
        db,
        actor=created_by,
        source_ip=source_ip,
        action="user.invite_created",
        entity_type="user",
        entity_id=user.id,
        tenant_id=tenant.id,
        details={
            "email": user.email,
            "invite_expires_at": expires_at.isoformat(),
        },
    )
    db.commit()
    db.refresh(tenant)
    db.refresh(user)
    return InternalTenantProvisionResult(
        tenant=tenant,
        user=user,
        magic_link_url=magic_link_url,
    )


def regenerate_user_invite(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    created_by: str,
    source_ip: str | None,
    invite_accept_base_url: str,
    ttl_hours: int,
) -> InternalTenantProvisionResult:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise EntityNotFoundError("Tenant not found.")
    user = db.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise EntityNotFoundError("User not found.")

    now = _utc_now()
    _invalidate_unconsumed_user_invites(db, user_id=user.id, now=now)
    user.invited_at = now
    expires_at = now + timedelta(hours=ttl_hours)
    _, plain_token = _create_magic_link_token(
        db,
        user_id=user.id,
        tenant_id=tenant.id,
        created_by=created_by,
        expires_at=expires_at,
    )
    magic_link_url = f"{invite_accept_base_url}?token={plain_token}"
    _log_magic_link_stub(
        db,
        user_id=user.id,
        tenant_id=tenant.id,
        created_by=created_by,
        magic_link_url=magic_link_url,
    )
    write_audit_event(
        db,
        actor=created_by,
        source_ip=source_ip,
        action="user.invite_regenerated",
        entity_type="user",
        entity_id=user.id,
        tenant_id=tenant.id,
        details={
            "email": user.email,
            "invite_expires_at": expires_at.isoformat(),
        },
    )
    db.commit()
    db.refresh(tenant)
    db.refresh(user)
    return InternalTenantProvisionResult(
        tenant=tenant,
        user=user,
        magic_link_url=magic_link_url,
    )


def list_internal_tenant_summaries(db: Session) -> list[InternalTenantSummary]:
    tenants = list(
        db.execute(select(Tenant).order_by(Tenant.created_at.desc())).scalars()
    )
    summaries: list[InternalTenantSummary] = []
    for tenant in tenants:
        admin_user = db.execute(
            select(User)
            .where(and_(User.tenant_id == tenant.id, User.role == "admin"))
            .order_by(User.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        summaries.append(
            InternalTenantSummary(
                tenant=tenant,
                admin_email=admin_user.email if admin_user else None,
                admin_last_login_at=admin_user.last_login_at if admin_user else None,
            )
        )
    return summaries


def get_internal_tenant_detail(db: Session, *, tenant_id: str) -> InternalTenantDetail:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise EntityNotFoundError("Tenant not found.")
    users = list(
        db.execute(
            select(User)
            .where(User.tenant_id == tenant_id)
            .order_by(User.created_at.asc())
        ).scalars()
    )
    return InternalTenantDetail(tenant=tenant, users=users)


@dataclass(frozen=True)
class ConsumedInvite:
    token: MagicLinkToken
    user: User


def consume_invite_token(db: Session, *, token: str) -> ConsumedInvite:
    token_hash = hash_magic_link_token(token)
    row = db.execute(
        select(MagicLinkToken).where(
            and_(
                MagicLinkToken.token_hash == token_hash,
                MagicLinkToken.purpose == INVITE_ACCEPT_PURPOSE,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise EntityNotFoundError("Invite token not found.")

    now = _utc_now()
    if row.consumed_at is not None:
        raise GoneError("Invite token has already been consumed.")
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise GoneError("Invite token has expired.")

    user = db.get(User, row.user_id)
    if user is None:
        raise EntityNotFoundError("Invite user not found.")

    row.consumed_at = now
    user.invite_consumed_at = now
    db.commit()
    db.refresh(row)
    db.refresh(user)
    return ConsumedInvite(token=row, user=user)


def apply_invite_identity_mapping(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    actor: str,
    source_ip: str | None,
) -> UserIdentity:
    user = db.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise EntityNotFoundError("Invite user not found.")

    existing_for_user = db.execute(
        select(UserIdentity).where(UserIdentity.user_id == user.id)
    ).scalar_one_or_none()
    existing_for_actor = db.execute(
        select(UserIdentity).where(UserIdentity.actor == actor)
    ).scalar_one_or_none()

    if existing_for_user is not None:
        logger.info(
            "Invite callback found existing user_identity for user_id=%s; updating login.",
            user.id,
        )
        if existing_for_actor and existing_for_actor.id != existing_for_user.id:
            raise ConflictError(
                "Authenticated actor is already mapped to another user."
            )
        row = existing_for_user
        if row.actor != actor:
            logger.warning(
                "Invite callback actor mismatch for user_id=%s (existing=%s incoming=%s); "
                "preserving existing mapping.",
                user.id,
                row.actor,
                actor,
            )
    elif existing_for_actor is not None:
        if existing_for_actor.user_id not in {None, user.id}:
            raise ConflictError(
                "Authenticated actor is already mapped to another user."
            )
        row = existing_for_actor
    else:
        row = UserIdentity(actor=actor, role="admin", user_id=user.id)
        db.add(row)
        db.flush()

    if existing_for_user is None:
        row.actor = actor
    row.user_id = user.id
    row.role = "admin" if user.role == "admin" else "user"
    row.tenant_id = user.tenant_id
    row.team_id = None
    row.active = True

    user.last_login_at = _utc_now()

    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action="user.invite_login_completed",
        entity_type="user",
        entity_id=user.id,
        tenant_id=user.tenant_id,
        details={"email": user.email},
    )
    write_audit_event(
        db,
        actor=actor,
        source_ip=source_ip,
        action="user_identity.invite_mapping_upsert",
        entity_type="user_identity",
        entity_id=row.id,
        tenant_id=user.tenant_id,
        details={"user_id": user.id},
    )
    db.commit()
    db.refresh(row)
    return row
