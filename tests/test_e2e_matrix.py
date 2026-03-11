from pathlib import Path

import pytest

import sparkpilot.e2e_matrix as e2e_matrix_module
from sparkpilot.config import get_settings
from sparkpilot.e2e_matrix import (
    MatrixConfig,
    MatrixRunOptions,
    estimate_matrix_cost_usd_micros,
    estimate_run_cost_usd_micros,
    evaluate_preflight_expectations,
    run_matrix,
)
from sparkpilot.services.finops import PricingSnapshot, _reset_pricing_cache


def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    _reset_pricing_cache()


def _base_manifest() -> dict:
    return {
        "matrix_name": "test-matrix",
        "environment": {
            "tenant_name_prefix": "Matrix Tenant",
            "region": "us-east-1",
            "provisioning_mode": "byoc_lite",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/sparkpilot",
            "eks_namespace": "sparkpilot-matrix",
            "instance_architecture": "mixed",
        },
        "job_defaults": {
            "name_prefix": "matrix-job",
            "artifact_uri": "s3://bucket/job.py",
            "artifact_digest": "sha256:test",
            "entrypoint": "job.main",
            "timeout_seconds": 600,
        },
        "scenarios": [
            {
                "name": "baseline",
                "description": "baseline scenario",
                "submit_run": False,
            }
        ],
    }


def test_matrix_config_requires_namespace_for_byoc_lite() -> None:
    payload = _base_manifest()
    del payload["environment"]["eks_namespace"]

    with pytest.raises(ValueError) as exc_info:
        MatrixConfig.from_dict(payload)
    assert "eks_namespace is required" in str(exc_info.value)


def test_estimate_run_cost_matches_expected_formula() -> None:
    payload = _base_manifest()
    payload["scenarios"][0]["requested_resources"] = {
        "driver_vcpu": 1,
        "driver_memory_gb": 2,
        "executor_vcpu": 2,
        "executor_memory_gb": 3,
        "executor_instances": 2,
    }
    config = MatrixConfig.from_dict(payload)
    resources = config.scenarios[0].requested_resources
    # total_vcpu = 5, total_memory = 8, timeout = 600
    # cost = ((5*600*11.244) + (8*600*1.235)) * 0.9 = 35693.4 -> 35694
    cost = estimate_run_cost_usd_micros(resources, timeout_seconds=600, instance_architecture="mixed")
    assert cost == 35_694


def test_estimate_matrix_ignores_non_submit_scenarios() -> None:
    payload = _base_manifest()
    payload["scenarios"] = [
        {
            "name": "no-submit",
            "description": "skip actual run",
            "submit_run": False,
        },
        {
            "name": "submit",
            "description": "run once",
            "submit_run": True,
            "repeat": 2,
            "requested_resources": {
                "driver_vcpu": 1,
                "driver_memory_gb": 1,
                "executor_vcpu": 1,
                "executor_memory_gb": 1,
                "executor_instances": 0,
            },
            "timeout_seconds": 100,
        },
    ]
    config = MatrixConfig.from_dict(payload)
    # Per run: ((1*100*11.244)+(1*100*1.235))*0.9 = 1123.11 -> 1123
    assert estimate_matrix_cost_usd_micros(config) == 2_246


