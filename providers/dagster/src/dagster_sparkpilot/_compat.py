from __future__ import annotations

from dataclasses import dataclass
import logging
from types import SimpleNamespace
from typing import Any, Callable

class _LocalTestOpContext:
    """Minimal op execution context for local/unit tests.

    Always available (regardless of whether the real Dagster is installed).
    Use ``build_local_test_context`` in ``ops.py`` to construct one.
    """

    def __init__(self, *, op_config: dict[str, Any] | None = None, resources: Any = None) -> None:
        self.op_config = op_config or {}
        self.resources = resources or SimpleNamespace()
        self.log = logging.getLogger("dagster-sparkpilot.op")


_dagster_available = False
_build_op_context_fn: Any = None

try:
    from dagster import (  # type: ignore[assignment]
        AssetExecutionContext,
        Definitions,
        Failure,
        Field,
        In,
        InitResourceContext,
        Nothing,
        OpExecutionContext,
        Out,
        RetryRequested,
        asset,
        build_op_context,
        job,
        op,
        resource,
    )
    _dagster_available = True
    _build_op_context_fn = build_op_context
except (ImportError, ModuleNotFoundError):

    class Failure(Exception):
        """Fallback Dagster failure signal for local tests."""

        def __init__(self, description: str) -> None:
            super().__init__(description)
            self.description = description

    class RetryRequested(Exception):
        """Fallback Dagster retry signal for local tests."""

        def __init__(self, *, max_retries: int = 1, seconds_to_wait: float = 0.0) -> None:
            super().__init__(
                f"RetryRequested(max_retries={max_retries}, seconds_to_wait={seconds_to_wait})"
            )
            self.max_retries = max_retries
            self.seconds_to_wait = seconds_to_wait

    class Field:
        def __init__(
            self,
            dagster_type: Any,
            *,
            is_required: bool = True,
            default_value: Any | None = None,
            description: str | None = None,
        ) -> None:
            self.dagster_type = dagster_type
            self.is_required = is_required
            self.default_value = default_value
            self.description = description

    class In:
        def __init__(self, dagster_type: Any = None, description: str | None = None) -> None:
            self.dagster_type = dagster_type
            self.description = description

    class Out:
        def __init__(self, dagster_type: Any = None, description: str | None = None) -> None:
            self.dagster_type = dagster_type
            self.description = description

    class Nothing:
        pass

    class OpExecutionContext:
        def __init__(self, *, op_config: dict[str, Any] | None = None, resources: Any = None) -> None:
            self.op_config = op_config or {}
            self.resources = resources or SimpleNamespace()
            self.log = logging.getLogger("dagster-sparkpilot.op")

    class AssetExecutionContext(OpExecutionContext):
        pass

    class InitResourceContext:
        def __init__(self, *, resource_config: dict[str, Any] | None = None) -> None:
            self.resource_config = resource_config or {}
            self.log = logging.getLogger("dagster-sparkpilot.resource")

    @dataclass(frozen=True)
    class Definitions:
        jobs: list[Any] | None = None
        assets: list[Any] | None = None
        resources: dict[str, Any] | None = None

    def _identity_decorator(*dargs: Any, **_dkwargs: Any) -> Callable[..., Any]:
        if dargs and callable(dargs[0]) and len(dargs) == 1:
            return dargs[0]

        def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return _wrap

    op = _identity_decorator
    asset = _identity_decorator
    job = _identity_decorator
    resource = _identity_decorator

