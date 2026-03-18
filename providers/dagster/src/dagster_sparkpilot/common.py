from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

TERMINAL_STATES = {"succeeded", "failed", "cancelled", "timed_out"}
SUCCESS_STATES = {"succeeded"}
FAILURE_STATES = {"failed", "cancelled", "timed_out"}


def parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def build_run_metadata(run: dict[str, Any]) -> dict[str, Any]:
    started_at = parse_iso8601(run.get("started_at"))
    ended_at = parse_iso8601(run.get("ended_at"))
    duration_seconds: int | None = None
    if started_at and ended_at:
        duration_seconds = max(0, int((ended_at - started_at).total_seconds()))
    return {
        "id": run.get("id"),
        "status": run.get("state"),
        "cost_usd_micros": run.get("effective_cost_usd_micros") or run.get("actual_cost_usd_micros"),
        "duration_seconds": duration_seconds,
        "log_url": run.get("driver_log_uri") or run.get("spark_ui_uri"),
        "run": run,
    }


def error_detail_from_json(payload: Any) -> str:
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return "Unknown error"

