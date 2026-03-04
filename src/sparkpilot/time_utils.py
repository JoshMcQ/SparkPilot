"""Shared time utilities, kept here to avoid circular imports."""

from datetime import UTC, datetime


def _as_utc(value: datetime) -> datetime:
    """Return *value* as a timezone-aware UTC datetime."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
