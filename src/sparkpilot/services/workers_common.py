"""Shared worker utilities: claim/release helpers and transient error detection."""

from datetime import timedelta
import uuid

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session, selectinload

from sparkpilot.models import ProvisioningOperation, Run
from sparkpilot.services._helpers import _now

WORKER_CLAIM_TTL_SECONDS = 1800


def _claim_cutoff_time():
    return _now() - timedelta(seconds=WORKER_CLAIM_TTL_SECONDS)


def _provisioning_claim_available(cutoff_time):
    return or_(
        ProvisioningOperation.worker_claim_token.is_(None),
        ProvisioningOperation.worker_claimed_at.is_(None),
        ProvisioningOperation.worker_claimed_at < cutoff_time,
    )


def _run_claim_available(cutoff_time):
    return or_(
        Run.worker_claim_token.is_(None),
        Run.worker_claimed_at.is_(None),
        Run.worker_claimed_at < cutoff_time,
    )


def _claim_provisioning_operations(
    db: Session,
    *,
    actor: str,
    provisioning_steps: list[str],
) -> list[ProvisioningOperation]:
    claim_token = f"{actor}:{uuid.uuid4().hex[:16]}"
    cutoff_time = _claim_cutoff_time()
    candidate_ids = [
        row[0]
        for row in db.execute(
            select(ProvisioningOperation.id)
            .where(
                and_(
                    ProvisioningOperation.state.in_(["queued", *provisioning_steps]),
                    _provisioning_claim_available(cutoff_time),
                )
            )
            .order_by(ProvisioningOperation.created_at.asc())
        ).all()
    ]
    claimed_ids: list[str] = []
    for op_id in candidate_ids:
        claimed = db.execute(
            update(ProvisioningOperation)
            .where(
                and_(
                    ProvisioningOperation.id == op_id,
                    ProvisioningOperation.state.in_(["queued", *provisioning_steps]),
                    _provisioning_claim_available(cutoff_time),
                )
            )
            .values(worker_claim_token=claim_token, worker_claimed_at=_now())
        )
        if claimed.rowcount == 1:
            claimed_ids.append(op_id)
    if not claimed_ids:
        return []
    return list(
        db.execute(
            select(ProvisioningOperation)
            .where(ProvisioningOperation.id.in_(claimed_ids))
            .options(selectinload(ProvisioningOperation.environment))
            .order_by(ProvisioningOperation.created_at.asc())
        ).scalars()
    )


def _claim_runs(
    db: Session,
    *,
    actor: str,
    states: list[str],
    limit: int,
    order_by_column,
) -> list[Run]:
    claim_token = f"{actor}:{uuid.uuid4().hex[:16]}"
    cutoff_time = _claim_cutoff_time()
    candidate_ids = [
        row[0]
        for row in db.execute(
            select(Run.id)
            .where(
                and_(
                    Run.state.in_(states),
                    _run_claim_available(cutoff_time),
                )
            )
            .order_by(order_by_column.asc())
            .limit(limit)
        ).all()
    ]
    claimed_ids: list[str] = []
    for run_id in candidate_ids:
        claimed = db.execute(
            update(Run)
            .where(
                and_(
                    Run.id == run_id,
                    Run.state.in_(states),
                    _run_claim_available(cutoff_time),
                )
            )
            .values(worker_claim_token=claim_token, worker_claimed_at=_now())
        )
        if claimed.rowcount == 1:
            claimed_ids.append(run_id)
    if not claimed_ids:
        return []
    return list(
        db.execute(
            select(Run)
            .where(Run.id.in_(claimed_ids))
            .options(selectinload(Run.job), selectinload(Run.environment))
            .order_by(order_by_column.asc())
        ).scalars()
    )


def _release_operation_claim(operation: ProvisioningOperation) -> None:
    operation.worker_claim_token = None
    operation.worker_claimed_at = None


def _release_run_claim(run: Run) -> None:
    run.worker_claim_token = None
    run.worker_claimed_at = None


# ---------------------------------------------------------------------------
# Transient dispatch error detection
# ---------------------------------------------------------------------------

TRANSIENT_DISPATCH_ERROR_CODES = {
    "Throttling",
    "ThrottlingException",
    "TooManyRequestsException",
    "ServiceUnavailableException",
    "InternalServerException",
    "RequestTimeout",
    "RequestTimeoutException",
    "ProvisionedThroughputExceededException",
}

TRANSIENT_DISPATCH_ERROR_CLASSNAMES = {
    "EndpointConnectionError",
    "ConnectTimeoutError",
    "ReadTimeoutError",
}

TRANSIENT_DISPATCH_ERROR_TOKENS = (
    "throttl",
    "rate exceeded",
    "too many requests",
    "timeout",
    "temporarily unavailable",
    "connection reset",
    "connection aborted",
)


def _extract_aws_error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error")
        if isinstance(error, dict):
            code = error.get("Code")
            if isinstance(code, str):
                return code
    return None


def _is_transient_dispatch_error(exc: Exception) -> bool:
    code = _extract_aws_error_code(exc)
    if code and code in TRANSIENT_DISPATCH_ERROR_CODES:
        return True
    if exc.__class__.__name__ in TRANSIENT_DISPATCH_ERROR_CLASSNAMES:
        return True
    message = str(exc).lower()
    return any(token in message for token in TRANSIENT_DISPATCH_ERROR_TOKENS)
