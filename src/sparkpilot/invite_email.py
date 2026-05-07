"""Tenant invite email delivery through Resend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
import logging
import random
import time
from typing import Literal

import httpx

from sparkpilot.config import get_settings
from sparkpilot.exceptions import SparkPilotError

logger = logging.getLogger(__name__)

RESEND_EMAILS_URL = "https://api.resend.com/emails"
RESEND_SEND_MAX_ATTEMPTS = 3
RESEND_RETRY_BASE_SECONDS = 0.25
RESEND_RETRY_JITTER_SECONDS = 0.1


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
    status: Literal["sent", "failed"]
    provider_message_id: str | None
    failure_detail: str | None = None


@dataclass(frozen=True)
class ContactEmailDelivery:
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


def _resend_retry_delay_seconds(attempt: int) -> float:
    return (RESEND_RETRY_BASE_SECONDS * (2 ** (attempt - 1))) + random.uniform(
        0,
        RESEND_RETRY_JITTER_SECONDS,
    )


def _configured_resend_email_settings() -> tuple[str, str, str, float]:
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
    return api_key, from_email, reply_to, settings.invite_email_timeout_seconds


def _post_resend_email(
    *,
    payload: dict[str, object],
    idempotency_key: str,
    log_context: str,
) -> str | None:
    api_key, _from_email, _reply_to, timeout_seconds = _configured_resend_email_settings()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Idempotency-Key": idempotency_key[:256],
    }
    response: httpx.Response | None = None
    for attempt in range(1, RESEND_SEND_MAX_ATTEMPTS + 1):
        try:
            response = httpx.post(
                RESEND_EMAILS_URL,
                json=payload,
                headers=headers,
                timeout=timeout_seconds,
            )
        except httpx.HTTPError as exc:
            if attempt >= RESEND_SEND_MAX_ATTEMPTS:
                raise InviteEmailDeliveryError(
                    "Resend email request failed."
                ) from exc
            delay = _resend_retry_delay_seconds(attempt)
            logger.warning(
                "Resend email transport failure attempt=%s/%s context=%s error_type=%s retry_delay_seconds=%.3f",
                attempt,
                RESEND_SEND_MAX_ATTEMPTS,
                log_context,
                exc.__class__.__name__,
                delay,
            )
            time.sleep(delay)
            continue
        if response.status_code < 500:
            break
        if attempt >= RESEND_SEND_MAX_ATTEMPTS:
            break
        delay = _resend_retry_delay_seconds(attempt)
        logger.warning(
            "Resend email transient HTTP %s attempt=%s/%s context=%s retry_delay_seconds=%.3f",
            response.status_code,
            attempt,
            RESEND_SEND_MAX_ATTEMPTS,
            log_context,
            delay,
        )
        time.sleep(delay)

    if response is None:
        raise InviteEmailDeliveryError("Resend email request failed.")

    if response.status_code >= 400:
        logger.warning(
            "Resend email returned HTTP %s context=%s",
            response.status_code,
            log_context,
        )
        raise InviteEmailDeliveryError("Resend email request was rejected.")

    provider_message_id: str | None = None
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        raw_id = body.get("id")
        if isinstance(raw_id, str) and raw_id.strip():
            provider_message_id = raw_id.strip()
    return provider_message_id


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

    _api_key, from_email, reply_to, _timeout_seconds = _configured_resend_email_settings()

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

    provider_message_id = _post_resend_email(
        payload=payload,
        idempotency_key=idempotency_key,
        log_context=f"purpose=invite_accept tenant_id={tenant_id} user_id={user_id}",
    )

    logger.info(
        "Invite email sent provider=resend tenant_id=%s user_id=%s provider_message_id=%s",
        tenant_id,
        user_id,
        provider_message_id,
    )
    return InviteEmailDelivery(
        provider="resend",
        recipient_email=recipient_email,
        status="sent",
        provider_message_id=provider_message_id,
    )


def _contact_request_subject(*, name: str, company: str | None) -> str:
    normalized_name = name.strip() or "Unknown"
    normalized_company = (company or "").strip()
    if normalized_company:
        return f"SparkPilot request from {normalized_name} at {normalized_company}"
    return f"SparkPilot request from {normalized_name}"


def _contact_request_text(
    *,
    name: str,
    email: str,
    company: str | None,
    use_case: str | None,
    message: str | None,
    source_url: str | None,
    submitted_at: datetime,
    request_id: str,
) -> str:
    return "\n".join(
        [
            "New SparkPilot request",
            "",
            f"Name: {name}",
            f"Email: {email}",
            f"Company: {(company or '').strip() or '-'}",
            f"Use case: {(use_case or '').strip() or '-'}",
            f"Source: {(source_url or '').strip() or '-'}",
            f"Submitted: {submitted_at.isoformat()}",
            f"Request ID: {request_id}",
            "",
            "Message:",
            (message or "").strip() or "-",
        ]
    )


def _contact_request_html(
    *,
    name: str,
    email: str,
    company: str | None,
    use_case: str | None,
    message: str | None,
    source_url: str | None,
    submitted_at: datetime,
    request_id: str,
) -> str:
    rows = [
        ("Name", name),
        ("Email", email),
        ("Company", (company or "").strip() or "-"),
        ("Use case", (use_case or "").strip() or "-"),
        ("Source", (source_url or "").strip() or "-"),
        ("Submitted", submitted_at.isoformat()),
        ("Request ID", request_id),
    ]
    rendered_rows = "".join(
        f"<tr><th align=\"left\">{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in rows
    )
    rendered_message = escape((message or "").strip() or "-").replace("\n", "<br>")
    return (
        "<p>New SparkPilot request.</p>"
        f"<table>{rendered_rows}</table>"
        "<p><strong>Message</strong></p>"
        f"<p>{rendered_message}</p>"
    )


def send_contact_request_email(
    *,
    recipient_email: str,
    name: str,
    email: str,
    company: str | None,
    use_case: str | None,
    message: str | None,
    source_url: str | None,
    submitted_at: datetime,
    request_id: str,
    idempotency_key: str,
) -> ContactEmailDelivery:
    """Send an inbound request/pilot lead notification through Resend."""

    _api_key, from_email, _reply_to, _timeout_seconds = _configured_resend_email_settings()
    payload: dict[str, object] = {
        "from": from_email,
        "to": [recipient_email],
        "subject": _contact_request_subject(name=name, company=company),
        "text": _contact_request_text(
            name=name,
            email=email,
            company=company,
            use_case=use_case,
            message=message,
            source_url=source_url,
            submitted_at=submitted_at,
            request_id=request_id,
        ),
        "html": _contact_request_html(
            name=name,
            email=email,
            company=company,
            use_case=use_case,
            message=message,
            source_url=source_url,
            submitted_at=submitted_at,
            request_id=request_id,
        ),
        "reply_to": email,
        "tags": [
            {"name": "purpose", "value": "contact_request"},
            {"name": "request_id", "value": request_id[:256]},
        ],
    }

    provider_message_id = _post_resend_email(
        payload=payload,
        idempotency_key=idempotency_key,
        log_context=f"purpose=contact_request request_id={request_id}",
    )
    logger.info(
        "Contact request email sent provider=resend request_id=%s provider_message_id=%s",
        request_id,
        provider_message_id,
    )
    return ContactEmailDelivery(
        provider="resend",
        recipient_email=recipient_email,
        provider_message_id=provider_message_id,
    )
