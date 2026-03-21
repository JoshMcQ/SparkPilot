"""Cost-center policy parsing and resolution helpers.

This module is intentionally dependency-light so both runtime dispatch
(`aws_clients`) and FinOps allocation (`services.finops`) can share the same
resolution behavior without circular imports.
"""

from dataclasses import dataclass
from functools import lru_cache
import json
from typing import Any


MAX_COST_CENTER_LENGTH = 255
_SUPPORTED_POLICY_KEYS = {"by_namespace", "by_virtual_cluster_id", "by_virtual_cluster", "by_team", "default"}


@dataclass(frozen=True)
class CostCenterPolicy:
    by_namespace: dict[str, str]
    by_virtual_cluster_id: dict[str, str]
    by_team: dict[str, str]
    default: str | None


@dataclass(frozen=True)
class CostCenterResolutionInputs:
    tenant_id: str
    namespace: str
    virtual_cluster_id: str
    environment_id: str


def _normalize_value(value: str, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} values must be non-empty strings.")
    return text[:MAX_COST_CENTER_LENGTH]


def _normalize_resolution_inputs(environment: Any) -> CostCenterResolutionInputs:
    return CostCenterResolutionInputs(
        tenant_id=str(getattr(environment, "tenant_id", "") or "").strip(),
        namespace=str(getattr(environment, "eks_namespace", "") or "").strip(),
        virtual_cluster_id=str(getattr(environment, "emr_virtual_cluster_id", "") or "").strip(),
        environment_id=str(getattr(environment, "id", "") or "").strip(),
    )


def _validate_mapping(payload: Any, *, key_name: str) -> dict[str, str]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"{key_name} must be a JSON object of string->string mappings.")
    out: dict[str, str] = {}
    for raw_key, raw_value in payload.items():
        key = str(raw_key).strip()
        if not key:
            raise ValueError(f"{key_name} keys must be non-empty strings.")
        out[key] = _normalize_value(raw_value, field_name=f"{key_name}.{key}")
    return out


@lru_cache(maxsize=64)
def _parse_policy_cached(raw_policy: str) -> CostCenterPolicy:
    raw = raw_policy.strip()
    if not raw:
        return CostCenterPolicy(by_namespace={}, by_virtual_cluster_id={}, by_team={}, default=None)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"must be valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("must be a JSON object.")

    extra = set(payload.keys()) - _SUPPORTED_POLICY_KEYS
    if extra:
        raise ValueError(f"contains unsupported keys: {', '.join(sorted(extra))}.")

    by_namespace = _validate_mapping(payload.get("by_namespace"), key_name="by_namespace")
    by_virtual_cluster = _validate_mapping(
        payload.get("by_virtual_cluster_id", payload.get("by_virtual_cluster")),
        key_name="by_virtual_cluster_id",
    )
    by_team = _validate_mapping(payload.get("by_team"), key_name="by_team")
    default_raw = payload.get("default")
    default_value: str | None
    if default_raw is None:
        default_value = None
    else:
        default_value = _normalize_value(default_raw, field_name="default")

    return CostCenterPolicy(
        by_namespace=by_namespace,
        by_virtual_cluster_id=by_virtual_cluster,
        by_team=by_team,
        default=default_value,
    )


def parse_cost_center_policy(raw_policy: str) -> CostCenterPolicy:
    """Parse policy JSON into a normalized immutable object."""
    return _parse_policy_cached(raw_policy or "")


def _resolve_cost_center_from_policy(*, policy: CostCenterPolicy, inputs: CostCenterResolutionInputs) -> str | None:
    lookups = (
        (inputs.virtual_cluster_id, policy.by_virtual_cluster_id),
        (inputs.namespace, policy.by_namespace),
        (inputs.tenant_id, policy.by_team),
    )
    for key, mapping in lookups:
        if key and key in mapping:
            return mapping[key]
    return policy.default


def _resolve_cost_center_fallback(inputs: CostCenterResolutionInputs) -> str:
    for fallback in (inputs.namespace, inputs.virtual_cluster_id, inputs.environment_id):
        if fallback:
            return fallback[:MAX_COST_CENTER_LENGTH]
    return "unmapped"


def resolve_cost_center_for_environment(*, settings: Any, environment: Any) -> str:
    """Resolve the effective cost center for an environment.

    Resolution precedence:
    1) by_virtual_cluster_id
    2) by_namespace
    3) by_team (tenant)
    4) default
    5) legacy fallback: namespace -> virtual cluster id -> environment id
    """
    policy_raw = str(getattr(settings, "cost_center_policy_json", "") or "")
    policy = parse_cost_center_policy(policy_raw)
    inputs = _normalize_resolution_inputs(environment)

    return _resolve_cost_center_from_policy(policy=policy, inputs=inputs) or _resolve_cost_center_fallback(inputs)
