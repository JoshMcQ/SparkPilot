"""Reconciler worker: polls EMR for run state and records terminal results."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from sparkpilot.audit import write_audit_event
from sparkpilot.aws_clients import EmrEksClient
from sparkpilot.config import get_settings
from sparkpilot.models import Environment, Run
from sparkpilot.services._helpers import TERMINAL_RUN_STATES, _as_utc, _now
from sparkpilot.services.diagnostics import _record_run_diagnostics_if_needed
from sparkpilot.services.finops import _record_usage_if_needed
from sparkpilot.services.preflight import (
    _build_preflight,
    _has_preflight_audit,
    _preflight_summary,
)
from sparkpilot.services.workers_common import _claim_runs, _release_run_claim

logger = logging.getLogger(__name__)

EMR_TO_PLATFORM_STATE = {
    "PENDING": "accepted",
    "SUBMITTED": "accepted",
    "RUNNING": "running",
    "COMPLETED": "succeeded",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
    "CANCEL_PENDING": "running",
}


def _emit_reconciler_preflight_diagnostic_if_missing(
    *,
    db: Session,
    run: Run,
    env: Environment,
    actor: str,
) -> None:
    if _has_preflight_audit(db, run.id):
        return
    spark_conf = {**(run.job.spark_conf_json or {}), **(run.spark_conf_overrides_json or {})}
    diagnostic = _build_preflight(env, run_id=run.id, spark_conf=spark_conf, db=db)
    write_audit_event(
        db,
        actor=actor,
        action="run.preflight_diagnostic",
        entity_type="run",
        entity_id=run.id,
        tenant_id=env.tenant_id,
        details={
            "ready": diagnostic["ready"],
            "summary": _preflight_summary(diagnostic["checks"], include_warnings=True),
            "environment_id": env.id,
        },
    )


def _mark_run_timed_out_if_needed(
    *,
    db: Session,
    run: Run,
    env: Environment,
    emr: EmrEksClient,
    actor: str,
) -> bool:
    if not run.started_at:
        return False
    elapsed = (_now() - _as_utc(run.started_at)).total_seconds()
    if elapsed <= run.timeout_seconds:
        return False

    run.cancellation_requested = True
    if run.emr_job_run_id:
        aws_request_id = emr.cancel_job_run(env, run)
        write_audit_event(
            db,
            actor=actor,
            action="run.timeout_cancel.dispatched",
            entity_type="run",
            entity_id=run.id,
            tenant_id=env.tenant_id,
            aws_request_id=aws_request_id,
        )
    run.state = "timed_out"
    run.error_message = "Run exceeded timeout_seconds."
    run.ended_at = _now()
    _record_usage_if_needed(db, run, env)
    _record_run_diagnostics_if_needed(db, run, env)
    write_audit_event(
        db,
        actor=actor,
        action="run.timed_out",
        entity_type="run",
        entity_id=run.id,
        tenant_id=env.tenant_id,
    )
    return True


def _dispatch_run_cancel_if_requested(
    *,
    db: Session,
    run: Run,
    env: Environment,
    emr: EmrEksClient,
    actor: str,
) -> None:
    if not (run.cancellation_requested and run.emr_job_run_id):
        return
    aws_request_id = emr.cancel_job_run(env, run)
    write_audit_event(
        db,
        actor=actor,
        action="run.cancel.dispatched",
        entity_type="run",
        entity_id=run.id,
        tenant_id=env.tenant_id,
        aws_request_id=aws_request_id,
    )


def _apply_reconciler_stale_overrides(
    *,
    run: Run,
    emr_state: str,
    mapped_state: str,
    error: str | None,
    settings: Any,
) -> tuple[str, str | None]:
    if not run.started_at:
        return mapped_state, error
    elapsed_minutes = (_now() - _as_utc(run.started_at)).total_seconds() / 60
    if emr_state == "SUBMITTED" and elapsed_minutes > settings.submitted_stale_minutes:
        return (
            "failed",
            (
                f"Run remained in EMR SUBMITTED for more than {settings.submitted_stale_minutes} minutes. "
                "Check IRSA/OIDC trust and pod scheduling events."
            ),
        )
    if mapped_state == "accepted" and elapsed_minutes > settings.accepted_stale_minutes:
        return (
            "failed",
            (
                f"Run remained in accepted state for more than {settings.accepted_stale_minutes} minutes. "
                "Check scheduler dispatch, EMR job state, and Kubernetes events."
            ),
        )
    return mapped_state, error


def _record_reconciled_run_state(
    *,
    db: Session,
    run: Run,
    env: Environment,
    actor: str,
    emr_state: str,
    mapped_state: str,
    error: str | None,
) -> None:
    if error:
        run.error_message = error
    run.state = mapped_state
    if mapped_state in TERMINAL_RUN_STATES:
        if not run.ended_at:
            run.ended_at = _now()
        _record_usage_if_needed(db, run, env)
        _record_run_diagnostics_if_needed(db, run, env)
    write_audit_event(
        db,
        actor=actor,
        action="run.reconciled",
        entity_type="run",
        entity_id=run.id,
        tenant_id=env.tenant_id,
        details={"emr_state": emr_state, "state": mapped_state},
    )


def process_reconciler_once(db: Session, *, actor: str = "worker:reconciler", limit: int = 20) -> int:
    emr = EmrEksClient()
    settings = get_settings()
    active_runs = _claim_runs(
        db,
        actor=actor,
        states=["accepted", "running"],
        limit=limit,
        order_by_column=Run.updated_at,
    )
    processed = 0
    for run in active_runs:
        env = run.environment
        try:
            with db.begin_nested():
                _emit_reconciler_preflight_diagnostic_if_missing(db=db, run=run, env=env, actor=actor)
                if _mark_run_timed_out_if_needed(db=db, run=run, env=env, emr=emr, actor=actor):
                    continue

                _dispatch_run_cancel_if_requested(db=db, run=run, env=env, emr=emr, actor=actor)
                emr_state, error = emr.describe_job_run(env, run)
                mapped_state = EMR_TO_PLATFORM_STATE.get(emr_state, "failed")
                mapped_state, error = _apply_reconciler_stale_overrides(
                    run=run,
                    emr_state=emr_state,
                    mapped_state=mapped_state,
                    error=error,
                    settings=settings,
                )
                _record_reconciled_run_state(
                    db=db,
                    run=run,
                    env=env,
                    actor=actor,
                    emr_state=emr_state,
                    mapped_state=mapped_state,
                    error=error,
                )
        except Exception:  # noqa: BLE001 — reconciler must process all runs; one failure must not block others
            logger.exception(
                "Reconciler error for run_id=%s environment_id=%s; skipping to next run.",
                run.id,
                env.id,
            )
        finally:
            _release_run_claim(run)
            processed += 1
    if processed:
        db.commit()
    return processed
