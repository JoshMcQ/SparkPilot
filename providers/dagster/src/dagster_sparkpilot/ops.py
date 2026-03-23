from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from dagster_sparkpilot._compat import (
    Field,
    In,
    OpExecutionContext,
    Out,
    _LocalTestOpContext,
    _build_op_context_fn,
    op,
)
from dagster_sparkpilot.client import SparkPilotClient
from dagster_sparkpilot.common import TERMINAL_STATES, build_run_metadata, normalize_op_config
from dagster_sparkpilot.errors import SparkPilotError, map_sparkpilot_error_to_dagster


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' must be a non-empty string.")
    return value.strip()


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"'{key}' must be a string when provided.")
    candidate = value.strip()
    return candidate or None


def _optional_positive_int(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"'{key}' must be an integer > 0 when provided.")
    return value


def _optional_string_list(payload: Mapping[str, Any], key: str) -> list[str] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"'{key}' must be a list when provided.")
    parsed: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"'{key}' must be a list of strings.")
        parsed.append(item)
    return parsed


def _optional_dict_str_str(payload: Mapping[str, Any], key: str) -> dict[str, str] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"'{key}' must be an object when provided.")
    parsed: dict[str, str] = {}
    for item_key, item_value in value.items():
        if not isinstance(item_key, str) or not isinstance(item_value, str):
            raise ValueError(f"'{key}' keys and values must be strings.")
        parsed[item_key] = item_value
    return parsed


def _optional_requested_resources(payload: Mapping[str, Any], key: str) -> dict[str, int] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"'{key}' must be an object when provided.")
    required = {
        "driver_vcpu": 1,
        "driver_memory_gb": 1,
        "executor_vcpu": 1,
        "executor_memory_gb": 1,
        "executor_instances": 0,
    }
    parsed: dict[str, int] = {}
    for field_name, minimum in required.items():
        field_value = value.get(field_name)
        if not isinstance(field_value, int) or field_value < minimum:
            raise ValueError(f"'{key}.{field_name}' must be an integer >= {minimum}.")
        parsed[field_name] = field_value
    return parsed


def _resolve_sparkpilot_client(context: OpExecutionContext) -> SparkPilotClient:
    resources = getattr(context, "resources", None)
    sparkpilot_resource = None
    if resources is not None:
        sparkpilot_resource = getattr(resources, "sparkpilot", None)
    if sparkpilot_resource is None and isinstance(resources, Mapping):
        sparkpilot_resource = resources.get("sparkpilot")
    if sparkpilot_resource is None:
        raise ValueError(
            "SparkPilot Dagster resource is missing. Add resource key 'sparkpilot' to your job/defs."
        )
    if isinstance(sparkpilot_resource, SparkPilotClient) or _looks_like_sparkpilot_client(sparkpilot_resource):
        return sparkpilot_resource
    get_client = getattr(sparkpilot_resource, "get_client", None)
    if callable(get_client):
        client = get_client()
        if isinstance(client, SparkPilotClient) or _looks_like_sparkpilot_client(client):
            return client
    raise ValueError("Resource 'sparkpilot' must be SparkPilotClient or expose get_client().")


_REQUIRED_CLIENT_METHODS = ("submit_run", "get_run", "cancel_run", "wait_for_terminal_state")


def _looks_like_sparkpilot_client(candidate: Any) -> bool:
    missing = [m for m in _REQUIRED_CLIENT_METHODS if not callable(getattr(candidate, m, None))]
    if missing:
        raise ValueError(
            f"SparkPilot client object is missing required methods: {missing}. "
            "Ensure the resource exposes a fully-implemented SparkPilotClient."
        )
    return True


@dataclass(frozen=True)
class SubmitRunOpConfig:
    job_id: str
    golden_path: str | None = None
    args: list[str] | None = None
    spark_conf: dict[str, str] | None = None
    requested_resources: dict[str, int] | None = None
    run_timeout_seconds: int | None = None
    idempotency_key: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SubmitRunOpConfig":
        return cls(
            job_id=_required_string(payload, "job_id"),
            golden_path=_optional_string(payload, "golden_path"),
            args=_optional_string_list(payload, "args"),
            spark_conf=_optional_dict_str_str(payload, "spark_conf"),
            requested_resources=_optional_requested_resources(payload, "requested_resources"),
            run_timeout_seconds=_optional_positive_int(payload, "run_timeout_seconds"),
            idempotency_key=_optional_string(payload, "idempotency_key"),
        )

    def to_run_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.golden_path:
            payload["golden_path"] = self.golden_path
        if self.args is not None:
            payload["args"] = self.args
        if self.spark_conf is not None:
            payload["spark_conf"] = self.spark_conf
        if self.requested_resources is not None:
            payload["requested_resources"] = self.requested_resources
        if self.run_timeout_seconds is not None:
            payload["timeout_seconds"] = self.run_timeout_seconds
        return payload


