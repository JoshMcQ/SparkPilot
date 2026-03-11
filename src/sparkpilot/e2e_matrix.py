"""Enterprise E2E scenario matrix runner with cost caps and evidence artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import time
from typing import Any
import uuid

import httpx

from sparkpilot.config import get_settings
from sparkpilot.services.finops import PricingSnapshot, resolve_runtime_pricing

TERMINAL_RUN_STATES = {"succeeded", "failed", "cancelled", "timed_out"}
PREFLIGHT_STATUSES = {"pass", "warning", "fail"}
RUN_EXPECTED_STATES = {"succeeded", "failed", "cancelled", "timed_out"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _require_non_empty_string(data: dict[str, Any], key: str, *, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: '{key}' must be a non-empty string.")
    return value.strip()


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"'{key}' must be a string when provided.")
    candidate = value.strip()
    return candidate or None


def _optional_dict_str_str(data: dict[str, Any], key: str) -> dict[str, str] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"'{key}' must be an object when provided.")
    parsed: dict[str, str] = {}
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ValueError(f"'{key}' keys and values must be strings.")
        parsed[k] = v
    return parsed


def _optional_string_list(data: dict[str, Any], key: str) -> list[str] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"'{key}' must be a list when provided.")
    parsed: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"'{key}' items must be strings.")
        parsed.append(item)
    return parsed


def _to_positive_int(value: Any, *, key: str, minimum: int = 1) -> int:
    if not isinstance(value, int) or value < minimum:
        raise ValueError(f"'{key}' must be an integer >= {minimum}.")
    return value


@dataclass(frozen=True)
class RequestedResources:
    driver_vcpu: int = 1
    driver_memory_gb: int = 4
    executor_vcpu: int = 2
    executor_memory_gb: int = 8
    executor_instances: int = 2

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RequestedResources":
        if payload is None:
            return cls()
        if not isinstance(payload, dict):
            raise ValueError("'requested_resources' must be an object when provided.")
        return cls(
            driver_vcpu=_to_positive_int(payload.get("driver_vcpu", 1), key="requested_resources.driver_vcpu"),
            driver_memory_gb=_to_positive_int(
                payload.get("driver_memory_gb", 4), key="requested_resources.driver_memory_gb"
            ),
            executor_vcpu=_to_positive_int(payload.get("executor_vcpu", 2), key="requested_resources.executor_vcpu"),
            executor_memory_gb=_to_positive_int(
                payload.get("executor_memory_gb", 8), key="requested_resources.executor_memory_gb"
            ),
            executor_instances=_to_positive_int(
                payload.get("executor_instances", 2), key="requested_resources.executor_instances", minimum=0
            ),
        )

    def to_api_payload(self) -> dict[str, int]:
        return asdict(self)

    def total_vcpu(self) -> int:
        return self.driver_vcpu + (self.executor_vcpu * self.executor_instances)

    def total_memory_gb(self) -> int:
        return self.driver_memory_gb + (self.executor_memory_gb * self.executor_instances)


@dataclass(frozen=True)
class MatrixEnvironment:
    tenant_name_prefix: str
    region: str
    provisioning_mode: str
    customer_role_arn: str
    eks_cluster_arn: str | None
    eks_namespace: str | None
    instance_architecture: str
    quotas: dict[str, int]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MatrixEnvironment":
        if not isinstance(payload, dict):
            raise ValueError("'environment' must be an object.")
        tenant_name_prefix = _require_non_empty_string(payload, "tenant_name_prefix", context="environment")
        region = _require_non_empty_string(payload, "region", context="environment")
        provisioning_mode = _require_non_empty_string(payload, "provisioning_mode", context="environment")
        if provisioning_mode not in {"byoc_lite", "full"}:
            raise ValueError("environment.provisioning_mode must be 'byoc_lite' or 'full'.")
        customer_role_arn = _require_non_empty_string(payload, "customer_role_arn", context="environment")
        eks_cluster_arn = _optional_string(payload, "eks_cluster_arn")
        eks_namespace = _optional_string(payload, "eks_namespace")
        if provisioning_mode == "byoc_lite":
            if not eks_cluster_arn:
                raise ValueError("environment.eks_cluster_arn is required for provisioning_mode=byoc_lite.")
            if not eks_namespace:
                raise ValueError("environment.eks_namespace is required for provisioning_mode=byoc_lite.")
        instance_architecture = _optional_string(payload, "instance_architecture") or "mixed"
        if instance_architecture not in {"x86_64", "arm64", "mixed"}:
            raise ValueError("environment.instance_architecture must be one of x86_64, arm64, mixed.")
        raw_quotas = payload.get("quotas") or {}
        if not isinstance(raw_quotas, dict):
            raise ValueError("environment.quotas must be an object when provided.")
        quotas = {
            "max_concurrent_runs": _to_positive_int(
                raw_quotas.get("max_concurrent_runs", 10),
                key="environment.quotas.max_concurrent_runs",
            ),
            "max_vcpu": _to_positive_int(raw_quotas.get("max_vcpu", 256), key="environment.quotas.max_vcpu"),
            "max_run_seconds": _to_positive_int(
                raw_quotas.get("max_run_seconds", 7200),
                key="environment.quotas.max_run_seconds",
            ),
        }
        return cls(
            tenant_name_prefix=tenant_name_prefix,
            region=region,
            provisioning_mode=provisioning_mode,
            customer_role_arn=customer_role_arn,
            eks_cluster_arn=eks_cluster_arn,
            eks_namespace=eks_namespace,
            instance_architecture=instance_architecture,
            quotas=quotas,
        )


@dataclass(frozen=True)
class MatrixJobDefaults:
    name_prefix: str
    artifact_uri: str
    artifact_digest: str
    entrypoint: str
    args: list[str] = field(default_factory=list)
    spark_conf: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 1800

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MatrixJobDefaults":
        if not isinstance(payload, dict):
            raise ValueError("'job_defaults' must be an object.")
        return cls(
            name_prefix=_require_non_empty_string(payload, "name_prefix", context="job_defaults"),
            artifact_uri=_require_non_empty_string(payload, "artifact_uri", context="job_defaults"),
            artifact_digest=_require_non_empty_string(payload, "artifact_digest", context="job_defaults"),
            entrypoint=_require_non_empty_string(payload, "entrypoint", context="job_defaults"),
            args=_optional_string_list(payload, "args") or [],
            spark_conf=_optional_dict_str_str(payload, "spark_conf") or {},
            timeout_seconds=_to_positive_int(payload.get("timeout_seconds", 1800), key="job_defaults.timeout_seconds"),
        )


@dataclass(frozen=True)
class ScenarioBudget:
    monthly_budget_usd_micros: int
    warn_threshold_pct: int
    block_threshold_pct: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScenarioBudget":
        if not isinstance(payload, dict):
            raise ValueError("'team_budget' must be an object.")
        warn_threshold_pct = _to_positive_int(payload.get("warn_threshold_pct", 80), key="team_budget.warn_threshold_pct")
        block_threshold_pct = _to_positive_int(
            payload.get("block_threshold_pct", 100), key="team_budget.block_threshold_pct"
        )
        if warn_threshold_pct > 100 or block_threshold_pct > 100:
            raise ValueError("team_budget thresholds must be <= 100.")
        if warn_threshold_pct > block_threshold_pct:
            raise ValueError("team_budget.warn_threshold_pct must be <= block_threshold_pct.")
        return cls(
            monthly_budget_usd_micros=_to_positive_int(
                payload.get("monthly_budget_usd_micros"), key="team_budget.monthly_budget_usd_micros"
            ),
            warn_threshold_pct=warn_threshold_pct,
            block_threshold_pct=block_threshold_pct,
        )


@dataclass(frozen=True)
class MatrixScenario:
    name: str
    description: str
    repeat: int
    submit_run: bool
    actor: str | None
    args: list[str] | None
    spark_conf: dict[str, str] | None
    golden_path: str | None
    requested_resources: RequestedResources
    timeout_seconds: int | None
    expect_preflight_ready: bool
    expected_preflight_statuses: dict[str, str]
    expected_run_state: str
    team_budget: ScenarioBudget | None
    collect_logs: bool
    collect_diagnostics: bool
    collect_showback: bool
    required_external_evidence: list[str]
    cluster_mutations: dict[str, Any]
    failure_injection: dict[str, Any]
    security_context: dict[str, str]
    orchestrator_path: str
    integration_requirements: list[str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MatrixScenario":
        if not isinstance(payload, dict):
            raise ValueError("Each scenario must be an object.")
        name = _require_non_empty_string(payload, "name", context="scenario")
        description = _require_non_empty_string(payload, "description", context=f"scenario:{name}")
        repeat = _to_positive_int(payload.get("repeat", 1), key=f"scenario:{name}.repeat")
        submit_run = bool(payload.get("submit_run", True))
        actor = _optional_string(payload, "actor")
        args = _optional_string_list(payload, "args")
        spark_conf = _optional_dict_str_str(payload, "spark_conf")
        golden_path = _optional_string(payload, "golden_path")
        requested_resources = RequestedResources.from_dict(payload.get("requested_resources"))
        timeout_raw = payload.get("timeout_seconds")
        timeout_seconds = None if timeout_raw is None else _to_positive_int(timeout_raw, key=f"scenario:{name}.timeout_seconds")
        expect_preflight_ready = bool(payload.get("expect_preflight_ready", True))
        raw_statuses = payload.get("expected_preflight_statuses") or {}
        if not isinstance(raw_statuses, dict):
            raise ValueError(f"scenario:{name}.expected_preflight_statuses must be an object.")
        expected_preflight_statuses: dict[str, str] = {}
        for check_code, status_value in raw_statuses.items():
            if not isinstance(check_code, str) or not isinstance(status_value, str):
                raise ValueError(f"scenario:{name}.expected_preflight_statuses must map strings to strings.")
            normalized = status_value.strip().lower()
            if normalized not in PREFLIGHT_STATUSES:
                raise ValueError(
                    f"scenario:{name}.expected_preflight_statuses[{check_code}] "
                    "must be one of pass|warning|fail."
                )
            expected_preflight_statuses[check_code] = normalized
        expected_run_state = _optional_string(payload, "expected_run_state") or "succeeded"
        if expected_run_state not in RUN_EXPECTED_STATES:
            raise ValueError(f"scenario:{name}.expected_run_state must be one of {sorted(RUN_EXPECTED_STATES)}.")
        team_budget_payload = payload.get("team_budget")
        team_budget = None if team_budget_payload is None else ScenarioBudget.from_dict(team_budget_payload)
        collect_logs = bool(payload.get("collect_logs", True))
        collect_diagnostics = bool(payload.get("collect_diagnostics", True))
        collect_showback = bool(payload.get("collect_showback", True))
        required_external_evidence = _optional_string_list(payload, "required_external_evidence") or []
        cluster_mutations_raw = payload.get("cluster_mutations") or {}
        if not isinstance(cluster_mutations_raw, dict):
            raise ValueError(f"scenario:{name}.cluster_mutations must be an object when provided.")
        failure_injection_raw = payload.get("failure_injection") or {}
        if not isinstance(failure_injection_raw, dict):
            raise ValueError(f"scenario:{name}.failure_injection must be an object when provided.")
        security_context_raw = payload.get("security_context") or {}
        if not isinstance(security_context_raw, dict):
            raise ValueError(f"scenario:{name}.security_context must be an object when provided.")
        security_context: dict[str, str] = {}
        for key, value in security_context_raw.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError(f"scenario:{name}.security_context must map strings to strings.")
            security_context[key] = value
        orchestrator_path = _optional_string(payload, "orchestrator_path") or "api"
        if orchestrator_path not in {"api", "cli", "airflow", "dagster", "ui"}:
            raise ValueError(f"scenario:{name}.orchestrator_path must be one of api|cli|airflow|dagster|ui.")
        integration_requirements = _optional_string_list(payload, "integration_requirements") or []
        return cls(
            name=name,
            description=description,
            repeat=repeat,
            submit_run=submit_run,
            actor=actor,
            args=args,
            spark_conf=spark_conf,
            golden_path=golden_path,
            requested_resources=requested_resources,
            timeout_seconds=timeout_seconds,
            expect_preflight_ready=expect_preflight_ready,
            expected_preflight_statuses=expected_preflight_statuses,
            expected_run_state=expected_run_state,
            team_budget=team_budget,
            collect_logs=collect_logs,
            collect_diagnostics=collect_diagnostics,
            collect_showback=collect_showback,
            required_external_evidence=required_external_evidence,
            cluster_mutations=dict(cluster_mutations_raw),
            failure_injection=dict(failure_injection_raw),
            security_context=security_context,
            orchestrator_path=orchestrator_path,
            integration_requirements=integration_requirements,
        )


@dataclass(frozen=True)
class MatrixConfig:
    matrix_name: str
    environment: MatrixEnvironment
    job_defaults: MatrixJobDefaults
    scenarios: list[MatrixScenario]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MatrixConfig":
        if not isinstance(payload, dict):
            raise ValueError("Matrix manifest must be a JSON object.")
        matrix_name = _require_non_empty_string(payload, "matrix_name", context="manifest")
        scenarios_payload = payload.get("scenarios")
        if not isinstance(scenarios_payload, list) or not scenarios_payload:
            raise ValueError("'scenarios' must be a non-empty list.")
        scenarios = [MatrixScenario.from_dict(item) for item in scenarios_payload]
        return cls(
            matrix_name=matrix_name,
            environment=MatrixEnvironment.from_dict(payload.get("environment", {})),
            job_defaults=MatrixJobDefaults.from_dict(payload.get("job_defaults", {})),
            scenarios=scenarios,
        )


def load_matrix_config(path: Path) -> MatrixConfig:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in matrix manifest {path}: {exc}") from exc
    return MatrixConfig.from_dict(payload)


def _runtime_pricing_snapshot() -> PricingSnapshot:
    return resolve_runtime_pricing(get_settings())


def _architecture_multiplier(architecture: str, pricing: PricingSnapshot) -> float:
    if architecture == "arm64":
        return max(0.0, 1.0 - (pricing.arm64_discount_pct / 100.0))
    if architecture == "mixed":
        return max(0.0, 1.0 - (pricing.mixed_discount_pct / 100.0))
    return 1.0


def estimate_run_cost_usd_micros(
    resources: RequestedResources,
    *,
    timeout_seconds: int,
    instance_architecture: str,
    pricing_snapshot: PricingSnapshot | None = None,
) -> int:
    pricing = pricing_snapshot or _runtime_pricing_snapshot()
    vcpu_seconds = timeout_seconds * resources.total_vcpu()
    memory_gb_seconds = timeout_seconds * resources.total_memory_gb()
    estimated_cost_usd = (
        (vcpu_seconds * pricing.vcpu_usd_per_second)
        + (memory_gb_seconds * pricing.memory_gb_usd_per_second)
    )
    return int((estimated_cost_usd * 1_000_000) * _architecture_multiplier(instance_architecture, pricing))


def estimate_scenario_cost_usd_micros(
    scenario: MatrixScenario,
    *,
    default_timeout_seconds: int,
    instance_architecture: str,
    pricing_snapshot: PricingSnapshot | None = None,
) -> int:
    timeout_seconds = scenario.timeout_seconds or default_timeout_seconds
    per_run = estimate_run_cost_usd_micros(
        scenario.requested_resources,
        timeout_seconds=timeout_seconds,
        instance_architecture=instance_architecture,
        pricing_snapshot=pricing_snapshot,
    )
    if not scenario.submit_run:
        return 0
    return per_run * scenario.repeat


def estimate_matrix_cost_usd_micros(
    config: MatrixConfig,
    *,
    pricing_snapshot: PricingSnapshot | None = None,
) -> int:
    snapshot = pricing_snapshot or _runtime_pricing_snapshot()
    return sum(
        estimate_scenario_cost_usd_micros(
            scenario,
            default_timeout_seconds=config.job_defaults.timeout_seconds,
            instance_architecture=config.environment.instance_architecture,
            pricing_snapshot=snapshot,
        )
        for scenario in config.scenarios
    )


def _current_billing_period() -> str:
    now = _utc_now()
    return f"{now.year:04d}-{now.month:02d}"


def evaluate_preflight_expectations(
    preflight: dict[str, Any],
    scenario: MatrixScenario,
) -> list[str]:
    failures: list[str] = []
    ready = bool(preflight.get("ready", False))
    if ready != scenario.expect_preflight_ready:
        failures.append(
            f"Expected preflight ready={scenario.expect_preflight_ready}, got {ready}."
        )
    checks_by_code: dict[str, dict[str, Any]] = {}
    for item in preflight.get("checks", []):
        code = item.get("code")
        if isinstance(code, str):
            checks_by_code[code] = item
    for expected_code, expected_status in scenario.expected_preflight_statuses.items():
        check = checks_by_code.get(expected_code)
        if check is None:
            failures.append(f"Missing expected preflight check '{expected_code}'.")
            continue
        actual = str(check.get("status", "")).lower()
        if actual != expected_status:
            failures.append(
                f"Preflight check '{expected_code}' expected status '{expected_status}', got '{actual}'."
            )
    return failures


class SparkPilotApiClient:
    """HTTP wrapper for SparkPilot API operations used by matrix runner."""

    def __init__(
        self,
        *,
        base_url: str,
        access_token: str,
        timeout_seconds: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token.strip()
        if not self.access_token:
            raise ValueError("access_token is required.")
        self.timeout_seconds = timeout_seconds

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        actor: str,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotent: bool = False,
    ) -> dict[str, Any]:
        _ = actor
        headers: dict[str, str] = {"Authorization": f"Bearer {self.access_token}"}
        if idempotent:
            headers["Idempotency-Key"] = uuid.uuid4().hex
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = client.request(method, path, headers=headers, json=body, params=params)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path} failed ({response.status_code}): {response.text}")
        return response.json()

    def create_tenant(self, *, actor: str, tenant_name: str) -> dict[str, Any]:
        return self._request_json(
            method="POST",
            path="/v1/tenants",
            actor=actor,
            body={"name": tenant_name},
            idempotent=True,
        )

    def create_environment(self, *, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json(
            method="POST",
            path="/v1/environments",
            actor=actor,
            body=payload,
            idempotent=True,
        )

    def get_provisioning_operation(self, *, actor: str, operation_id: str) -> dict[str, Any]:
        return self._request_json(
            method="GET",
            path=f"/v1/provisioning-operations/{operation_id}",
            actor=actor,
        )

    def get_preflight(self, *, actor: str, environment_id: str, run_id: str | None = None) -> dict[str, Any]:
        params = {"run_id": run_id} if run_id else None
        return self._request_json(
            method="GET",
            path=f"/v1/environments/{environment_id}/preflight",
            actor=actor,
            params=params,
        )

    def create_job(self, *, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json(
            method="POST",
            path="/v1/jobs",
            actor=actor,
            body=payload,
            idempotent=True,
        )

    def create_run(self, *, actor: str, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json(
            method="POST",
            path=f"/v1/jobs/{job_id}/runs",
            actor=actor,
            body=payload,
            idempotent=True,
        )

    def get_run(self, *, actor: str, run_id: str) -> dict[str, Any]:
        return self._request_json(
            method="GET",
            path=f"/v1/runs/{run_id}",
            actor=actor,
        )

    def get_logs(self, *, actor: str, run_id: str, limit: int = 200) -> dict[str, Any]:
        return self._request_json(
            method="GET",
            path=f"/v1/runs/{run_id}/logs",
            actor=actor,
            params={"limit": limit},
        )

    def get_diagnostics(self, *, actor: str, run_id: str) -> dict[str, Any]:
        return self._request_json(
            method="GET",
            path=f"/v1/runs/{run_id}/diagnostics",
            actor=actor,
        )

    def upsert_team_budget(
        self,
        *,
        actor: str,
        team: str,
        monthly_budget_usd_micros: int,
        warn_threshold_pct: int,
        block_threshold_pct: int,
    ) -> dict[str, Any]:
        return self._request_json(
            method="POST",
            path="/v1/team-budgets",
            actor=actor,
            body={
                "team": team,
                "monthly_budget_usd_micros": monthly_budget_usd_micros,
                "warn_threshold_pct": warn_threshold_pct,
                "block_threshold_pct": block_threshold_pct,
            },
        )

    def get_showback(self, *, actor: str, team: str, period: str) -> dict[str, Any]:
        return self._request_json(
            method="GET",
            path="/v1/costs",
            actor=actor,
            params={"team": team, "period": period},
        )


@dataclass(frozen=True)
class MatrixRunOptions:
    default_actor: str
    poll_seconds: int = 15
    wait_timeout_seconds: int = 1800
    max_estimated_cost_usd: float | None = None
    max_scenario_cost_usd: float | None = None
    allow_over_budget: bool = False
    fail_fast: bool = False
    logs_limit: int = 200


def _wait_for_operation_ready(
    *,
    client: SparkPilotApiClient,
    actor: str,
    operation_id: str,
    poll_seconds: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        op = client.get_provisioning_operation(actor=actor, operation_id=operation_id)
        state = op.get("state")
        if state == "ready":
            return op
        if state == "failed":
            raise RuntimeError(f"Provisioning operation failed: {op.get('message')}")
        time.sleep(poll_seconds)
    raise TimeoutError(f"Timed out waiting for provisioning operation {operation_id}.")


def _wait_for_run_terminal(
    *,
    client: SparkPilotApiClient,
    actor: str,
    run_id: str,
    poll_seconds: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        run = client.get_run(actor=actor, run_id=run_id)
        state = str(run.get("state", ""))
        if state in TERMINAL_RUN_STATES:
            return run
        time.sleep(poll_seconds)
    raise TimeoutError(f"Timed out waiting for run {run_id} to reach terminal state.")


def _check_cost_guard(config: MatrixConfig, options: MatrixRunOptions) -> tuple[int, str]:
    pricing_snapshot = _runtime_pricing_snapshot()
    estimated_usd_micros = estimate_matrix_cost_usd_micros(config, pricing_snapshot=pricing_snapshot)
    estimated_usd = estimated_usd_micros / 1_000_000
    message = (
        f"Estimated total matrix cost: ${estimated_usd:.4f} ({estimated_usd_micros} micros). "
        f"Pricing source: {pricing_snapshot.source}."
    )
    if options.max_estimated_cost_usd is None:
        return estimated_usd_micros, message
    if estimated_usd <= options.max_estimated_cost_usd:
        return estimated_usd_micros, message
    if options.allow_over_budget:
        return estimated_usd_micros, f"{message} Over budget but allowed by flag."
    raise RuntimeError(
        f"{message} This exceeds --max-estimated-cost-usd={options.max_estimated_cost_usd:.4f}. "
        "Increase the cap or pass --allow-over-budget."
    )


def _check_scenario_cost_guard(
    *,
    scenario: MatrixScenario,
    config: MatrixConfig,
    options: MatrixRunOptions,
) -> tuple[int, str]:
    pricing_snapshot = _runtime_pricing_snapshot()
    estimated_micros = estimate_scenario_cost_usd_micros(
        scenario,
        default_timeout_seconds=config.job_defaults.timeout_seconds,
        instance_architecture=config.environment.instance_architecture,
        pricing_snapshot=pricing_snapshot,
    )
    estimated_usd = estimated_micros / 1_000_000
    message = (
        f"Estimated scenario cost for '{scenario.name}': "
        f"${estimated_usd:.4f} ({estimated_micros} micros). "
        f"Pricing source: {pricing_snapshot.source}."
    )
    if options.max_scenario_cost_usd is None:
        return estimated_micros, message
    if estimated_usd <= options.max_scenario_cost_usd:
        return estimated_micros, message
    if options.allow_over_budget:
        return estimated_micros, f"{message} Over budget but allowed by flag."
    raise RuntimeError(
        f"{message} This exceeds --max-scenario-cost-usd={options.max_scenario_cost_usd:.4f}. "
        "Increase the cap or pass --allow-over-budget."
    )


def _scenario_job_payload(
    *,
    config: MatrixConfig,
    environment_id: str,
    scenario: MatrixScenario,
    iteration_index: int,
) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:8]
    name = f"{config.job_defaults.name_prefix}-{scenario.name}-{iteration_index}-{suffix}"
    return {
        "environment_id": environment_id,
        "name": name,
        "artifact_uri": config.job_defaults.artifact_uri,
        "artifact_digest": config.job_defaults.artifact_digest,
        "entrypoint": config.job_defaults.entrypoint,
        "args": scenario.args if scenario.args is not None else config.job_defaults.args,
        "spark_conf": (
            scenario.spark_conf
            if scenario.spark_conf is not None
            else dict(config.job_defaults.spark_conf)
        ),
        "timeout_seconds": scenario.timeout_seconds or config.job_defaults.timeout_seconds,
    }


def _scenario_run_payload(
    *,
    config: MatrixConfig,
    scenario: MatrixScenario,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "requested_resources": scenario.requested_resources.to_api_payload(),
        "timeout_seconds": scenario.timeout_seconds or config.job_defaults.timeout_seconds,
    }
    if scenario.args is not None:
        payload["args"] = scenario.args
    if scenario.spark_conf is not None:
        payload["spark_conf"] = scenario.spark_conf
    if scenario.golden_path:
        payload["golden_path"] = scenario.golden_path
    return payload


def _required_external_evidence_status(required_external_evidence: list[str]) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for item in required_external_evidence:
        path = Path(item)
        statuses.append(
            {
                "path": item,
                "exists": path.exists(),
            }
        )
    return statuses


def _coverage_gaps_from_results(scenario_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for scenario in scenario_results:
        for evidence_status in scenario.get("required_external_evidence_status", []):
            if bool(evidence_status.get("exists")):
                continue
            gaps.append(
                {
                    "scenario": scenario.get("name"),
                    "iteration": scenario.get("iteration"),
                    "missing_evidence": evidence_status.get("path"),
                }
            )
    return gaps


def run_matrix(
    *,
    client: SparkPilotApiClient,
    config: MatrixConfig,
    options: MatrixRunOptions,
    artifacts_dir: Path,
) -> dict[str, Any]:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    started_at = _utc_now_iso()
    estimated_cost_micros, cost_message = _check_cost_guard(config, options)

    manifest_artifact = artifacts_dir / "resolved-manifest.json"
    manifest_payload = asdict(config)
    manifest_payload["estimated_cost_usd_micros"] = estimated_cost_micros
    manifest_artifact.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    actor = options.default_actor
    tenant_name = f"{config.environment.tenant_name_prefix} {_utc_now().strftime('%Y%m%d-%H%M%S')}"
    tenant = client.create_tenant(actor=actor, tenant_name=tenant_name)

    environment_payload: dict[str, Any] = {
        "tenant_id": tenant["id"],
        "provisioning_mode": config.environment.provisioning_mode,
        "region": config.environment.region,
        "instance_architecture": config.environment.instance_architecture,
        "customer_role_arn": config.environment.customer_role_arn,
        "quotas": config.environment.quotas,
    }
    if config.environment.provisioning_mode == "byoc_lite":
        environment_payload["eks_cluster_arn"] = config.environment.eks_cluster_arn
        environment_payload["eks_namespace"] = config.environment.eks_namespace

    operation = client.create_environment(actor=actor, payload=environment_payload)
    operation_ready = _wait_for_operation_ready(
        client=client,
        actor=actor,
        operation_id=operation["id"],
        poll_seconds=options.poll_seconds,
        timeout_seconds=options.wait_timeout_seconds,
    )
    environment_id = operation["environment_id"]

    scenario_results: list[dict[str, Any]] = []
    failure_count = 0
    expected_block_events = 0
    billing_period = _current_billing_period()

    for scenario in config.scenarios:
        scenario_estimated_cost_micros, scenario_cost_message = _check_scenario_cost_guard(
            scenario=scenario,
            config=config,
            options=options,
        )
        scenario_actor = scenario.actor or options.default_actor
        for iteration in range(1, scenario.repeat + 1):
            scenario_start = _utc_now_iso()
            result: dict[str, Any] = {
                "name": scenario.name,
                "description": scenario.description,
                "iteration": iteration,
                "actor": scenario_actor,
                "started_at": scenario_start,
                "expected_run_state": scenario.expected_run_state,
                "required_external_evidence": scenario.required_external_evidence,
                "required_external_evidence_status": _required_external_evidence_status(
                    scenario.required_external_evidence
                ),
                "cluster_mutations": scenario.cluster_mutations,
                "failure_injection": scenario.failure_injection,
                "security_context": scenario.security_context,
                "orchestrator_path": scenario.orchestrator_path,
                "integration_requirements": scenario.integration_requirements,
                "estimated_scenario_cost_usd_micros": scenario_estimated_cost_micros,
                "estimated_scenario_cost_message": scenario_cost_message,
            }
            try:
                if scenario.team_budget is not None:
                    budget = client.upsert_team_budget(
                        actor=scenario_actor,
                        team=tenant["id"],
                        monthly_budget_usd_micros=scenario.team_budget.monthly_budget_usd_micros,
                        warn_threshold_pct=scenario.team_budget.warn_threshold_pct,
                        block_threshold_pct=scenario.team_budget.block_threshold_pct,
                    )
                    result["team_budget"] = budget

                preflight = client.get_preflight(actor=scenario_actor, environment_id=environment_id)
                result["preflight"] = preflight
                preflight_failures = evaluate_preflight_expectations(preflight, scenario)
                result["preflight_expectation_failures"] = preflight_failures
                if preflight_failures:
                    raise RuntimeError("; ".join(preflight_failures))
                if not scenario.submit_run:
                    result["status"] = "passed"
                    if not scenario.expect_preflight_ready or scenario.expected_run_state != "succeeded":
                        expected_block_events += 1
                    result["completed_at"] = _utc_now_iso()
                    scenario_results.append(result)
                    scenario_file = artifacts_dir / f"{scenario.name}-{iteration}.json"
                    scenario_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
                    continue

                job_payload = _scenario_job_payload(
                    config=config,
                    environment_id=environment_id,
                    scenario=scenario,
                    iteration_index=iteration,
                )
                job = client.create_job(actor=scenario_actor, payload=job_payload)
                result["job"] = job

                run_payload = _scenario_run_payload(config=config, scenario=scenario)
                run = client.create_run(actor=scenario_actor, job_id=job["id"], payload=run_payload)
                result["run"] = run

                terminal = _wait_for_run_terminal(
                    client=client,
                    actor=scenario_actor,
                    run_id=run["id"],
                    poll_seconds=options.poll_seconds,
                    timeout_seconds=options.wait_timeout_seconds,
                )
                result["terminal_run"] = terminal
                terminal_state = str(terminal.get("state"))
                if terminal_state != scenario.expected_run_state:
                    raise RuntimeError(
                        f"Run terminal state mismatch: expected {scenario.expected_run_state}, got {terminal_state}."
                    )

                if scenario.collect_logs:
                    result["logs"] = client.get_logs(
                        actor=scenario_actor,
                        run_id=run["id"],
                        limit=options.logs_limit,
                    )
                if scenario.collect_diagnostics:
                    result["diagnostics"] = client.get_diagnostics(actor=scenario_actor, run_id=run["id"])
                if scenario.collect_showback:
                    result["showback"] = client.get_showback(
                        actor=scenario_actor,
                        team=tenant["id"],
                        period=billing_period,
                    )
                result["status"] = "passed"
                if not scenario.expect_preflight_ready or scenario.expected_run_state != "succeeded":
                    expected_block_events += 1
            except Exception as exc:  # noqa: BLE001
                result["status"] = "failed"
                result["error"] = str(exc)
                failure_count += 1
            result["completed_at"] = _utc_now_iso()
            scenario_results.append(result)
            scenario_file = artifacts_dir / f"{scenario.name}-{iteration}.json"
            scenario_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
            if options.fail_fast and result["status"] == "failed":
                break
        if options.fail_fast and failure_count > 0:
            break

    coverage_gaps = _coverage_gaps_from_results(scenario_results)
    summary = {
        "matrix_name": config.matrix_name,
        "started_at": started_at,
        "completed_at": _utc_now_iso(),
        "cost_estimate": {
            "estimated_cost_usd_micros": estimated_cost_micros,
            "message": cost_message,
        },
        "tenant_id": tenant["id"],
        "environment_id": environment_id,
        "operation_id": operation["id"],
        "operation_state": operation_ready.get("state"),
        "total_scenarios_executed": len(scenario_results),
        "failed_scenarios": failure_count,
        "unexpected_failures": failure_count,
        "expected_block_events": expected_block_events,
        "passed_scenarios": len(scenario_results) - failure_count,
        "coverage_gaps": coverage_gaps,
        "scenario_results": scenario_results,
    }
    (artifacts_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
