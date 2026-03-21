"""Shared exception-formatting helpers for consistent operational error messaging."""

from __future__ import annotations


def error_type(exc: Exception) -> str:
    return exc.__class__.__name__


def error_message(exc: Exception, *, include_type: bool = False) -> str:
    message = str(exc)
    if include_type:
        return f"[{error_type(exc)}] {message}"
    return message


def error_details(exc: Exception, *, include_type: bool = True) -> dict[str, str]:
    details = {"error": error_message(exc, include_type=False)}
    if include_type:
        details["error_type"] = error_type(exc)
    return details
