"""SparkPilot operational KPI metrics collection and reporting."""
from __future__ import annotations
from datetime import datetime, UTC, timedelta
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from sparkpilot.models import Run, AuditEvent


def preflight_outcome_rates(db: Session, *, since: datetime | None = None) -> dict[str, Any]:
    """Returns preflight block/warn/pass rates over the given window."""
    if since is None:
        since = datetime.now(UTC) - timedelta(days=30)

    # Count audit events by action
    actions = ["run.preflight_passed", "run.preflight_failed", "run.dispatch_retry_scheduled"]
    result = {}
    for action in actions:
        count = db.query(func.count(AuditEvent.id)).filter(
            and_(AuditEvent.action == action, AuditEvent.created_at >= since)
        ).scalar() or 0
        result[action.replace("run.", "")] = count

    total = sum(result.values())
    return {
        "window_start": since.isoformat(),
        "window_end": datetime.now(UTC).isoformat(),
        "total_evaluated": total,
        "preflight_pass_count": result.get("preflight_passed", 0),
        "preflight_block_count": result.get("preflight_failed", 0),
        "preflight_pass_rate_pct": round(100 * result.get("preflight_passed", 0) / total, 1) if total else 0,
        "preflight_block_rate_pct": round(100 * result.get("preflight_failed", 0) / total, 1) if total else 0,
    }


def dispatch_success_rate(db: Session, *, since: datetime | None = None) -> dict[str, Any]:
    """Returns dispatch success/failure rates."""
    if since is None:
        since = datetime.now(UTC) - timedelta(days=30)

    total = db.query(func.count(Run.id)).filter(Run.created_at >= since).scalar() or 0
    succeeded = db.query(func.count(Run.id)).filter(
        and_(Run.created_at >= since, Run.state == "succeeded")
    ).scalar() or 0
    failed = db.query(func.count(Run.id)).filter(
        and_(Run.created_at >= since, Run.state == "failed")
    ).scalar() or 0

    return {
        "window_start": since.isoformat(),
        "window_end": datetime.now(UTC).isoformat(),
        "total_runs": total,
        "succeeded": succeeded,
        "failed": failed,
        "success_rate_pct": round(100 * succeeded / total, 1) if total else 0,
    }


def queue_to_running_latency_p50_p95_seconds(db: Session, *, since: datetime | None = None) -> dict[str, Any]:
    """Returns queue-to-running latency distribution."""
    if since is None:
        since = datetime.now(UTC) - timedelta(days=30)

    runs = db.query(Run.created_at, Run.started_at).filter(
        and_(Run.created_at >= since, Run.started_at.isnot(None))
    ).all()

    if not runs:
        return {"p50_seconds": None, "p95_seconds": None, "sample_count": 0}

    latencies = sorted([
        (r.started_at - r.created_at).total_seconds()
        for r in runs
        if r.started_at and r.created_at
    ])
    n = len(latencies)
    p50 = latencies[int(n * 0.50)] if latencies else None
    p95 = latencies[int(n * 0.95)] if latencies else None
    return {"p50_seconds": p50, "p95_seconds": p95, "sample_count": n}


def budget_guardrail_trigger_frequency(db: Session, *, since: datetime | None = None) -> dict[str, Any]:
    """Returns how often budget guardrails blocked or warned runs."""
    if since is None:
        since = datetime.now(UTC) - timedelta(days=30)

    budget_blocks = db.query(func.count(AuditEvent.id)).filter(
        and_(AuditEvent.action == "run.budget_blocked", AuditEvent.created_at >= since)
    ).scalar() or 0
    budget_warns = db.query(func.count(AuditEvent.id)).filter(
        and_(AuditEvent.action == "run.budget_warned", AuditEvent.created_at >= since)
    ).scalar() or 0

    return {
        "window_start": since.isoformat(),
        "budget_block_count": budget_blocks,
        "budget_warn_count": budget_warns,
    }


def terminal_outcome_distribution(db: Session, *, since: datetime | None = None) -> dict[str, Any]:
    """Returns terminal state distribution for completed runs."""
    if since is None:
        since = datetime.now(UTC) - timedelta(days=30)

    terminal_states = ["succeeded", "failed", "cancelled", "timed_out"]
    result = {}
    for state in terminal_states:
        count = db.query(func.count(Run.id)).filter(
            and_(Run.created_at >= since, Run.state == state)
        ).scalar() or 0
        result[state] = count

    return {
        "window_start": since.isoformat(),
        **result,
    }


def jwks_refresh_stats() -> dict[str, Any]:
    """Return JWKS refresh telemetry from the singleton OIDC verifier."""
    try:
        from sparkpilot.api import _oidc_verifier
        verifier = _oidc_verifier()
        return verifier.jwks_refresh_stats
    except Exception:
        return {"total": 0, "forced": 0, "throttled": 0}


def collect_all_kpis(db: Session, *, since: datetime | None = None) -> dict[str, Any]:
    """Collect all KPI metrics in one call."""
    return {
        "preflight_outcome_rates": preflight_outcome_rates(db, since=since),
        "dispatch_success_rate": dispatch_success_rate(db, since=since),
        "queue_to_running_latency": queue_to_running_latency_p50_p95_seconds(db, since=since),
        "budget_guardrail_triggers": budget_guardrail_trigger_frequency(db, since=since),
        "terminal_outcome_distribution": terminal_outcome_distribution(db, since=since),
        "jwks_refresh_stats": jwks_refresh_stats(),
    }