@dataclass(frozen=True)
class WaitRunOpConfig:
    run_id: str | None = None
    poll_interval_seconds: int = 15
    timeout_seconds: int = 3600

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "WaitRunOpConfig":
        run_id = _optional_string(payload, "run_id")
        poll_interval_seconds = payload.get("poll_interval_seconds", 15)
        timeout_seconds = payload.get("timeout_seconds", 3600)
        if not isinstance(poll_interval_seconds, int) or poll_interval_seconds <= 0:
            raise ValueError("'poll_interval_seconds' must be an integer > 0.")
        if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise ValueError("'timeout_seconds' must be an integer > 0.")
        return cls(
            run_id=run_id,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )


@dataclass(frozen=True)
class CancelRunOpConfig:
    run_id: str | None = None
    idempotency_key: str | None = None
    wait_for_completion: bool = True
    poll_interval_seconds: int = 10
    timeout_seconds: int = 600

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CancelRunOpConfig":
        run_id = _optional_string(payload, "run_id")
        idempotency_key = _optional_string(payload, "idempotency_key")
        wait_for_completion = bool(payload.get("wait_for_completion", True))
        poll_interval_seconds = payload.get("poll_interval_seconds", 10)
        timeout_seconds = payload.get("timeout_seconds", 600)
        if not isinstance(poll_interval_seconds, int) or poll_interval_seconds <= 0:
            raise ValueError("'poll_interval_seconds' must be an integer > 0.")
        if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise ValueError("'timeout_seconds' must be an integer > 0.")
        return cls(
            run_id=run_id,
            idempotency_key=idempotency_key,
            wait_for_completion=wait_for_completion,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )


def _run_id_from_config_or_metadata(
    *,
    config_run_id: str | None,
    run_metadata: dict[str, Any] | None,
    config_key: str,
) -> str:
    if config_run_id:
        return config_run_id
    metadata = run_metadata or {}
    candidate = metadata.get("id")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    raise ValueError(f"'{config_key}' is required when no upstream run metadata with 'id' is provided.")


def submit_run_with_client(client: SparkPilotClient, config: SubmitRunOpConfig) -> dict[str, Any]:
    submitted = client.submit_run(
        job_id=config.job_id,
        run_payload=config.to_run_payload(),
        idempotency_key=config.idempotency_key,
    )
    return build_run_metadata(submitted)


