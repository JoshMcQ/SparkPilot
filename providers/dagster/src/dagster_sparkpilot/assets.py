from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dagster_sparkpilot._compat import AssetExecutionContext, asset
from dagster_sparkpilot.ops import (
    CANCEL_RUN_OP_CONFIG_SCHEMA,
    SUBMIT_RUN_OP_CONFIG_SCHEMA,
    WAIT_RUN_OP_CONFIG_SCHEMA,
    CancelRunOpConfig,
    SubmitRunOpConfig,
    WaitRunOpConfig,
    cancel_run_with_client,
    submit_run_with_client,
    wait_for_run_with_client,
    _resolve_sparkpilot_client,
)


def _normalized_asset_config(context: AssetExecutionContext) -> dict[str, Any]:
    raw_config = getattr(context, "op_config", {}) or {}
    if not isinstance(raw_config, Mapping):
        raise ValueError("Asset config must be an object mapping.")
    normalized = dict(raw_config)
    if normalized.get("run_timeout_seconds", 0) == 0:
        normalized.pop("run_timeout_seconds", None)
    for key in ("golden_path", "idempotency_key", "run_id"):
        if normalized.get(key, "") == "":
            normalized.pop(key, None)
    if normalized.get("args") == []:
        normalized.pop("args", None)
    if normalized.get("spark_conf") == {}:
        normalized.pop("spark_conf", None)
    if normalized.get("requested_resources") == {}:
        normalized.pop("requested_resources", None)
    return normalized


@asset(required_resource_keys={"sparkpilot"}, config_schema=SUBMIT_RUN_OP_CONFIG_SCHEMA)
def sparkpilot_submit_asset(context: AssetExecutionContext) -> dict[str, Any]:
    client = _resolve_sparkpilot_client(context)
    config = SubmitRunOpConfig.from_mapping(_normalized_asset_config(context))
    return submit_run_with_client(client, config)


@asset(required_resource_keys={"sparkpilot"}, config_schema=WAIT_RUN_OP_CONFIG_SCHEMA)
def sparkpilot_wait_asset(
    context: AssetExecutionContext, sparkpilot_submit_asset: dict[str, Any]
) -> dict[str, Any]:
    client = _resolve_sparkpilot_client(context)
    config = WaitRunOpConfig.from_mapping(_normalized_asset_config(context))
    return wait_for_run_with_client(client, config, run_metadata=sparkpilot_submit_asset)


@asset(required_resource_keys={"sparkpilot"}, config_schema=CANCEL_RUN_OP_CONFIG_SCHEMA)
def sparkpilot_cancel_asset(
    context: AssetExecutionContext, sparkpilot_submit_asset: dict[str, Any]
) -> dict[str, Any]:
    client = _resolve_sparkpilot_client(context)
    config = CancelRunOpConfig.from_mapping(_normalized_asset_config(context))
    return cancel_run_with_client(client, config, run_metadata=sparkpilot_submit_asset)


RUN_LIFECYCLE_ASSET_CONFIG_SCHEMA: dict[str, Any] = {
    **SUBMIT_RUN_OP_CONFIG_SCHEMA,
    "poll_interval_seconds": WAIT_RUN_OP_CONFIG_SCHEMA["poll_interval_seconds"],
    "timeout_seconds": WAIT_RUN_OP_CONFIG_SCHEMA["timeout_seconds"],
}


@asset(required_resource_keys={"sparkpilot"}, config_schema=RUN_LIFECYCLE_ASSET_CONFIG_SCHEMA)
def sparkpilot_run_lifecycle_asset(context: AssetExecutionContext) -> dict[str, Any]:
    client = _resolve_sparkpilot_client(context)
    normalized = _normalized_asset_config(context)
    submit_config = SubmitRunOpConfig.from_mapping(normalized)
    wait_config = WaitRunOpConfig.from_mapping(normalized)
    submitted = submit_run_with_client(client, submit_config)
    return wait_for_run_with_client(client, wait_config, run_metadata=submitted)

