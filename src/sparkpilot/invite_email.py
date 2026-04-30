"""Tenant invite email delivery through Resend."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import logging
from typing import Literal

import httpx

from sparkpilot.config import get_settings
from sparkpilot.exceptions import SparkPilotError

logger = logging.getLogger(__name__)

RESEND_EMAILS_URL = "https://api.resend.com/emails"


class InviteEmailConfigurationError(SparkPilotError):
    """Invite email delivery is not configured."""

    def __init__(self, detail: str = "Invite email delivery is not configured.") -> None:
        super().__init__(detail, status_code=503)


class InviteEmailDeliveryError(SparkPilotError):
    """Invite email delivery failed at the email provider."""

    def __init__(self, detail: str = "Invite email delivery failed.") -> None:
        super().__init__(detail, status_code=502)


@dataclass(frozen=True)
class InviteEmailDelivery:
    provider: Literal["resend"]
    recipient_email: str
    provider_message_id: str | None


def _invite_email_subject(tenant_name: str) -> str:
    return f"SparkPilot invite for {tenant_name}"


def _invite_email_text(*, tenant_name: str, invite_url: str, ttl_hours: int) -> str:
    return (
        f"You have been invited to administer {tenant_name} in SparkPilot.\n\n"
        f"Accept the invite: {invite_url}\n\n"
        f"This link expires in {ttl_hours} hours. If you were not expecting this "
        "invite, ignore this email."
    )


def _invite_email_html(*, tenant_name: str, invite_url: str, ttl_hours: int) -> str:
    safe_tenant_name = escape(tenant_name)
    safe_invite_url = escape(invite_url, quote=True)
    return (
        "<p>You have been invited to administer "
        f"<strong>{safe_tenant_name}</strong> in SparkPilot.</p>"
        f'<p><a href="{safe_invite_url}">Accept invite</a></p>'
        f"<p>This link expires in {ttl_hours} hours. If you were not expecting "
        "this invite, ignore this email.</p>"
    )


def send_invite_email(
    *,
    recipient_email: str,
    tenant_name: str,
    invite_url: str,
    tenant_id: str,
    user_id: str,
    ttl_hours: int,
    idempotency_key: str,
) -> InviteEmailDelivery:
    """Send a tenant admin invite email.

    The invite URL is intentionally accepted only as an argument and never logged.
    """

    settings = get_settings()
    api_key = settings.resend_api_key.strip()
    from_email = settings.invite_email_from.strip()
    reply_to = settings.invite_email_reply_to.strip()
    if not api_key:
        raise InviteEmailConfigurationError("SPARKPILOT_RESEND_API_KEY is not configured.")
    if not from_email:
        raise InviteEmailConfigurationError(
            "SPARKPILOT_INVITE_EMAIL_FROM is not configured."
        )

    payload: dict[str, object] = {
        "from": from_email,
        "to": [recipient_email],
        "subject": _invite_email_subject(tenant_name),
        "text": _invite_email_text(
            tenant_name=tenant_name,
            invite_url=invite_url,
            ttl_hours=ttl_hours,
        ),
        "html": _invite_email_html(
            tenant_name=tenant_name,
            invite_url=invite_url,
            ttl_hours=ttl_hours,
        ),
        "tags": [
            {"name": "tenant_id", "value": tenant_id},
            {"name": "user_id", "value": user_id},
            {"name": "purpose", "value": "invite_accept"},
        ],
    }
    if reply_to:
        payload["reply_to"] = reply_to

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Idempotency-Key": idempotency_key[:256],
    }
    try:
        response = httpx.post(
            RESEND_EMAILS_URL,
            json=payload,
            headers=headers,
            timeout=settings.invite_email_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise InviteEmailDeliveryError("Resend invite email request failed.") from exc

    if response.status_code >= 400:
        logger.warning(
            "Resend invite email returned HTTP %s for tenant_id=%s user_id=%s",
            response.status_code,
            tenant_id,
            user_id,
        )
        raise InviteEmailDeliveryError("Resend invite email request was rejected.")

    provider_message_id: str | None = None
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        raw_id = body.get("id")
        if isinstance(raw_id, str) and raw_id.strip():
            provider_message_id = raw_id.strip()

    logger.info(
        "Invite email sent provider=resend tenant_id=%s user_id=%s provider_message_id=%s",
        tenant_id,
        user_id,
        provider_message_id,
    )
    return InviteEmailDelivery(
        provider="resend",
        recipient_email=recipient_email,
        provider_message_id=provider_message_id,
    )
