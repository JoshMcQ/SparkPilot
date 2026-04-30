"""Internal-admin tenant provisioning and invite lifecycle operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import logging
import secrets

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from sparkpilot.audit import write_audit_event
from sparkpilot.crm_webhook import emit_tenant_lifecycle_event
from sparkpilot.exceptions import (
    ConflictError,
    EntityNotFoundError,
    GoneError,
    SparkPilotError,
    ValidationError,
)
from sparkpilot.invite_email import InviteEmailDelivery, send_invite_email
from sparkpilot.models import MagicLinkLog, MagicLinkToken, Tenant, User, UserIdentity
from sparkpilot.schemas import InternalTenantCreateRequest, TenantCreateRequest
from sparkpilot.services.crud import create_tenant

logger = logging.getLogger(__name__)

INVITE_ACCEPT_PURPOSE = "invite_accept"


@dataclass(frozen=True)
class InternalTenantProvisionResult:
    tenant: Tenant
    user: User
    invite_email: InviteEmailDelivery


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


def _log_magic_link_issued(
    db: Session,
    *,
    user_id: str,
    tenant_id: str,
    created_by: str,
    magic_link_url: str,
) -> None:
    redacted_magic_link = magic_link_url.split("?", 1)[0]
    logger.info(
        "Invite magic link issued user_id=%s tenant_id=%s purpose=%s created_by=%s",
        user_id,
        tenant_id,
        INVITE_ACCEPT_PURPOSE,
        created_by,
    )
    db.add(
        MagicLinkLog(
            user_id=user_id,
            tenant_id=tenant_id,
            purpose=INVITE_ACCEPT_PURPOSE,
            magic_link_url=redacted_magic_link,
            created_by=created_by,
        )
    )


def _send_invite_email_and_audit(
    db: Session,
    *,
    tenant: Tenant,
    user: User,
    created_by: str,
    source_ip: str | None,
    invite_url: str,
    ttl_hours: int,
    idempotency_key: str,
    failure_detail: str,
) -> InviteEmailDelivery:
    try:
        delivery = send_invite_email(
            recipient_email=user.email,
            tenant_name=tenant.name,
            invite_url=invite_url,
            tenant_id=tenant.id,
            user_id=user.id,
            ttl_hours=ttl_hours,
            idempotency_key=idempotency_key,
        )
    except SparkPilotError as exc:
        write_audit_event(
            db,
            actor=created_by,
            source_ip=source_ip,
            action="user.invite_email_failed",
            entity_type="user",
            entity_id=user.id,
            tenant_id=tenant.id,
            details={
                "email": user.email,
                "provider": "resend",
                "error_type": exc.__class__.__name__,
            },
        )
        db.commit()
        raise SparkPilotError(failure_detail, status_code=exc.status_code) from exc

    write_audit_event(
        db,
        actor=created_by,
        source_ip=source_ip,
        action="user.invite_email_sent",
        entity_type="user",
        entity_id=user.id,
        tenant_id=tenant.id,
        details={
            "email": user.email,
            "provider": delivery.provider,
            "provider_message_id": delivery.provider_message_id,
        },
    )
    db.commit()
    return delivery


def _invalidate_unconsumed_user_invites(
    db: Session, *, user_id: str, now: datetime
) -> None:
    db.execute(
        update(MagicLinkToken)
        .where(
            and_(
                MagicLinkToken.user_id == user_id,
                MagicLinkToken.purpose == INVITE_ACCEPT_PURPOSE,
                MagicLinkToken.consumed_at.is_(None),
            )
        )
        .values(consumed_at=now)
    )


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
    token_row, plain_token = _create_magic_link_token(
        db,
        user_id=user.id,
        tenant_id=tenant.id,
        created_by=created_by,
        expires_at=expires_at,
    )
    token_id = token_row.id
    magic_link_url = f"{invite_accept_base_url}?token={plain_token}"
    _log_magic_link_issued(
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
    invite_email = _send_invite_email_and_audit(
        db,
        tenant=tenant,
        user=user,
        created_by=created_by,
        source_ip=source_ip,
        invite_url=magic_link_url,
        ttl_hours=ttl_hours,
        idempotency_key=f"invite:{token_id}",
        failure_detail=(
            "Tenant was created, but invite email delivery failed. "
            "Fix invite email configuration and regenerate the invite from tenant detail."
        ),
    )
    emit_tenant_lifecycle_event(
        event_type="tenant.created",
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        admin_email=user.email,
        actor_email=created_by,
    )
    return InternalTenantProvisionResult(
        tenant=tenant,
        user=user,
        invite_email=invite_email,
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
    token_row, plain_token = _create_magic_link_token(
        db,
        user_id=user.id,
        tenant_id=tenant.id,
        created_by=created_by,
        expires_at=expires_at,
    )
    token_id = token_row.id
    magic_link_url = f"{invite_accept_base_url}?token={plain_token}"
    _log_magic_link_issued(
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
    invite_email = _send_invite_email_and_audit(
        db,
        tenant=tenant,
        user=user,
        created_by=created_by,
        source_ip=source_ip,
        invite_url=magic_link_url,
        ttl_hours=ttl_hours,
        idempotency_key=f"invite:{token_id}",
        failure_detail=(
            "Invite was regenerated, but invite email delivery failed. "
            "Fix invite email configuration and regenerate the invite again."
        ),
    )
    emit_tenant_lifecycle_event(
        event_type="tenant.invite_regenerated",
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        admin_email=user.email,
        actor_email=created_by,
    )
    return InternalTenantProvisionResult(
        tenant=tenant,
        user=user,
        invite_email=invite_email,
    )


def list_internal_tenant_summaries(db: Session) -> list[InternalTenantSummary]:
    ranked_admins = (
        select(
            User.tenant_id.label("tenant_id"),
            User.email.label("admin_email"),
            User.last_login_at.label("admin_last_login_at"),
            func.row_number()
            .over(
                partition_by=User.tenant_id,
                order_by=(User.created_at.asc(), User.id.asc()),
            )
            .label("row_number"),
        )
        .where(User.role == "admin")
        .subquery()
    )
    rows = db.execute(
        select(
            Tenant,
            ranked_admins.c.admin_email,
            ranked_admins.c.admin_last_login_at,
        )
        .outerjoin(
            ranked_admins,
            and_(
                ranked_admins.c.tenant_id == Tenant.id,
                ranked_admins.c.row_number == 1,
            ),
        )
        .order_by(Tenant.created_at.desc())
    ).all()
    return [
        InternalTenantSummary(
            tenant=tenant,
            admin_email=admin_email,
            admin_last_login_at=admin_last_login_at,
        )
        for tenant, admin_email, admin_last_login_at in rows
    ]


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


def consume_invite_callback_state(
    db: Session,
    *,
    token_id: str,
    tenant_id: str,
    user_id: str,
) -> MagicLinkToken:
    now = _utc_now()
    updated = db.execute(
        update(MagicLinkToken)
        .where(
            and_(
                MagicLinkToken.id == token_id,
                MagicLinkToken.purpose == INVITE_ACCEPT_PURPOSE,
                MagicLinkToken.tenant_id == tenant_id,
                MagicLinkToken.user_id == user_id,
                MagicLinkToken.consumed_at.is_not(None),
                MagicLinkToken.callback_consumed_at.is_(None),
                MagicLinkToken.expires_at > now,
            )
        )
        .values(callback_consumed_at=now)
    )
    if updated.rowcount != 1:
        row = db.get(MagicLinkToken, token_id)
        if row is None or row.purpose != INVITE_ACCEPT_PURPOSE:
            raise EntityNotFoundError("Invite token not found.")
        if row.tenant_id != tenant_id or row.user_id != user_id:
            raise EntityNotFoundError("Invite token does not match invite context.")
        if row.consumed_at is None:
            raise GoneError("Invite token has not been accepted.")
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            raise GoneError("Invite token has expired.")
        if row.callback_consumed_at is not None:
            raise GoneError("Invite state has already been consumed.")
        raise GoneError("Invite state is no longer valid.")

    row = db.get(MagicLinkToken, token_id)
    if row is None:
        raise EntityNotFoundError("Invite token not found.")
    return row


def consume_invite_token(db: Session, *, token: str) -> ConsumedInvite:
    token_hash = hash_magic_link_token(token)
    now = _utc_now()
    updated = db.execute(
        update(MagicLinkToken)
        .where(
            and_(
                MagicLinkToken.token_hash == token_hash,
                MagicLinkToken.purpose == INVITE_ACCEPT_PURPOSE,
                MagicLinkToken.consumed_at.is_(None),
                MagicLinkToken.expires_at > now,
            )
        )
        .values(consumed_at=now)
    )
    if updated.rowcount != 1:
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
        if row.consumed_at is not None:
            raise GoneError("Invite token has already been consumed.")
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            raise GoneError("Invite token has expired.")
        raise GoneError("Invite token is no longer valid.")

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

    user = db.get(User, row.user_id)
    if user is None:
        raise EntityNotFoundError("Invite user not found.")

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
    commit: bool = True,
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
        row.team_id = None
    row.user_id = user.id
    row.role = "admin" if user.role == "admin" else "user"
    row.tenant_id = user.tenant_id
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
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row