def wait_for_run_with_client(
    client: SparkPilotClient,
    config: WaitRunOpConfig,
    *,
    run_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = _run_id_from_config_or_metadata(
        config_run_id=config.run_id,
        run_metadata=run_metadata,
        config_key="run_id",
    )
    terminal = client.wait_for_terminal_state(
        run_id=run_id,
        poll_interval_seconds=config.poll_interval_seconds,
        timeout_seconds=config.timeout_seconds,
    )
    return build_run_metadata(terminal)


def cancel_run_with_client(
    client: SparkPilotClient,
    config: CancelRunOpConfig,
    *,
    run_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = _run_id_from_config_or_metadata(
        config_run_id=config.run_id,
        run_metadata=run_metadata,
        config_key="run_id",
    )
    cancel_response = client.cancel_run(run_id=run_id, idempotency_key=config.idempotency_key)
    state = str(cancel_response.get("state") or "").lower()
    if state in TERMINAL_STATES:
        return build_run_metadata(cancel_response)
    if not config.wait_for_completion:
        return build_run_metadata(cancel_response)
    terminal = client.wait_for_terminal_state(
        run_id=run_id,
        poll_interval_seconds=config.poll_interval_seconds,
        timeout_seconds=config.timeout_seconds,
    )
    return build_run_metadata(terminal)


SUBMIT_RUN_OP_CONFIG_SCHEMA = {
    "job_id": Field(str, description="SparkPilot job id to run."),
    "golden_path": Field(
        str,
        is_required=False,
        default_value="",
        description="Golden-path preset identifier used for opinionated run templates.",
    ),
    "args": Field(
        [str],
        is_required=False,
        default_value=[],
        description="Optional argument list override for the run entrypoint.",
    ),
    "spark_conf": Field(
        dict,
        is_required=False,
        default_value={},
        description="Optional Spark configuration overrides.",
    ),
    "requested_resources": Field(
        dict,
        is_required=False,
        default_value={},
        description="Requested driver/executor resources.",
    ),
    "run_timeout_seconds": Field(
        int,
        is_required=False,
        default_value=0,
        description="Optional SparkPilot run timeout override in seconds.",
    ),
    "idempotency_key": Field(
        str,
        is_required=False,
        default_value="",
        description="Optional idempotency key for replay-safe submit.",
    ),
}

WAIT_RUN_OP_CONFIG_SCHEMA = {
    "run_id": Field(
        str,
        is_required=False,
        default_value="",
        description="Run id to poll. When omitted, upstream metadata.id is used.",
    ),
    "poll_interval_seconds": Field(
        int,
        is_required=False,
        default_value=15,
        description="Poll interval while waiting for terminal state.",
    ),
    "timeout_seconds": Field(
        int,
        is_required=False,
        default_value=3600,
        description="Maximum wait time for terminal state.",
    ),
}

CANCEL_RUN_OP_CONFIG_SCHEMA = {
    "run_id": Field(
        str,
        is_required=False,
        default_value="",
        description="Run id to cancel. When omitted, upstream metadata.id is used.",
    ),
    "idempotency_key": Field(
        str,
        is_required=False,
        default_value="",
        description="Optional idempotency key for replay-safe cancel requests.",
    ),
    "wait_for_completion": Field(
        bool,
        is_required=False,
        default_value=True,
        description="When true, poll until run reaches a terminal state.",
    ),
    "poll_interval_seconds": Field(
        int,
        is_required=False,
        default_value=10,
        description="Poll interval while waiting after cancel request.",
    ),
    "timeout_seconds": Field(
        int,
        is_required=False,
        default_value=600,
        description="Maximum wait duration after cancel request.",
    ),
}


def _normalized_op_config(context: OpExecutionContext) -> dict[str, Any]:
    return normalize_op_config(getattr(context, "op_config", {}) or {})


@op(
    required_resource_keys={"sparkpilot"},
    out=Out(dict, description="Normalized SparkPilot run metadata."),
    config_schema=SUBMIT_RUN_OP_CONFIG_SCHEMA,
)
def sparkpilot_submit_run_op(context) -> dict[str, Any]:  # noqa: ANN001
    client = _resolve_sparkpilot_client(context)
    config = SubmitRunOpConfig.from_mapping(_normalized_op_config(context))
    try:
        result = submit_run_with_client(client, config)
    except SparkPilotError as exc:
        raise map_sparkpilot_error_to_dagster(exc) from exc
    context.log.info("Submitted SparkPilot run '%s' for job '%s'.", result.get("id"), config.job_id)
    return result


@op(
    required_resource_keys={"sparkpilot"},
    ins={"run_metadata": In(dict, description="Submit op output metadata.")},
    out=Out(dict, description="Terminal SparkPilot run metadata."),
    config_schema=WAIT_RUN_OP_CONFIG_SCHEMA,
)
def sparkpilot_wait_for_run_op(  # noqa: ANN001
    context, run_metadata: dict[str, Any]
) -> dict[str, Any]:
    client = _resolve_sparkpilot_client(context)
    config = WaitRunOpConfig.from_mapping(_normalized_op_config(context))
    try:
        result = wait_for_run_with_client(client, config, run_metadata=run_metadata)
    except SparkPilotError as exc:
        raise map_sparkpilot_error_to_dagster(exc) from exc
    context.log.info("Run '%s' reached terminal status '%s'.", result.get("id"), result.get("status"))
    return result


@op(
    required_resource_keys={"sparkpilot"},
    ins={"run_metadata": In(dict, description="Submit op output metadata.")},
    out=Out(dict, description="Post-cancel SparkPilot run metadata."),
    config_schema=CANCEL_RUN_OP_CONFIG_SCHEMA,
)
def sparkpilot_cancel_run_op(  # noqa: ANN001
    context, run_metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    client = _resolve_sparkpilot_client(context)
    config = CancelRunOpConfig.from_mapping(_normalized_op_config(context))
    try:
        result = cancel_run_with_client(client, config, run_metadata=run_metadata)
    except SparkPilotError as exc:
        raise map_sparkpilot_error_to_dagster(exc) from exc
    context.log.info("Run '%s' cancellation completed with status '%s'.", result.get("id"), result.get("status"))
    return result


def build_local_test_context(
    *,
    sparkpilot: SparkPilotClient,
    op_config: dict[str, Any] | None = None,
) -> Any:
    """Build a context for local/unit tests.

    When Dagster is installed, uses ``dagster.build_op_context`` so that
    direct ``@op`` invocations work correctly under Dagster 1.8+.
    When Dagster is not installed, returns the lightweight compat shim context.
    """
    if _build_op_context_fn is not None:
        return _build_op_context_fn(
            op_config=op_config or {},
            resources={"sparkpilot": sparkpilot},
        )
    return _LocalTestOpContext(op_config=op_config or {}, resources=SimpleNamespace(sparkpilot=sparkpilot))
