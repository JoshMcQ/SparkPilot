from __future__ import annotations

from datetime import UTC, datetime
import logging
import threading
import uuid

import httpx

from sparkpilot.config import get_settings

logger = logging.getLogger(__name__)


def _post_crm_webhook(url: str, payload: dict[str, str]) -> None:
    try:
        response = httpx.post(url, json=payload, timeout=5.0)
        if response.status_code >= 400:
            logger.warning(
                "CRM webhook returned HTTP %s for event_type=%s event_id=%s",
                response.status_code,
                payload.get("event_type"),
                payload.get("event_id"),
            )
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.warning(
            "CRM webhook delivery failed for event_type=%s event_id=%s: %s",
            payload.get("event_type"),
            payload.get("event_id"),
            exc,
        )


def emit_tenant_lifecycle_event(
    *,
    event_type: str,
    tenant_id: str,
    tenant_name: str,
    admin_email: str,
    actor_email: str,
) -> None:
    """Fire-and-forget tenant lifecycle webhook.

    Payload shape is intentionally stable across events:
    {
      "event_type": "...",
      "event_id": "uuid",
      "occurred_at": "iso8601",
      "tenant_id": "...",
      "tenant_name": "...",
      "admin_email": "...",
      "actor_email": "..."
    }
    """

    webhook_url = get_settings().crm_webhook_url.strip()
    if not webhook_url:
        return
    payload = {
        "event_type": event_type,
        "event_id": str(uuid.uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "admin_email": admin_email,
        "actor_email": actor_email,
    }
    threading.Thread(
        target=_post_crm_webhook,
        args=(webhook_url, payload),
        daemon=True,
        name="sparkpilot-crm-webhook",
    ).start()

