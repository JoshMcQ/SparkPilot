from typing import Any

from sqlalchemy.orm import Session

from sparkpilot.models import AuditEvent


def write_audit_event(
    db: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    tenant_id: str | None = None,
    source_ip: str | None = None,
    details: dict[str, Any] | None = None,
    aws_request_id: str | None = None,
    cloudtrail_event_id: str | None = None,
) -> None:
    event = AuditEvent(
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        source_ip=source_ip,
        entity_type=entity_type,
        entity_id=entity_id,
        details_json=details or {},
        aws_request_id=aws_request_id,
        cloudtrail_event_id=cloudtrail_event_id,
    )
    db.add(event)

