from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import sparkpilot.services.preflight as preflight


def _fake_environment(env_id: str, *, updated_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        id=env_id,
        status="ready",
        region="us-east-1",
        tenant_id="tenant-a",
        instance_architecture="mixed",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/example",
        eks_namespace="sparkpilot",
        emr_virtual_cluster_id="vc-1234",
        updated_at=updated_at,
    )


def test_preflight_cache_invalidates_on_environment_change(monkeypatch) -> None:
    preflight._preflight_cache.clear()
    calls = {"count": 0}

    def _fake_build_preflight(
        environment,
        run_id=None,
        *,
        spark_conf=None,
        require_environment_ready=True,  # noqa: ARG001
        require_virtual_cluster=True,  # noqa: ARG001
        db=None,  # noqa: ARG001
    ):
        calls["count"] += 1
        return {
            "environment_id": environment.id,
            "run_id": run_id,
            "ready": True,
            "generated_at": preflight._now(),
            "checks": [],
        }

    monkeypatch.setattr(preflight, "_build_preflight", _fake_build_preflight)

    env = _fake_environment("env-a", updated_at=datetime.now(UTC))
    first = preflight._build_preflight_cached(env, run_id="run-1", spark_conf={"k": "v"})
    second = preflight._build_preflight_cached(env, run_id="run-2", spark_conf={"k": "v"})
    assert calls["count"] == 1
    assert first["environment_id"] == second["environment_id"]
    assert second["run_id"] == "run-2"

    env.updated_at = env.updated_at + timedelta(seconds=1)
    preflight._build_preflight_cached(env, run_id="run-3", spark_conf={"k": "v"})
    assert calls["count"] == 2


def test_preflight_cache_has_max_size(monkeypatch) -> None:
    preflight._preflight_cache.clear()
    monkeypatch.setattr(preflight, "_PREFLIGHT_CACHE_MAX_ENTRIES", 2)
    monkeypatch.setattr(preflight, "_PREFLIGHT_CACHE_TTL_SECONDS", 3600)

    def _fake_build_preflight(
        environment,
        run_id=None,
        *,
        spark_conf=None,  # noqa: ARG001
        require_environment_ready=True,  # noqa: ARG001
        require_virtual_cluster=True,  # noqa: ARG001
        db=None,  # noqa: ARG001
    ):
        return {
            "environment_id": environment.id,
            "run_id": run_id,
            "ready": True,
            "generated_at": preflight._now(),
            "checks": [],
        }

    monkeypatch.setattr(preflight, "_build_preflight", _fake_build_preflight)

    now = datetime.now(UTC)
    for idx in range(3):
        env = _fake_environment(f"env-{idx}", updated_at=now + timedelta(seconds=idx))
        preflight._build_preflight_cached(env, run_id=f"run-{idx}", spark_conf={"k": str(idx)})

    assert len(preflight._preflight_cache) == 2
