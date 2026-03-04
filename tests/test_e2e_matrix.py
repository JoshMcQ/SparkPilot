from pathlib import Path

import pytest

from sparkpilot.e2e_matrix import (
    MatrixConfig,
    MatrixRunOptions,
    estimate_matrix_cost_usd_micros,
    estimate_run_cost_usd_micros,
    evaluate_preflight_expectations,
    run_matrix,
)


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
    # cost = ((5*600*35) + (8*600*4)) * 0.9 = 111780
    cost = estimate_run_cost_usd_micros(resources, timeout_seconds=600, instance_architecture="mixed")
    assert cost == 111_780


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
    # Per run: ((1*100*35)+(1*100*4))*0.9 = 3510
    assert estimate_matrix_cost_usd_micros(config) == 7_020


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
