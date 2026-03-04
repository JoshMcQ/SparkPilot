import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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


def _load_idempotency_record(db: Session, *, scope: str, key: str) -> IdempotencyRecord | None:
    return db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key == key,
        )
    ).scalar_one_or_none()


def _replay_or_conflict(existing: IdempotencyRecord, *, fingerprint: str) -> IdempotentResult:
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


def with_idempotency(
    db: Session,
    *,
    scope: str,
    key: str,
    payload: Any,
    execute: Callable[[], tuple[int, dict[str, Any], str | None, str | None]],
) -> IdempotentResult:
    fingerprint = _fingerprint(payload)
    existing = _load_idempotency_record(db, scope=scope, key=key)
    if existing:
        return _replay_or_conflict(existing, fingerprint=fingerprint)

    reservation = IdempotencyRecord(
        scope=scope,
        key=key,
        fingerprint=fingerprint,
        # Reservation row is updated with final result after execute() succeeds.
        response_json="{}",
        status_code=0,
        resource_type=None,
        resource_id=None,
    )
    db.add(reservation)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = _load_idempotency_record(db, scope=scope, key=key)
        if existing is None:
            raise
        return _replay_or_conflict(existing, fingerprint=fingerprint)

    try:
        status_code_value, body, resource_type, resource_id = execute()
        reservation.response_json = json.dumps(body, default=str)
        reservation.status_code = status_code_value
        reservation.resource_type = resource_type
        reservation.resource_id = resource_id
        db.commit()
    except BaseException:
        # BaseException (not Exception) so rollback runs on KeyboardInterrupt too.
        db.rollback()
        raise
    return IdempotentResult(status_code=status_code_value, body=body, replayed=False)
