"""Run diagnostic pattern matching and CloudWatch log analysis."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sparkpilot.aws_clients import CloudWatchLogsProxy
from sparkpilot.models import Environment, Run, RunDiagnostic
from sparkpilot.services._helpers import _require_run

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Diagnostic pattern catalogue
# ---------------------------------------------------------------------------

DIAGNOSTIC_PATTERNS: list[dict[str, Any]] = [
    {
        "category": "oom",
        "tokens": ("outofmemoryerror", "java heap space", "container killed by yarn for exceeding memory limits"),
        "description": "Spark driver or executor ran out of memory.",
        "remediation": "Increase driver/executor memory, reduce partition size, or tune shuffle/storage settings.",
    },
    {
        "category": "shuffle_fetch_failure",
        "tokens": ("fetchfailed", "metadata fetch failed", "shuffle block fetch failed"),
        "description": "Shuffle fetch failure detected.",
        "remediation": "Check executor churn/network instability and increase shuffle retry/timeout settings.",
    },
    {
        "category": "s3_access_denied",
        "tokens": ("accessdenied", "403 forbidden", "amazon s3", "s3a"),
        "description": "S3 access denied during Spark run.",
        "remediation": "Verify execution role S3 permissions and bucket policy for input/output prefixes.",
    },
    {
        "category": "schema_mismatch",
        "tokens": ("analysisexception", "cannot resolve", "schema mismatch"),
        "description": "Schema mismatch or unresolved column detected.",
        "remediation": "Validate input schema evolution and update query/transform logic accordingly.",
    },
    {
        "category": "timeout",
        "tokens": ("timed out", "timeout", "run exceeded timeout_seconds"),
        "description": "Run exceeded timeout or stalled beyond configured threshold.",
        "remediation": "Increase timeout or reduce workload size/resources per run.",
    },
    {
        "category": "spot_interruption",
        "tokens": ("spot interruption", "termination notice", "executor lost", "node was drained"),
        "description": "Spot interruption or eviction pattern detected.",
        "remediation": "Increase Spot diversification and retry/fault-tolerance configuration for executors.",
    },
]


# ---------------------------------------------------------------------------
# Log line analysis
# ---------------------------------------------------------------------------

def _first_matching_line(lines: list[str], tokens: tuple[str, ...]) -> str | None:
    lowered_tokens = tuple(token.lower() for token in tokens)
    for line in lines:
        text = line.lower()
        if any(token in text for token in lowered_tokens):
            return line[:500]
    return None


def _diagnostics_from_log_lines(lines: list[str], *, error_message: str | None = None) -> list[dict[str, str | None]]:
    diagnostics: list[dict[str, str | None]] = []
    seen_categories: set[str] = set()
    all_lines = list(lines)
    if error_message:
        all_lines.append(error_message)

    for pattern in DIAGNOSTIC_PATTERNS:
        category = str(pattern["category"])
        tokens = tuple(str(token) for token in pattern["tokens"])
        snippet = _first_matching_line(all_lines, tokens)
        if snippet is None:
            continue
        if category in seen_categories:
            continue
        seen_categories.add(category)
        diagnostics.append(
            {
                "category": category,
                "description": str(pattern["description"]),
                "remediation": str(pattern["remediation"]),
                "log_snippet": snippet,
            }
        )

    if not diagnostics and error_message:
        diagnostics.append(
            {
                "category": "unknown_failure",
                "description": "Run failed but no known diagnostic pattern matched.",
                "remediation": "Review full driver/executor logs and EMR job details for root cause.",
                "log_snippet": error_message[:500],
            }
        )
    return diagnostics


# ---------------------------------------------------------------------------
# Diagnostic recording
# ---------------------------------------------------------------------------

def _record_run_diagnostics_if_needed(db: Session, run: Run, env: Environment) -> None:
    if run.state not in {"failed", "timed_out", "cancelled"}:
        return
    existing = db.execute(select(RunDiagnostic.id).where(RunDiagnostic.run_id == run.id)).first()
    if existing is not None:
        return

    lines: list[str] = []
    log_fetch_error: str | None = None
    if run.log_group and run.log_stream_prefix:
        try:
            lines = CloudWatchLogsProxy().fetch_lines(
                role_arn=env.customer_role_arn,
                region=env.region,
                log_group=run.log_group,
                log_stream_prefix=run.log_stream_prefix,
                limit=500,
            )
        except Exception as exc:  # noqa: BLE001 - diagnostics must degrade gracefully on any log-fetch failure
            logger.exception(
                "Failed to fetch CloudWatch logs for diagnostics run_id=%s env_id=%s error_type=%s",
                run.id,
                env.id,
                type(exc).__name__,
            )
            log_fetch_error = str(exc)
            lines = []
    diagnostics = _diagnostics_from_log_lines(lines, error_message=run.error_message)
    if log_fetch_error:
        diagnostics.insert(
            0,
            {
                "category": "log_collection_error",
                "description": "CloudWatch diagnostic log collection failed.",
                "remediation": (
                    "Verify customer role permissions for CloudWatch Logs and inspect worker logs "
                    "for fetch errors."
                ),
                "log_snippet": log_fetch_error[:500],
            },
        )
    for item in diagnostics:
        db.add(
            RunDiagnostic(
                run_id=run.id,
                category=str(item["category"]),
                description=str(item["description"]),
                remediation=str(item["remediation"]),
                log_snippet=str(item["log_snippet"]) if item.get("log_snippet") is not None else None,
            )
        )


def list_run_diagnostics(db: Session, run_id: str) -> list[RunDiagnostic]:
    _require_run(db, run_id)
    return list(
        db.execute(
            select(RunDiagnostic)
            .where(RunDiagnostic.run_id == run_id)
            .order_by(RunDiagnostic.created_at.asc())
        ).scalars()
    )
