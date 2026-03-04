"""Scheduler worker: dispatches queued runs to EMR on EKS."""

import logging
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from sparkpilot.audit import write_audit_event
from sparkpilot.aws_clients import EmrEksClient
from sparkpilot.models import Environment, Run
from sparkpilot.services._helpers import _now
from sparkpilot.services.preflight import _build_preflight_cached, _preflight_summary
from sparkpilot.services.workers_common import (
    _claim_runs,
    _is_transient_dispatch_error,
    _release_run_claim,
)

logger = logging.getLogger(__name__)


def _log_dispatch_failure(run: Run, env: Environment, exc: Exception) -> None:
    if isinstance(exc, (ClientError, BotoCoreError)):
        logger.exception(
            "AWS dispatch error for run_id=%s environment_id=%s attempt=%s error_type=%s",
            run.id,
            env.id,
            run.attempt,
            type(exc).__name__,
        )
        return
    logger.exception(
        "Unexpected dispatch error for run_id=%s environment_id=%s attempt=%s error_type=%s",
        run.id,
        env.id,
        run.attempt,
        type(exc).__name__,
    )


def _handle_dispatch_failure(
    db: Session,
    *,
    actor: str,
    run: Run,
    env: Environment,
    job: Any,
    exc: Exception,
) -> None:
    _log_dispatch_failure(run, env, exc)
    transient = _is_transient_dispatch_error(exc)
    if transient and run.attempt < job.retry_max_attempts:
        previous_attempt = run.attempt
        run.attempt += 1
        run.state = "queued"
        run.error_message = (
            f"Transient dispatch failure on attempt {previous_attempt} of {job.retry_max_attempts}: {exc}. "
            f"Retry scheduled as attempt {run.attempt}."
        )
        write_audit_event(
            db,
            actor=actor,
            action="run.dispatch_retry_scheduled",
            entity_type="run",
            entity_id=run.id,
            tenant_id=env.tenant_id,
            details={
                "error": str(exc),
                "error_type": type(exc).__name__,
                "attempt": run.attempt,
                "max_attempts": job.retry_max_attempts,
            },
        )
        return

    run.state = "failed"
    run.error_message = str(exc) if isinstance(exc, (ClientError, BotoCoreError)) else f"[{type(exc).__name__}] {exc}"
    run.ended_at = _now()
    write_audit_event(
        db,
        actor=actor,
        action="run.dispatch_failed",
        entity_type="run",
        entity_id=run.id,
        tenant_id=env.tenant_id,
        details={"error": str(exc), "error_type": type(exc).__name__, "transient": transient},
    )


def process_scheduler_once(db: Session, *, actor: str = "worker:scheduler", limit: int = 20) -> int:
    emr = EmrEksClient()
    queued_runs = _claim_runs(
        db,
        actor=actor,
        states=["queued"],
        limit=limit,
        order_by_column=Run.created_at,
    )
    processed = 0
    for run in queued_runs:
        job = run.job
        env = run.environment
        try:
            spark_conf = {**(job.spark_conf_json or {}), **(run.spark_conf_overrides_json or {})}
            if run.cancellation_requested:
                run.state = "cancelled"
                run.ended_at = _now()
                continue

            preflight = _build_preflight_cached(env, run_id=run.id, spark_conf=spark_conf, db=db)
            if not preflight["ready"]:
                run.state = "failed"
                run.error_message = f"Preflight failed: {_preflight_summary(preflight['checks'])}"
                run.ended_at = _now()
                write_audit_event(
                    db,
                    actor=actor,
                    action="run.preflight_failed",
                    entity_type="run",
                    entity_id=run.id,
                    tenant_id=env.tenant_id,
                    details={
                        "ready": False,
                        "summary": _preflight_summary(preflight["checks"], include_warnings=True),
                        "environment_id": env.id,
                    },
                )
                continue

            write_audit_event(
                db,
                actor=actor,
                action="run.preflight_passed",
                entity_type="run",
                entity_id=run.id,
                tenant_id=env.tenant_id,
                details={
                    "ready": True,
                    "summary": _preflight_summary(preflight["checks"], include_warnings=True),
                    "environment_id": env.id,
                },
            )

            run.state = "dispatching"
            dispatch = emr.start_job_run(env, job, run)
            run.state = "accepted"
            run.started_at = _now()
            run.emr_job_run_id = dispatch.emr_job_run_id
            run.log_group = dispatch.log_group
            run.log_stream_prefix = dispatch.log_stream_prefix
            run.driver_log_uri = dispatch.driver_log_uri
            run.spark_ui_uri = dispatch.spark_ui_uri
            write_audit_event(
                db,
                actor=actor,
                action="run.dispatched",
                entity_type="run",
                entity_id=run.id,
                tenant_id=env.tenant_id,
                aws_request_id=dispatch.aws_request_id,
                details={"emr_job_run_id": run.emr_job_run_id},
            )
        except Exception as exc:  # noqa: BLE001 — scheduler must handle all errors per-run, not crash the batch
            _handle_dispatch_failure(
                db,
                actor=actor,
                run=run,
                env=env,
                job=job,
                exc=exc,
            )
        finally:
            _release_run_claim(run)
            processed += 1
    if processed:
        db.commit()
    return processed