def test_estimate_run_cost_uses_env_pricing_coefficients(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_PRICING_VCPU_USD_PER_SECOND", "0.00002")
    monkeypatch.setenv("SPARKPILOT_PRICING_MEMORY_GB_USD_PER_SECOND", "0.000003")
    monkeypatch.setenv("SPARKPILOT_PRICING_MIXED_DISCOUNT_PCT", "10")
    _clear_settings_cache()
    resources = MatrixConfig.from_dict(_base_manifest()).scenarios[0].requested_resources
    cost = estimate_run_cost_usd_micros(resources, timeout_seconds=100, instance_architecture="mixed")
    # resources defaults: total_vcpu=5, total_memory=20
    # usd = (5*100*0.00002) + (20*100*0.000003) = 0.016
    # micros = 16000, mixed 10% discount => 14400
    assert cost == 14_400
    _clear_settings_cache()


def test_estimate_run_cost_uses_runtime_pricing_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv("SPARKPILOT_PRICING_SOURCE", "auto")
    _clear_settings_cache()

    pricing = PricingSnapshot(
        vcpu_usd_per_second=0.00002,
        memory_gb_usd_per_second=0.000003,
        arm64_discount_pct=20.0,
        mixed_discount_pct=10.0,
        source="aws_pricing_api:test",
    )
    monkeypatch.setattr(e2e_matrix_module, "resolve_runtime_pricing", lambda _settings: pricing)

    resources = MatrixConfig.from_dict(_base_manifest()).scenarios[0].requested_resources
    # resources defaults: total_vcpu=5, total_memory=20
    # usd = (5*100*0.00002) + (20*100*0.000003) = 0.016
    # micros = 16000, mixed 10% discount => 14400
    cost = estimate_run_cost_usd_micros(resources, timeout_seconds=100, instance_architecture="mixed")
    assert cost == 14_400
    _clear_settings_cache()


def test_evaluate_preflight_expectations_detects_mismatch() -> None:
    payload = _base_manifest()
    payload["scenarios"][0]["expect_preflight_ready"] = False
    payload["scenarios"][0]["expected_preflight_statuses"] = {
        "team_budget": "fail",
    }
    config = MatrixConfig.from_dict(payload)
    scenario = config.scenarios[0]

    preflight = {
        "ready": True,
        "checks": [{"code": "team_budget", "status": "pass"}],
    }
    failures = evaluate_preflight_expectations(preflight, scenario)
    assert len(failures) == 2
    assert "Expected preflight ready=False" in failures[0]


def test_matrix_config_parses_manifest_v2_fields() -> None:
    payload = _base_manifest()
    payload["scenarios"][0] = {
        "name": "v2",
        "description": "v2 fields",
        "submit_run": False,
        "orchestrator_path": "airflow",
        "security_context": {"iam_profile": "restricted"},
        "integration_requirements": ["athena", "cur"],
        "cluster_mutations": {"scale_node_group_to": 0},
        "failure_injection": {"inject_access_denied": True},
    }
    config = MatrixConfig.from_dict(payload)
    scenario = config.scenarios[0]
    assert scenario.orchestrator_path == "airflow"
    assert scenario.security_context["iam_profile"] == "restricted"
    assert scenario.integration_requirements == ["athena", "cur"]
    assert scenario.cluster_mutations["scale_node_group_to"] == 0
    assert scenario.failure_injection["inject_access_denied"] is True


def test_matrix_config_rejects_invalid_orchestrator_path() -> None:
    payload = _base_manifest()
    payload["scenarios"][0]["orchestrator_path"] = "unknown"

    with pytest.raises(ValueError) as exc_info:
        MatrixConfig.from_dict(payload)
    assert "orchestrator_path must be one of" in str(exc_info.value)


class _FakeClient:
    def create_tenant(self, *, actor: str, tenant_name: str) -> dict:
        return {"id": "tenant-1", "name": tenant_name}

    def create_environment(self, *, actor: str, payload: dict) -> dict:
        return {"id": "op-1", "environment_id": "env-1"}

    def get_provisioning_operation(self, *, actor: str, operation_id: str) -> dict:
        return {"id": operation_id, "state": "ready"}

    def get_preflight(self, *, actor: str, environment_id: str, run_id: str | None = None) -> dict:
        return {"environment_id": environment_id, "ready": True, "checks": []}


def test_run_matrix_succeeds_for_preflight_only_scenario(tmp_path: Path) -> None:
    payload = _base_manifest()
    config = MatrixConfig.from_dict(payload)
    artifacts_dir = tmp_path / "artifacts"
    summary = run_matrix(
        client=_FakeClient(),  # type: ignore[arg-type]
        config=config,
        options=MatrixRunOptions(default_actor="matrix-admin", fail_fast=True),
        artifacts_dir=artifacts_dir,
    )
    assert summary["failed_scenarios"] == 0
    assert summary["passed_scenarios"] == 1
    assert (artifacts_dir / "summary.json").exists()


def test_run_matrix_summary_includes_v2_metrics_and_coverage_gaps(tmp_path: Path) -> None:
    class _BlockingPreflightClient(_FakeClient):
        def get_preflight(self, *, actor: str, environment_id: str, run_id: str | None = None) -> dict:
            return {"environment_id": environment_id, "ready": False, "checks": []}

    payload = _base_manifest()
    payload["scenarios"][0]["expect_preflight_ready"] = False
    payload["scenarios"][0]["required_external_evidence"] = [
        str(tmp_path / "missing-evidence.json"),
    ]
    config = MatrixConfig.from_dict(payload)
    artifacts_dir = tmp_path / "artifacts-v2"
    summary = run_matrix(
        client=_BlockingPreflightClient(),  # type: ignore[arg-type]
        config=config,
        options=MatrixRunOptions(default_actor="matrix-admin", fail_fast=True),
        artifacts_dir=artifacts_dir,
    )
    assert summary["unexpected_failures"] == 0
    assert summary["expected_block_events"] == 1
    assert len(summary["coverage_gaps"]) == 1
    gap = summary["coverage_gaps"][0]
    assert gap["missing_evidence"].endswith("missing-evidence.json")


def test_run_matrix_blocks_when_scenario_cost_over_cap(tmp_path: Path) -> None:
    payload = _base_manifest()
    payload["scenarios"][0]["submit_run"] = True
    payload["scenarios"][0]["requested_resources"] = {
        "driver_vcpu": 10,
        "driver_memory_gb": 64,
        "executor_vcpu": 10,
        "executor_memory_gb": 64,
        "executor_instances": 10,
    }
    payload["scenarios"][0]["timeout_seconds"] = 7200
    config = MatrixConfig.from_dict(payload)

    with pytest.raises(RuntimeError) as exc_info:
        run_matrix(
            client=_FakeClient(),  # type: ignore[arg-type]
            config=config,
            options=MatrixRunOptions(
                default_actor="matrix-admin",
                max_scenario_cost_usd=0.01,
                allow_over_budget=False,
            ),
            artifacts_dir=tmp_path / "artifacts-scenario-cap",
        )
    assert "exceeds --max-scenario-cost-usd" in str(exc_info.value)


def test_run_matrix_blocks_when_cost_over_cap(tmp_path: Path) -> None:
    payload = _base_manifest()
    payload["scenarios"][0]["submit_run"] = True
    payload["scenarios"][0]["repeat"] = 1
    payload["scenarios"][0]["requested_resources"] = {
        "driver_vcpu": 10,
        "driver_memory_gb": 64,
        "executor_vcpu": 10,
        "executor_memory_gb": 64,
        "executor_instances": 10,
    }
    payload["scenarios"][0]["timeout_seconds"] = 7200
    config = MatrixConfig.from_dict(payload)

    with pytest.raises(RuntimeError) as exc_info:
        run_matrix(
            client=_FakeClient(),  # type: ignore[arg-type]
            config=config,
            options=MatrixRunOptions(
                default_actor="matrix-admin",
                max_estimated_cost_usd=0.01,
                allow_over_budget=False,
            ),
            artifacts_dir=tmp_path / "artifacts",
        )
    assert "exceeds --max-estimated-cost-usd" in str(exc_info.value)
