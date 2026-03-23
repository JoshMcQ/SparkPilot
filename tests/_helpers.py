"""Shared test helpers importable by all test modules."""
from __future__ import annotations

import os

import pytest


def live_env_required(name: str) -> str:
    """Return env var value or skip test if missing."""
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"Live integration disabled/missing env: {name}")
    return value
