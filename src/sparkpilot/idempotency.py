import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from sparkpilot.models import IdempotencyRecord


def _fingerprint(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(slots=True)
class IdempotentResult:
    status_code: int
    body: dict[str, Any]
    replayed: bool


def with_idempotency(
    db: Session,
    *,
    scope: str,
    key: str,
    payload: Any,
    execute: Callable[[], tuple[int, dict[str, Any], str | None, str | None]],
) -> IdempotentResult:
    fingerprint = _fingerprint(payload)
    existing = db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key == key,
        )
    ).scalar_one_or_none()

    if existing:
        if existing.fingerprint != fingerprint:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency-Key already used with a different request body.",
            )
        return IdempotentResult(
            status_code=existing.status_code,
            body=json.loads(existing.response_json),
            replayed=True,
        )

    status_code_value, body, resource_type, resource_id = execute()
    record = IdempotencyRecord(
        scope=scope,
        key=key,
        fingerprint=fingerprint,
        response_json=json.dumps(body, default=str),
        status_code=status_code_value,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    db.add(record)
    db.commit()
    return IdempotentResult(status_code=status_code_value, body=body, replayed=False)

