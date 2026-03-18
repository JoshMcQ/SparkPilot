from __future__ import annotations

from dagster_sparkpilot._compat import Failure, RetryRequested

TRANSIENT_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class SparkPilotError(RuntimeError):
    """Base SparkPilot orchestration error."""


class SparkPilotTransientError(SparkPilotError):
    """Retryable error for transport instability and transient backend states."""


class SparkPilotPermanentError(SparkPilotError):
    """Non-retryable configuration, authz/authn, or validation error."""


class SparkPilotRunFailedError(SparkPilotPermanentError):
    """Run reached a terminal failure state."""


def is_transient_status_code(status_code: int) -> bool:
    return status_code in TRANSIENT_STATUS_CODES


def map_sparkpilot_error_to_dagster(
    exc: SparkPilotError,
    *,
    retry_count: int = 3,
    retry_backoff_seconds: float = 5.0,
) -> Exception:
    if isinstance(exc, SparkPilotTransientError):
        return RetryRequested(max_retries=retry_count, seconds_to_wait=retry_backoff_seconds)
    return Failure(description=str(exc))

