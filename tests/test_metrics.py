"""Tests for src/sparkpilot/metrics.py (Issue #71)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from sparkpilot.db import Base
from sparkpilot.metrics import (
    budget_guardrail_trigger_frequency,
    collect_all_kpis,
    dispatch_success_rate,
    preflight_outcome_rates,
    queue_to_running_latency_p50_p95_seconds,
    terminal_outcome_distribution,
)
from sparkpilot.models import AuditEvent, Run


# ---------------------------------------------------------------------------
# In-memory SQLite session fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


def _now() -> datetime:
    return datetime.now(UTC)


def _audit(
    *,
    action: str,
    created_at: datetime | None = None,
) -> AuditEvent:
    return AuditEvent(
        actor="test-actor",
        action=action,
        entity_type="run",
        entity_id="run-1",
        created_at=created_at or _now(),
    )


def _run(
    *,
    state: str,
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> Run:
    import uuid

    return Run(
        job_id="job-1",
        environment_id="env-1",
        state=state,
        attempt=1,
        idempotency_key=str(uuid.uuid4()),
        requested_resources_json={},
        args_overrides_json=[],
        spark_conf_overrides_json={},
        timeout_seconds=3600,
        cancellation_requested=False,
        created_at=created_at or _now(),
        updated_at=_now(),
        started_at=started_at,
        ended_at=ended_at,
    )


def test_collect_all_kpis_returns_correct_structure(db: Session) -> None:
    result = collect_all_kpis(db)

    assert "preflight_outcome_rates" in result
    assert "dispatch_success_rate" in result
    assert "queue_to_running_latency" in result
    assert "budget_guardrail_triggers" in result
    assert "terminal_outcome_distribution" in result

    por = result["preflight_outcome_rates"]
    assert "total_evaluated" in por
    assert "preflight_pass_count" in por
    assert "preflight_block_count" in por
    assert "preflight_pass_rate_pct" in por
    assert "preflight_block_rate_pct" in por
    assert por["total_evaluated"] == 0
    assert por["preflight_pass_rate_pct"] == 0

    dsr = result["dispatch_success_rate"]
    assert "total_runs" in dsr
    assert "succeeded" in dsr
    assert "failed" in dsr
    assert "success_rate_pct" in dsr
    assert dsr["total_runs"] == 0

    lat = result["queue_to_running_latency"]
    assert lat["p50_seconds"] is None
    assert lat["p95_seconds"] is None
    assert lat["sample_count"] == 0

    bgt = result["budget_guardrail_triggers"]
    assert "budget_block_count" in bgt
    assert "budget_warn_count" in bgt
    assert bgt["budget_block_count"] == 0

    tod = result["terminal_outcome_distribution"]
    assert "succeeded" in tod
    assert "failed" in tod
    assert "cancelled" in tod
    assert "timed_out" in tod


# ---------------------------------------------------------------------------
# test_preflight_outcome_rates_counts_audit_events
# ---------------------------------------------------------------------------


def test_preflight_outcome_rates_counts_audit_events(db: Session) -> None:
    since = _now() - timedelta(hours=1)

    # 3 passed, 1 failed, 1 retry_scheduled
    for _ in range(3):
        db.add(_audit(action="run.preflight_passed"))
    db.add(_audit(action="run.preflight_failed"))
    db.add(_audit(action="run.dispatch_retry_scheduled"))
    # One event outside the window
    db.add(_audit(action="run.preflight_passed", created_at=_now() - timedelta(days=60)))
    db.commit()

    result = preflight_outcome_rates(db, since=since)

    assert result["total_evaluated"] == 5
    assert result["preflight_pass_count"] == 3
    assert result["preflight_block_count"] == 1
    assert result["preflight_pass_rate_pct"] == 60.0
    assert result["preflight_block_rate_pct"] == 20.0


def test_dispatch_success_rate_counts_runs(db: Session) -> None:
    since = _now() - timedelta(hours=1)

    db.add(_run(state="succeeded"))
    db.add(_run(state="succeeded"))
    db.add(_run(state="failed"))
    db.add(_run(state="queued"))
    # Outside window
    db.add(_run(state="succeeded", created_at=_now() - timedelta(days=60)))
    db.commit()

    result = dispatch_success_rate(db, since=since)

    assert result["total_runs"] == 4
    assert result["succeeded"] == 2
    assert result["failed"] == 1
    assert result["success_rate_pct"] == 50.0


def test_queue_to_running_latency_computes_percentiles(db: Session) -> None:
    since = _now() - timedelta(hours=1)
    base = _now() - timedelta(minutes=30)

    for i in range(10):
        created = base
        started = base + timedelta(seconds=i * 10)
        db.add(_run(state="succeeded", created_at=created, started_at=started))
    db.commit()

    result = queue_to_running_latency_p50_p95_seconds(db, since=since)

    assert result["sample_count"] == 10
    assert result["p50_seconds"] is not None
    assert result["p95_seconds"] is not None
    assert result["p95_seconds"] >= result["p50_seconds"]


def test_budget_guardrail_trigger_frequency_counts_events(db: Session) -> None:
    since = _now() - timedelta(hours=1)

    db.add(_audit(action="run.budget_blocked"))
    db.add(_audit(action="run.budget_blocked"))
    db.add(_audit(action="run.budget_warned"))
    db.commit()

    result = budget_guardrail_trigger_frequency(db, since=since)

    assert result["budget_block_count"] == 2
    assert result["budget_warn_count"] == 1


def test_terminal_outcome_distribution_counts_states(db: Session) -> None:
    since = _now() - timedelta(hours=1)

    db.add(_run(state="succeeded"))
    db.add(_run(state="succeeded"))
    db.add(_run(state="failed"))
    db.add(_run(state="cancelled"))
    db.add(_run(state="timed_out"))
    db.commit()

    result = terminal_outcome_distribution(db, since=since)

    assert result["succeeded"] == 2
    assert result["failed"] == 1
    assert result["cancelled"] == 1
    assert result["timed_out"] == 1
