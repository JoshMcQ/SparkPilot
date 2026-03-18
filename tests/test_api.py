from datetime import UTC, datetime, timedelta
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import and_, select

os.environ.setdefault("SPARKPILOT_DATABASE_URL", "sqlite:///./sparkpilot_test.db")

from sparkpilot.api import app  # noqa: E402
from sparkpilot.aws_clients import EmrDispatchResult  # noqa: E402
from sparkpilot.config import get_settings  # noqa: E402
from sparkpilot.db import Base, SessionLocal, engine, init_db  # noqa: E402
from sparkpilot.models import AuditEvent, EmrRelease, Environment, ProvisioningOperation, Run, UsageRecord  # noqa: E402
from sparkpilot.services import _record_usage_if_needed, process_provisioning_once, process_reconciler_once, process_scheduler_once, sync_emr_releases_once  # noqa: E402
from sparkpilot.terraform_orchestrator import TerraformApplyResult, TerraformPlanResult  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    init_db()


def _create_ready_environment_and_run(
    client: TestClient,
    *,
    suffix: str,
    retry_max_attempts: int = 1,
    instance_architecture: str = "mixed",
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    tenant = client.post(
        "/v1/tenants",
        json={"name": f"Tenant {suffix}"},
        headers={"Idempotency-Key": f"tenant-{suffix}", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "instance_architecture": instance_architecture,
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": f"env-{suffix}", "X-Actor": "test-user"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)
    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": f"job-{suffix}",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
            "retry_max_attempts": retry_max_attempts,
        },
        headers={"Idempotency-Key": f"job-{suffix}", "X-Actor": "test-user"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={
            "requested_resources": {
                "driver_vcpu": 1,
                "driver_memory_gb": 4,
                "executor_vcpu": 1,
                "executor_memory_gb": 4,
                "executor_instances": 1,
            }
        },
        headers={"Idempotency-Key": f"run-{suffix}", "X-Actor": "test-user"},
    ).json()
    return tenant, op, job, run


def test_tenant_create_idempotent() -> None:
    client = TestClient(app)
    headers = {"Idempotency-Key": "tenant-create-key", "X-Actor": "test-user"}
    payload = {"name": "Acme Data"}
    first = client.post("/v1/tenants", json=payload, headers=headers)
    assert first.status_code == 201
    second = client.post("/v1/tenants", json=payload, headers=headers)
    assert second.status_code == 201
    assert second.headers.get("X-Idempotent-Replay") == "true"
    assert first.json()["id"] == second.json()["id"]


def test_api_bearer_auth_enforced_when_test_bypass_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ALLOW_INSECURE_TEST_AUTH", "false")
    client = TestClient(app)

    missing = client.get("/v1/runs", headers={"Authorization": "", "X-Actor": "test-user"})
    assert missing.status_code == 401

    invalid = client.get("/v1/runs", headers={"Authorization": "Bearer invalid-token", "X-Actor": "test-user"})
    assert invalid.status_code == 401

    valid = client.get("/v1/runs", headers={"Authorization": "Bearer dev-token", "X-Actor": "test-user"})
    assert valid.status_code == 200


def test_cors_allows_configured_local_ui_origin() -> None:
    client = TestClient(app)
    response = client.get("/v1/runs", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_healthz_reports_database_and_aws_checks() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"]["database"]["status"] == "ok"
    assert payload["checks"]["aws"]["status"] in {"ok", "skipped"}


def test_environment_provisioning_run_and_usage() -> None:
    client = TestClient(app)

    tenant = client.post(
        "/v1/tenants",
        json={"name": "Pilot Corp"},
        headers={"Idempotency-Key": "tenant-1", "X-Actor": "test-user"},
    ).json()

    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "warm_pool_enabled": False,
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-1", "X-Actor": "test-user"},
    )
    assert op.status_code == 201
    operation_id = op.json()["id"]
    environment_id = op.json()["environment_id"]

    with SessionLocal() as db:
        processed = process_provisioning_once(db)
    assert processed == 1

    env = client.get(f"/v1/environments/{environment_id}").json()
    assert env["status"] == "ready"

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": environment_id,
            "name": "daily-aggregation",
            "artifact_uri": "s3://acme-artifacts/jobs/daily.jar",
            "artifact_digest": "sha256:abc123",
            "entrypoint": "com.acme.jobs.Daily",
            "args": ["--date", "2026-02-17"],
            "spark_conf": {"spark.dynamicAllocation.enabled": "true"},
            "retry_max_attempts": 2,
            "timeout_seconds": 1800,
        },
        headers={"Idempotency-Key": "job-1", "X-Actor": "test-user"},
    )
    assert job.status_code == 201
    job_id = job.json()["id"]

    run = client.post(
        f"/v1/jobs/{job_id}/runs",
        json={
            "requested_resources": {
                "driver_vcpu": 1,
                "driver_memory_gb": 4,
                "executor_vcpu": 2,
                "executor_memory_gb": 8,
                "executor_instances": 2,
            }
        },
        headers={"Idempotency-Key": "run-1", "X-Actor": "test-user"},
    )
    assert run.status_code == 201
    run_id = run.json()["id"]
    assert run.json()["state"] == "queued"

    with SessionLocal() as db:
        scheduled = process_scheduler_once(db)
    assert scheduled == 1

    current = client.get(f"/v1/runs/{run_id}").json()
    assert current["state"] in {"accepted", "running"}
    assert current["emr_job_run_id"]

    with SessionLocal() as db:
        row = db.get(Run, run_id)
        assert row is not None
        row.started_at = datetime.now(UTC) - timedelta(minutes=5)
        db.commit()

    with SessionLocal() as db:
        reconciled = process_reconciler_once(db)
    assert reconciled == 1

    final = client.get(f"/v1/runs/{run_id}").json()
    assert final["state"] in {"running", "succeeded"}

    if final["state"] != "succeeded":
        with SessionLocal() as db:
            row = db.get(Run, run_id)
            assert row is not None
            row.started_at = datetime.now(UTC) - timedelta(minutes=10)
            db.commit()
            process_reconciler_once(db)
        final = client.get(f"/v1/runs/{run_id}").json()

    assert final["state"] == "succeeded"

    logs = client.get(f"/v1/runs/{run_id}/logs")
    assert logs.status_code == 200
    assert len(logs.json()["lines"]) >= 1

    usage = client.get(f"/v1/usage?tenant_id={tenant['id']}")
    assert usage.status_code == 200
    assert len(usage.json()["items"]) == 1
    usage_paged = client.get(f"/v1/usage?tenant_id={tenant['id']}&limit=1&offset=0")
    assert usage_paged.status_code == 200
    assert len(usage_paged.json()["items"]) == 1
    usage_empty_page = client.get(f"/v1/usage?tenant_id={tenant['id']}&limit=1&offset=1")
    assert usage_empty_page.status_code == 200
    assert usage_empty_page.json()["items"] == []

    op_status = client.get(f"/v1/provisioning-operations/{operation_id}")
    assert op_status.status_code == 200
    assert op_status.json()["state"] == "ready"


def test_environment_retry_endpoint_queues_new_operation() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Tenant retry-env"},
        headers={"Idempotency-Key": "tenant-retry-env", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "instance_architecture": "mixed",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 64, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-retry-env", "X-Actor": "test-user"},
    ).json()

    with SessionLocal() as db:
        env = db.get(Environment, op["environment_id"])
        assert env is not None
        env.status = "failed"
        for operation in db.execute(
            select(ProvisioningOperation).where(ProvisioningOperation.environment_id == op["environment_id"])
        ).scalars():
            operation.state = "failed"
            operation.step = "failed"
        db.commit()

    retry = client.post(
        f"/v1/environments/{op['environment_id']}/retry",
        headers={"Idempotency-Key": "env-retry-op", "X-Actor": "test-user"},
    )
    assert retry.status_code == 200
    payload = retry.json()
    assert payload["environment_id"] == op["environment_id"]
    assert payload["state"] == "queued"
    assert payload["step"] == "queued"

    env_after = client.get(f"/v1/environments/{op['environment_id']}", headers={"X-Actor": "test-user"})
    assert env_after.status_code == 200
    assert env_after.json()["status"] == "provisioning"


def test_environment_delete_blocks_active_runs_then_marks_deleted() -> None:
    client = TestClient(app)
    _, op, _, run = _create_ready_environment_and_run(client, suffix="env-delete")

    blocked = client.delete(f"/v1/environments/{op['environment_id']}", headers={"X-Actor": "test-user"})
    assert blocked.status_code == 409
    assert "active or in-flight runs" in blocked.json()["detail"]

    with SessionLocal() as db:
        run_row = db.get(Run, run["id"])
        assert run_row is not None
        run_row.state = "succeeded"
        db.commit()

    deleted = client.delete(f"/v1/environments/{op['environment_id']}", headers={"X-Actor": "test-user"})
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"


def test_default_golden_paths_seeded() -> None:
    client = TestClient(app)
    response = client.get("/v1/golden-paths")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert {"small", "medium", "large", "gpu"}.issubset(names)


def test_create_golden_path_and_submit_run_with_golden_path() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "GoldenPath Tenant"},
        headers={"Idempotency-Key": "tenant-gp", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-gp", "X-Actor": "test-user"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)

    golden = client.post(
        "/v1/golden-paths",
        json={
            "environment_id": op["environment_id"],
            "name": "medium-spot-graviton",
            "description": "Team medium profile",
            "spark_config": {
                "spark.kubernetes.executor.node.selector.eks.amazonaws.com/capacityType": "SPOT",
                "spark.kubernetes.executor.tolerations": "spot=true:NoSchedule",
            },
            "driver_resources": {"vcpu": 2, "memory_gb": 4},
            "executor_resources": {"vcpu": 2, "memory_gb": 8},
            "executor_count": 2,
            "instance_architecture": "arm64",
            "capacity_type": "spot",
            "max_runtime_minutes": 60,
            "tags": {"team": "analytics"},
            "recommended_instance_types": ["m7g.xlarge", "r7g.xlarge"],
        },
    )
    assert golden.status_code == 201

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": "job-gp",
            "artifact_uri": "s3://bucket/job.py",
            "artifact_digest": "sha256:gp123",
            "entrypoint": "main",
            "timeout_seconds": 7200,
        },
        headers={"Idempotency-Key": "job-gp", "X-Actor": "test-user"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"golden_path": "medium-spot-graviton"},
        headers={"Idempotency-Key": "run-gp", "X-Actor": "test-user"},
    )
    assert run.status_code == 201
    payload = run.json()
    assert payload["spark_conf"]["spark.kubernetes.executor.node.selector.eks.amazonaws.com/capacityType"] == "SPOT"
    assert payload["spark_conf"]["spark.kubernetes.executor.node.selector.kubernetes.io/arch"] == "arm64"
    assert payload["requested_resources"]["driver_vcpu"] == 2
    assert payload["requested_resources"]["executor_vcpu"] == 2
    assert payload["requested_resources"]["executor_instances"] == 2
    assert payload["timeout_seconds"] == 3600


def test_run_create_rejects_blocked_spark_conf_policy() -> None:
    client = TestClient(app)
    _, op, job, _ = _create_ready_environment_and_run(client, suffix="policy")

    blocked = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={
            "spark_conf": {
                "spark.kubernetes.authenticate.driver.serviceAccountName": "override-sa",
            }
        },
        headers={"Idempotency-Key": "run-policy-block", "X-Actor": "test-user"},
    )
    assert blocked.status_code == 422
    assert "violates environment policy" in blocked.json()["detail"]


def test_emr_release_sync_and_list_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "sparkpilot.services.EmrEksClient.list_release_labels",
        lambda *_args, **_kwargs: [
            "emr-7.10.0-latest",
            "emr-7.9.0-latest",
            "emr-7.8.0-latest",
            "emr-6.15.0-latest",
        ],
    )

    with SessionLocal() as db:
        changed = sync_emr_releases_once(db)
        assert changed >= 1

    client = TestClient(app)
    response = client.get("/v1/emr-releases")
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 4
    labels = {item["release_label"]: item for item in items}
    assert labels["emr-7.10.0-latest"]["lifecycle_status"] == "current"
    assert labels["emr-6.15.0-latest"]["lifecycle_status"] == "end_of_life"

    paged = client.get("/v1/emr-releases?limit=2&offset=1")
    assert paged.status_code == 200
    assert len(paged.json()) == 2


def test_preflight_warns_for_deprecated_release_label() -> None:
    with SessionLocal() as db:
        db.add(
            EmrRelease(
                release_label="emr-7.10.0-latest",
                lifecycle_status="deprecated",
                graviton_supported=True,
                lake_formation_supported=True,
                upgrade_target="emr-7.11.0-latest",
                source="emr-containers",
            )
        )
        db.commit()

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Release Currency Tenant"},
        headers={"Idempotency-Key": "tenant-release-currency", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team-a",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-release-currency", "X-Actor": "test-user"},
    )
    assert op.status_code == 201
    with SessionLocal() as db:
        process_provisioning_once(db)

    preflight = client.get(f"/v1/environments/{op.json()['environment_id']}/preflight")
    assert preflight.status_code == 200
    currency = next(item for item in preflight.json()["checks"] if item["code"] == "config.emr_release_currency")
    assert currency["status"] == "warning"
    assert "deprecated" in currency["message"].lower()


def test_preflight_fails_arm64_when_release_not_graviton_capable() -> None:
    with SessionLocal() as db:
        db.add(
            EmrRelease(
                release_label="emr-7.10.0-latest",
                lifecycle_status="current",
                graviton_supported=False,
                lake_formation_supported=True,
                upgrade_target=None,
                source="emr-containers",
            )
        )
        db.commit()

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Graviton Gate Tenant"},
        headers={"Idempotency-Key": "tenant-graviton-gate", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "instance_architecture": "arm64",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team-a",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-graviton-gate", "X-Actor": "test-user"},
    )
    assert op.status_code == 201
    with SessionLocal() as db:
        process_provisioning_once(db)

    preflight = client.get(f"/v1/environments/{op.json()['environment_id']}/preflight")
    assert preflight.status_code == 200
    graviton = next(item for item in preflight.json()["checks"] if item["code"] == "config.graviton_release_support")
    assert graviton["status"] == "fail"


def test_usage_cost_applies_arm64_discount() -> None:
    client = TestClient(app)
    _, op_x86, _, run_x86 = _create_ready_environment_and_run(client, suffix="cost-x86", instance_architecture="x86_64")
    _, op_arm, _, run_arm = _create_ready_environment_and_run(client, suffix="cost-arm", instance_architecture="arm64")

    with SessionLocal() as db:
        env_x86 = db.get(Environment, op_x86["environment_id"])
        env_arm = db.get(Environment, op_arm["environment_id"])
        row_x86 = db.get(Run, run_x86["id"])
        row_arm = db.get(Run, run_arm["id"])
        assert env_x86 is not None and env_arm is not None and row_x86 is not None and row_arm is not None
        start = datetime.now(UTC) - timedelta(minutes=10)
        end = datetime.now(UTC)
        row_x86.started_at = start
        row_x86.ended_at = end
        row_arm.started_at = start
        row_arm.ended_at = end
        _record_usage_if_needed(db, row_x86, env_x86)
        _record_usage_if_needed(db, row_arm, env_arm)
        db.commit()

        usage_x86 = db.execute(select(UsageRecord).where(UsageRecord.run_id == row_x86.id)).scalar_one()
        usage_arm = db.execute(select(UsageRecord).where(UsageRecord.run_id == row_arm.id)).scalar_one()
        assert usage_arm.estimated_cost_usd_micros < usage_x86.estimated_cost_usd_micros


def test_full_byoc_provisioning_records_checkpoint_audit(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ENABLE_FULL_BYOC_MODE", "true")
    get_settings.cache_clear()
    plan_calls: list[str] = []
    apply_calls: list[str] = []

    def _plan(_self, context):
        plan_calls.append(context.stage)
        return TerraformPlanResult(
            ok=True,
            command=["terraform", "plan", context.stage],
            plan_path=f"/tmp/{context.stage}.tfplan",
            stdout_excerpt="ok",
            stderr_excerpt="",
            error=None,
        )

    def _apply(_self, context, _plan_result):
        apply_calls.append(context.stage)
        outputs = {}
        if context.stage == "provisioning_emr":
            outputs = {
                "eks_cluster_arn": {"value": "arn:aws:eks:us-east-1:123456789012:cluster/full-byoc-demo"},
                "emr_virtual_cluster_id": {"value": "vc-fullbyocdemo"},
            }
        return TerraformApplyResult(
            ok=True,
            command=["terraform", "apply", context.stage],
            stdout_excerpt="ok",
            stderr_excerpt="",
            error=None,
            outputs=outputs,
        )

    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.plan", _plan)
    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.apply", _apply)

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Full BYOC Checkpoint Tenant"},
        headers={"Idempotency-Key": "tenant-full-checkpoint", "X-Actor": "test-user"},
    ).json()

    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "full",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-full-checkpoint", "X-Actor": "test-user"},
    ).json()

    with SessionLocal() as db:
        processed = process_provisioning_once(db)
        assert processed == 1

        env = db.get(Environment, op["environment_id"])
        assert env is not None
        assert env.status == "ready"
        assert env.emr_virtual_cluster_id is not None

        op_row = db.get(ProvisioningOperation, op["id"])
        assert op_row is not None
        assert op_row.state == "ready"

        checkpoints = list(
            db.execute(
                select(AuditEvent).where(
                    and_(
                        AuditEvent.action == "environment.full_byoc_checkpoint",
                        AuditEvent.entity_type == "environment",
                        AuditEvent.entity_id == op["environment_id"],
                    )
                )
            ).scalars()
        )
        assert len(checkpoints) >= 5
        latest = checkpoints[-1].details_json
        assert latest.get("operation_id") == op["id"]
        checkpoint = latest.get("checkpoint")
        assert isinstance(checkpoint, dict)
        attempts = checkpoint.get("attempt_count_by_stage")
        assert isinstance(attempts, dict)
        assert attempts.get("provisioning_network") == 1
        assert attempts.get("provisioning_eks") == 1
        assert attempts.get("provisioning_emr") == 1
        assert attempts.get("validating_bootstrap") == 1
        assert attempts.get("validating_runtime") == 1
        assert checkpoint.get("last_successful_stage") == "validating_runtime"
        artifacts = checkpoint.get("artifacts")
        assert isinstance(artifacts, list)
        assert any(item.get("kind") == "validation" and item.get("stage") == "validating_bootstrap" for item in artifacts)
        assert any(item.get("kind") == "validation" and item.get("stage") == "validating_runtime" for item in artifacts)
        assert "placeholder" not in (op_row.message or "").lower()

    assert plan_calls == ["provisioning_network", "provisioning_eks", "provisioning_emr"]
    assert apply_calls == ["provisioning_network", "provisioning_eks", "provisioning_emr"]


def test_full_byoc_plan_failure_preserves_prior_checkpoint(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ENABLE_FULL_BYOC_MODE", "true")
    get_settings.cache_clear()
    def _plan(_self, context):
        if context.stage == "provisioning_eks":
            return TerraformPlanResult(
                ok=False,
                command=["terraform", "plan", context.stage],
                plan_path=None,
                stdout_excerpt="",
                stderr_excerpt="Error: insufficient permissions",
                error="terraform plan failed",
            )
        return TerraformPlanResult(
            ok=True,
            command=["terraform", "plan", context.stage],
            plan_path=f"/tmp/{context.stage}.tfplan",
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    def _apply(_self, context, _plan_result):
        return TerraformApplyResult(
            ok=True,
            command=["terraform", "apply", context.stage],
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.plan", _plan)
    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.apply", _apply)

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Plan Failure Tenant"},
        headers={"Idempotency-Key": "tenant-plan-fail", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "full",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-plan-fail", "X-Actor": "test-user"},
    ).json()

    with SessionLocal() as db:
        process_provisioning_once(db)

    env_status = client.get(f"/v1/environments/{op['environment_id']}").json()
    assert env_status["status"] == "failed"

    op_status = client.get(f"/v1/provisioning-operations/{op['id']}").json()
    assert op_status["state"] == "failed"
    assert "plan failed" in (op_status["message"] or "").lower()

    with SessionLocal() as db:
        checkpoints = list(
            db.execute(
                select(AuditEvent).where(
                    and_(
                        AuditEvent.action == "environment.full_byoc_checkpoint",
                        AuditEvent.entity_id == op["environment_id"],
                    )
                ).order_by(AuditEvent.created_at.desc())
            ).scalars()
        )
        assert len(checkpoints) >= 1
        latest = checkpoints[0].details_json
        checkpoint = latest.get("checkpoint")
        assert isinstance(checkpoint, dict)
        assert checkpoint.get("last_successful_stage") == "provisioning_network"
        attempts = checkpoint.get("attempt_count_by_stage", {})
        assert attempts.get("provisioning_network") == 1
        assert attempts.get("provisioning_eks") == 1


def test_full_byoc_apply_failure_persists_attempt_count(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ENABLE_FULL_BYOC_MODE", "true")
    get_settings.cache_clear()
    def _plan(_self, context):
        return TerraformPlanResult(
            ok=True,
            command=["terraform", "plan", context.stage],
            plan_path=f"/tmp/{context.stage}.tfplan",
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    def _apply(_self, context, _plan_result):
        if context.stage == "provisioning_eks":
            return TerraformApplyResult(
                ok=False,
                command=["terraform", "apply", context.stage],
                stdout_excerpt="",
                stderr_excerpt="Error: resource creation failed",
                error="terraform apply failed",
            )
        return TerraformApplyResult(
            ok=True,
            command=["terraform", "apply", context.stage],
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.plan", _plan)
    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.apply", _apply)

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Apply Failure Tenant"},
        headers={"Idempotency-Key": "tenant-apply-fail", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "full",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-apply-fail", "X-Actor": "test-user"},
    ).json()

    with SessionLocal() as db:
        process_provisioning_once(db)

    env_status = client.get(f"/v1/environments/{op['environment_id']}").json()
    assert env_status["status"] == "failed"

    op_status = client.get(f"/v1/provisioning-operations/{op['id']}").json()
    assert op_status["state"] == "failed"
    assert "apply failed" in (op_status["message"] or "").lower()

    with SessionLocal() as db:
        checkpoints = list(
            db.execute(
                select(AuditEvent).where(
                    and_(
                        AuditEvent.action == "environment.full_byoc_checkpoint",
                        AuditEvent.entity_id == op["environment_id"],
                    )
                ).order_by(AuditEvent.created_at.desc())
            ).scalars()
        )
        assert len(checkpoints) >= 1
        latest = checkpoints[0].details_json
        checkpoint = latest.get("checkpoint")
        assert isinstance(checkpoint, dict)
        assert checkpoint.get("last_successful_stage") == "provisioning_network"
        attempts = checkpoint.get("attempt_count_by_stage", {})
        assert attempts.get("provisioning_eks") == 1


def test_full_byoc_resume_skips_completed_stages(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ENABLE_FULL_BYOC_MODE", "true")
    get_settings.cache_clear()
    plan_calls: list[str] = []
    apply_calls: list[str] = []
    fail_eks_plan = {"active": True}

    def _plan(_self, context):
        plan_calls.append(context.stage)
        if context.stage == "provisioning_eks" and fail_eks_plan["active"]:
            return TerraformPlanResult(
                ok=False,
                command=["terraform", "plan", context.stage],
                plan_path=None,
                stdout_excerpt="",
                stderr_excerpt="Error: simulated failure",
                error="terraform plan failed",
            )
        return TerraformPlanResult(
            ok=True,
            command=["terraform", "plan", context.stage],
            plan_path=f"/tmp/{context.stage}.tfplan",
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    def _apply(_self, context, _plan_result):
        apply_calls.append(context.stage)
        outputs = {}
        if context.stage == "provisioning_emr":
            outputs = {
                "eks_cluster_arn": {"value": "arn:aws:eks:us-east-1:123456789012:cluster/full-byoc-resume"},
                "emr_virtual_cluster_id": {"value": "vc-fullbyocresume"},
            }
        return TerraformApplyResult(
            ok=True,
            command=["terraform", "apply", context.stage],
            stdout_excerpt="ok",
            stderr_excerpt="",
            outputs=outputs,
        )

    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.plan", _plan)
    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.apply", _apply)

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Resume Tenant"},
        headers={"Idempotency-Key": "tenant-resume", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "full",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-resume", "X-Actor": "test-user"},
    ).json()

    # First tick: fails at provisioning_eks plan
    with SessionLocal() as db:
        process_provisioning_once(db)

    env_status = client.get(f"/v1/environments/{op['environment_id']}").json()
    assert env_status["status"] == "failed"
    assert "provisioning_network" in plan_calls
    assert "provisioning_eks" in plan_calls
    assert apply_calls == ["provisioning_network"]

    # Reset for second tick
    plan_calls.clear()
    apply_calls.clear()
    fail_eks_plan["active"] = False

    with SessionLocal() as db:
        op_row = db.get(ProvisioningOperation, op["id"])
        assert op_row is not None
        op_row.state = "provisioning_eks"
        op_row.step = "provisioning_eks"
        env_row = db.get(Environment, op["environment_id"])
        assert env_row is not None
        env_row.status = "provisioning"
        db.commit()

    # Second tick: should resume from provisioning_eks, not replay provisioning_network
    with SessionLocal() as db:
        process_provisioning_once(db)

    env_status = client.get(f"/v1/environments/{op['environment_id']}").json()
    assert env_status["status"] == "ready"
    assert "provisioning_network" not in plan_calls
    assert "provisioning_network" not in apply_calls
    assert plan_calls == ["provisioning_eks", "provisioning_emr"]
    assert apply_calls == ["provisioning_eks", "provisioning_emr"]


def test_full_byoc_per_stage_commit_survives_crash(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ENABLE_FULL_BYOC_MODE", "true")
    get_settings.cache_clear()
    def _plan(_self, context):
        if context.stage == "provisioning_eks":
            raise KeyboardInterrupt("simulated crash")
        return TerraformPlanResult(
            ok=True,
            command=["terraform", "plan", context.stage],
            plan_path=f"/tmp/{context.stage}.tfplan",
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    def _apply(_self, context, _plan_result):
        return TerraformApplyResult(
            ok=True,
            command=["terraform", "apply", context.stage],
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.plan", _plan)
    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.apply", _apply)

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Crash Durability Tenant"},
        headers={"Idempotency-Key": "tenant-crash-durable", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "full",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-crash-durable", "X-Actor": "test-user"},
    ).json()

    with pytest.raises(KeyboardInterrupt):
        with SessionLocal() as db:
            process_provisioning_once(db)

    # Despite the crash, per-stage commits preserved the checkpoint
    with SessionLocal() as db:
        checkpoints = list(
            db.execute(
                select(AuditEvent).where(
                    and_(
                        AuditEvent.action == "environment.full_byoc_checkpoint",
                        AuditEvent.entity_id == op["environment_id"],
                    )
                ).order_by(AuditEvent.created_at.asc())
            ).scalars()
        )
        assert len(checkpoints) >= 1
        latest = checkpoints[-1]
        checkpoint = latest.details_json.get("checkpoint")
        assert isinstance(checkpoint, dict)
        assert checkpoint.get("last_successful_stage") == "provisioning_network"


def test_full_byoc_bootstrap_validation_failure_is_actionable(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ENABLE_FULL_BYOC_MODE", "true")
    get_settings.cache_clear()

    def _plan(_self, context):
        return TerraformPlanResult(
            ok=True,
            command=["terraform", "plan", context.stage],
            plan_path=f"/tmp/{context.stage}.tfplan",
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    def _apply(_self, context, _plan_result):
        outputs = {}
        if context.stage == "provisioning_emr":
            outputs = {
                "eks_cluster_arn": {"value": "arn:aws:eks:us-east-1:123456789012:cluster/full-byoc-bootstrap"},
                "emr_virtual_cluster_id": {"value": "vc-fullbyocbootstrap"},
            }
        return TerraformApplyResult(
            ok=True,
            command=["terraform", "apply", context.stage],
            stdout_excerpt="ok",
            stderr_excerpt="",
            outputs=outputs,
        )

    def _oidc_missing(_self, _environment):
        return {
            "associated": False,
            "cluster_name": "full-byoc-bootstrap",
            "oidc_provider_arn": "arn:aws:iam::123456789012:oidc-provider/example",
        }

    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.plan", _plan)
    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.apply", _apply)
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.check_oidc_provider_association", _oidc_missing)

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Bootstrap Validation Failure Tenant"},
        headers={"Idempotency-Key": "tenant-bootstrap-fail", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "full",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-bootstrap-fail", "X-Actor": "test-user"},
    ).json()

    with SessionLocal() as db:
        process_provisioning_once(db)

    env_status = client.get(f"/v1/environments/{op['environment_id']}").json()
    assert env_status["status"] == "failed"

    op_status = client.get(f"/v1/provisioning-operations/{op['id']}").json()
    assert op_status["state"] == "failed"
    assert "oidc provider association is missing" in (op_status["message"] or "").lower()
    assert "eksctl utils associate-iam-oidc-provider" in (op_status["message"] or "")

    with SessionLocal() as db:
        checkpoints = list(
            db.execute(
                select(AuditEvent).where(
                    and_(
                        AuditEvent.action == "environment.full_byoc_checkpoint",
                        AuditEvent.entity_id == op["environment_id"],
                    )
                ).order_by(AuditEvent.created_at.desc())
            ).scalars()
        )
        assert len(checkpoints) >= 1
        checkpoint = checkpoints[0].details_json.get("checkpoint")
        assert isinstance(checkpoint, dict)
        assert checkpoint.get("last_successful_stage") == "provisioning_emr"
        attempts = checkpoint.get("attempt_count_by_stage", {})
        assert attempts.get("validating_bootstrap") == 1


def test_full_byoc_runtime_validation_failure_resumes_without_replaying_terraform(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ENABLE_FULL_BYOC_MODE", "true")
    get_settings.cache_clear()
    plan_calls: list[str] = []
    apply_calls: list[str] = []
    dispatch_ready = {"pass": False}

    def _plan(_self, context):
        plan_calls.append(context.stage)
        return TerraformPlanResult(
            ok=True,
            command=["terraform", "plan", context.stage],
            plan_path=f"/tmp/{context.stage}.tfplan",
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    def _apply(_self, context, _plan_result):
        apply_calls.append(context.stage)
        outputs = {}
        if context.stage == "provisioning_emr":
            outputs = {
                "eks_cluster_arn": {"value": "arn:aws:eks:us-east-1:123456789012:cluster/full-byoc-runtime"},
                "emr_virtual_cluster_id": {"value": "vc-fullbyocruntime"},
            }
        return TerraformApplyResult(
            ok=True,
            command=["terraform", "apply", context.stage],
            stdout_excerpt="ok",
            stderr_excerpt="",
            outputs=outputs,
        )

    def _dispatch_readiness(_self, _environment):
        if dispatch_ready["pass"]:
            return {
                "dispatch_actions_allowed": True,
                "pass_role_allowed": True,
                "denied_dispatch_actions": "",
                "execution_role_arn": "arn:aws:iam::123456789012:role/SparkPilotEmrExecutionRole",
            }
        return {
            "dispatch_actions_allowed": False,
            "pass_role_allowed": False,
            "denied_dispatch_actions": "emr-containers:StartJobRun",
            "execution_role_arn": "arn:aws:iam::123456789012:role/SparkPilotEmrExecutionRole",
        }

    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.plan", _plan)
    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.apply", _apply)
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.check_customer_role_dispatch_permissions", _dispatch_readiness)

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Runtime Validation Resume Tenant"},
        headers={"Idempotency-Key": "tenant-runtime-resume", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "full",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-runtime-resume", "X-Actor": "test-user"},
    ).json()

    with SessionLocal() as db:
        process_provisioning_once(db)

    env_status = client.get(f"/v1/environments/{op['environment_id']}").json()
    assert env_status["status"] == "failed"
    op_status = client.get(f"/v1/provisioning-operations/{op['id']}").json()
    assert "dispatch readiness is incomplete" in (op_status["message"] or "").lower()
    assert plan_calls == ["provisioning_network", "provisioning_eks", "provisioning_emr"]
    assert apply_calls == ["provisioning_network", "provisioning_eks", "provisioning_emr"]

    with SessionLocal() as db:
        checkpoints = list(
            db.execute(
                select(AuditEvent).where(
                    and_(
                        AuditEvent.action == "environment.full_byoc_checkpoint",
                        AuditEvent.entity_id == op["environment_id"],
                    )
                ).order_by(AuditEvent.created_at.desc())
            ).scalars()
        )
        assert len(checkpoints) >= 1
        checkpoint = checkpoints[0].details_json.get("checkpoint")
        assert isinstance(checkpoint, dict)
        assert checkpoint.get("last_successful_stage") == "validating_bootstrap"

    plan_calls.clear()
    apply_calls.clear()
    dispatch_ready["pass"] = True

    with SessionLocal() as db:
        op_row = db.get(ProvisioningOperation, op["id"])
        assert op_row is not None
        op_row.state = "validating_runtime"
        op_row.step = "validating_runtime"
        env_row = db.get(Environment, op["environment_id"])
        assert env_row is not None
        env_row.status = "provisioning"
        db.commit()

    with SessionLocal() as db:
        process_provisioning_once(db)

    env_status = client.get(f"/v1/environments/{op['environment_id']}").json()
    assert env_status["status"] == "ready"
    assert plan_calls == []
    assert apply_calls == []


def test_quota_enforcement() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Quota Inc"},
        headers={"Idempotency-Key": "tenant-q", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 1, "max_vcpu": 4, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-q", "X-Actor": "test-user"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)
    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": "job-q",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
        },
        headers={"Idempotency-Key": "job-q", "X-Actor": "test-user"},
    ).json()
    first = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"requested_resources": {"driver_vcpu": 1, "driver_memory_gb": 4, "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1}},
        headers={"Idempotency-Key": "run-q-1", "X-Actor": "test-user"},
    )
    assert first.status_code == 201
    second = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"requested_resources": {"driver_vcpu": 1, "driver_memory_gb": 4, "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1}},
        headers={"Idempotency-Key": "run-q-2", "X-Actor": "test-user"},
    )
    assert second.status_code == 429


def test_byoc_lite_environment_flow() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "BYOC Lite Tenant"},
        headers={"Idempotency-Key": "tenant-bl", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team-a",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-bl-1", "X-Actor": "test-user"},
    )
    assert op.status_code == 201

    with SessionLocal() as db:
        processed = process_provisioning_once(db)
    assert processed == 1

    env = client.get(f"/v1/environments/{op.json()['environment_id']}").json()
    assert env["status"] == "ready"
    assert env["provisioning_mode"] == "byoc_lite"
    assert env["eks_cluster_arn"].endswith("cluster/customer-shared")
    assert env["eks_namespace"] == "sparkpilot-team-a"
    assert env["emr_virtual_cluster_id"] is not None


def test_byoc_lite_provisioning_records_trust_policy_update_audit(monkeypatch) -> None:
    monkeypatch.setattr(
        "sparkpilot.services.EmrEksClient.check_oidc_provider_association",
        lambda *_args, **_kwargs: {
            "associated": True,
            "cluster_name": "customer-shared",
            "oidc_issuer": "https://oidc.eks.us-east-1.amazonaws.com/id/TEST",
            "oidc_provider_arn": "arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/TEST",
        },
    )
    monkeypatch.setattr(
        "sparkpilot.services.EmrEksClient.update_execution_role_trust_policy",
        lambda *_args, **_kwargs: {
            "updated": True,
            "cluster_name": "customer-shared",
            "namespace": "sparkpilot-team-a",
            "role_name": "SparkPilotEmrExecutionRole",
            "aws_request_id": "req-trust-1",
        },
    )

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "BYOC Lite Trust Policy Tenant"},
        headers={"Idempotency-Key": "tenant-bl-trust", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team-a",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-bl-trust", "X-Actor": "test-user"},
    )
    assert op.status_code == 201

    with SessionLocal() as db:
        processed = process_provisioning_once(db)
        assert processed == 1
        audit = db.execute(
            select(AuditEvent).where(
                and_(
                    AuditEvent.entity_type == "environment",
                    AuditEvent.entity_id == op.json()["environment_id"],
                    AuditEvent.action == "environment.byoc_lite_trust_policy_updated",
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
        result = audit.details_json.get("result")
        assert isinstance(result, dict)
        assert result.get("updated") is True
        assert result.get("role_name") == "SparkPilotEmrExecutionRole"

    env = client.get(f"/v1/environments/{op.json()['environment_id']}").json()
    assert env["status"] == "ready"


def test_byoc_lite_trust_policy_access_denied_fails_with_remediation(monkeypatch) -> None:
    monkeypatch.setattr(
        "sparkpilot.services.EmrEksClient.check_oidc_provider_association",
        lambda *_args, **_kwargs: {
            "associated": True,
            "cluster_name": "customer-shared",
            "oidc_issuer": "https://oidc.eks.us-east-1.amazonaws.com/id/TEST",
            "oidc_provider_arn": "arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/TEST",
        },
    )

    def _raise_access_denied(*_args, **_kwargs):
        raise ValueError(
            "Access denied while updating execution role trust policy. "
            "Required permissions: eks:DescribeCluster, "
            "iam:GetRole, iam:UpdateAssumeRolePolicy. "
            "Remediation: run `aws emr-containers update-role-trust-policy --cluster-name customer-shared "
            "--namespace sparkpilot-team-a --role-name SparkPilotEmrExecutionRole --region us-east-1` "
            "with an admin role, or grant the permissions above to customer_role_arn."
        )

    monkeypatch.setattr(
        "sparkpilot.services.EmrEksClient.update_execution_role_trust_policy",
        _raise_access_denied,
    )

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "BYOC Lite Trust Denied Tenant"},
        headers={"Idempotency-Key": "tenant-bl-trust-denied", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team-a",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-bl-trust-denied", "X-Actor": "test-user"},
    )
    assert op.status_code == 201

    with SessionLocal() as db:
        processed = process_provisioning_once(db)
        assert processed == 1
        trust_failure = db.execute(
            select(AuditEvent).where(
                and_(
                    AuditEvent.entity_type == "environment",
                    AuditEvent.entity_id == op.json()["environment_id"],
                    AuditEvent.action == "environment.byoc_lite_trust_policy_failed",
                )
            )
        ).scalar_one_or_none()
        assert trust_failure is not None
        error = str(trust_failure.details_json.get("error"))
        assert "iam:GetRole" in error
        assert "aws emr-containers update-role-trust-policy" in error

    op_status = client.get(f"/v1/provisioning-operations/{op.json()['id']}").json()
    assert op_status["state"] == "failed"
    assert "iam:UpdateAssumeRolePolicy" in (op_status["message"] or "")
    assert "aws emr-containers update-role-trust-policy" in (op_status["message"] or "")

    env = client.get(f"/v1/environments/{op.json()['environment_id']}").json()
    assert env["status"] == "failed"


def test_byoc_lite_oidc_missing_fails_before_trust_update(monkeypatch) -> None:
    monkeypatch.setattr(
        "sparkpilot.services.EmrEksClient.check_oidc_provider_association",
        lambda *_args, **_kwargs: {
            "associated": False,
            "cluster_name": "customer-shared",
            "oidc_issuer": "https://oidc.eks.us-east-1.amazonaws.com/id/MISSING",
            "oidc_provider_arn": "arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/MISSING",
        },
    )

    def _trust_should_not_run(*_args, **_kwargs):
        raise AssertionError("Trust policy update should not run when OIDC is missing")

    monkeypatch.setattr(
        "sparkpilot.services.EmrEksClient.update_execution_role_trust_policy",
        _trust_should_not_run,
    )

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "BYOC Lite OIDC Missing Tenant"},
        headers={"Idempotency-Key": "tenant-bl-oidc-missing", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team-a",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-bl-oidc-missing", "X-Actor": "test-user"},
    )
    assert op.status_code == 201

    with SessionLocal() as db:
        processed = process_provisioning_once(db)
        assert processed == 1
        oidc_check = db.execute(
            select(AuditEvent).where(
                and_(
                    AuditEvent.entity_type == "environment",
                    AuditEvent.entity_id == op.json()["environment_id"],
                    AuditEvent.action == "environment.byoc_lite_oidc_checked",
                )
            )
        ).scalar_one_or_none()
        assert oidc_check is not None
        result = oidc_check.details_json.get("result")
        assert isinstance(result, dict)
        assert result.get("associated") is False

    op_status = client.get(f"/v1/provisioning-operations/{op.json()['id']}").json()
    assert op_status["state"] == "failed"
    assert "OIDC provider is not associated" in (op_status["message"] or "")
    assert "eksctl utils associate-iam-oidc-provider" in (op_status["message"] or "")

    env = client.get(f"/v1/environments/{op.json()['environment_id']}").json()
    assert env["status"] == "failed"


def test_byoc_lite_environment_validation_errors() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "BYOC Lite Validation Tenant"},
        headers={"Idempotency-Key": "tenant-blv", "X-Actor": "test-user"},
    ).json()

    missing_cluster = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_namespace": "sparkpilot-team-a",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-blv-1", "X-Actor": "test-user"},
    )
    assert missing_cluster.status_code == 422
    assert missing_cluster.json()["detail"] == "eks_cluster_arn is required for byoc_lite."

    missing_namespace = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-blv-2", "X-Actor": "test-user"},
    )
    assert missing_namespace.status_code == 422
    assert missing_namespace.json()["detail"] == "eks_namespace is required for byoc_lite."


def test_environment_preflight_endpoint_returns_checks() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Preflight Tenant"},
        headers={"Idempotency-Key": "tenant-pf", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team-a",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-pf-1", "X-Actor": "test-user"},
    )
    assert op.status_code == 201
    with SessionLocal() as db:
        process_provisioning_once(db)

    preflight = client.get(f"/v1/environments/{op.json()['environment_id']}/preflight")
    assert preflight.status_code == 200
    payload = preflight.json()
    assert payload["ready"] is True
    assert payload["run_id"] is None
    codes = {item["code"] for item in payload["checks"]}
    assert "config.execution_role" in codes
    assert "byoc_lite.oidc_association" in codes
    assert "byoc_lite.customer_role_dispatch" in codes
    assert "byoc_lite.iam_pass_role" in codes
    assert "byoc_lite.execution_role_trust" in codes
    execution_role_check = next((item for item in payload["checks"] if item["code"] == "config.execution_role"), None)
    assert execution_role_check is not None
    assert "execution_role_arn" in execution_role_check["details"]


def test_environment_preflight_endpoint_accepts_run_id_query() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Preflight Run Query Tenant"},
        headers={"Idempotency-Key": "tenant-pf-run", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team-a",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-pf-run", "X-Actor": "test-user"},
    )
    assert op.status_code == 201
    with SessionLocal() as db:
        process_provisioning_once(db)

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op.json()["environment_id"],
            "name": "job-pf-run",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
            "spark_conf": {
                "spark.kubernetes.executor.node.selector.eks.amazonaws.com/capacityType": "SPOT",
                "spark.kubernetes.executor.tolerations": "spot=true:NoSchedule",
            },
        },
        headers={"Idempotency-Key": "job-pf-run", "X-Actor": "test-user"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={
            "spark_conf_overrides": {},
            "requested_resources": {
                "driver_vcpu": 1,
                "driver_memory_gb": 2,
                "executor_vcpu": 1,
                "executor_memory_gb": 2,
                "executor_instances": 1,
            },
        },
        headers={"Idempotency-Key": "run-pf-run", "X-Actor": "test-user"},
    ).json()

    run_id = run["id"]
    preflight = client.get(f"/v1/environments/{op.json()['environment_id']}/preflight?run_id={run_id}")
    assert preflight.status_code == 200
    payload = preflight.json()
    assert payload["environment_id"] == op.json()["environment_id"]
    assert payload["run_id"] == run_id
    assert isinstance(payload["checks"], list)
    assert all("code" in item and "status" in item for item in payload["checks"])
    spot_check = next(item for item in payload["checks"] if item["code"] == "byoc_lite.spot_executor_placement")
    assert spot_check["status"] == "pass"


def test_environment_preflight_rejects_run_id_from_another_environment() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Preflight Run Mismatch Tenant"},
        headers={"Idempotency-Key": "tenant-pf-mismatch", "X-Actor": "test-user"},
    ).json()

    env_a = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team-a",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-pf-mismatch-a", "X-Actor": "test-user"},
    ).json()
    env_b = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team-b",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-pf-mismatch-b", "X-Actor": "test-user"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)
        process_provisioning_once(db)

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": env_a["environment_id"],
            "name": "job-pf-mismatch",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
        },
        headers={"Idempotency-Key": "job-pf-mismatch", "X-Actor": "test-user"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={
            "requested_resources": {
                "driver_vcpu": 1,
                "driver_memory_gb": 2,
                "executor_vcpu": 1,
                "executor_memory_gb": 2,
                "executor_instances": 1,
            },
        },
        headers={"Idempotency-Key": "run-pf-mismatch", "X-Actor": "test-user"},
    ).json()

    response = client.get(f"/v1/environments/{env_b['environment_id']}/preflight?run_id={run['id']}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Run not found for this environment."


def test_environment_preflight_spot_warnings_when_spot_nodegroups_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "sparkpilot.services.EmrEksClient.describe_nodegroups",
        lambda *_args, **_kwargs: [
            {
                "name": "on-demand-ng",
                "capacity_type": "ON_DEMAND",
                "instance_types": ["m7i.xlarge"],
                "desired_size": 2,
            }
        ],
    )

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Preflight Spot Warning Tenant"},
        headers={"Idempotency-Key": "tenant-pf-spot-warn", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team-a",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-pf-spot-warn", "X-Actor": "test-user"},
    )
    assert op.status_code == 201
    with SessionLocal() as db:
        process_provisioning_once(db)

    preflight = client.get(f"/v1/environments/{op.json()['environment_id']}/preflight")
    assert preflight.status_code == 200
    payload = preflight.json()
    checks = {item["code"]: item for item in payload["checks"]}
    assert checks["byoc_lite.spot_capacity"]["status"] == "warning"
    assert checks["byoc_lite.spot_diversification"]["status"] == "warning"

def test_scheduler_blocks_dispatch_on_preflight_failure() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Scheduler Preflight Tenant"},
        headers={"Idempotency-Key": "tenant-spf", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-spf", "X-Actor": "test-user"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": "job-spf",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
        },
        headers={"Idempotency-Key": "job-spf", "X-Actor": "test-user"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"requested_resources": {"driver_vcpu": 1, "driver_memory_gb": 4, "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1}},
        headers={"Idempotency-Key": "run-spf", "X-Actor": "test-user"},
    ).json()

    with SessionLocal() as db:
        env = db.get(Environment, op["environment_id"])
        assert env is not None
        env.emr_virtual_cluster_id = None
        db.commit()
        process_scheduler_once(db)

    run_payload = client.get(f"/v1/runs/{run['id']}").json()
    assert run_payload["state"] == "failed"
    assert "Preflight failed" in (run_payload["error_message"] or "")


def test_scheduler_blocks_dispatch_when_customer_role_dispatch_check_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "sparkpilot.services.EmrEksClient.check_customer_role_dispatch_permissions",
        lambda *_args, **_kwargs: {
            "dispatch_actions_allowed": False,
            "pass_role_allowed": False,
            "denied_dispatch_actions": "emr-containers:StartJobRun",
            "execution_role_arn": "arn:aws:iam::123456789012:role/SparkPilotEmrExecutionRole",
        },
    )

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Scheduler Dispatch Policy Tenant"},
        headers={"Idempotency-Key": "tenant-spf-dispatch", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-spf-dispatch", "X-Actor": "test-user"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": "job-spf-dispatch",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
        },
        headers={"Idempotency-Key": "job-spf-dispatch", "X-Actor": "test-user"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"requested_resources": {"driver_vcpu": 1, "driver_memory_gb": 4, "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1}},
        headers={"Idempotency-Key": "run-spf-dispatch", "X-Actor": "test-user"},
    ).json()

    with SessionLocal() as db:
        process_scheduler_once(db)

    run_payload = client.get(f"/v1/runs/{run['id']}").json()
    assert run_payload["state"] == "failed"
    assert "byoc_lite.customer_role_dispatch" in (run_payload["error_message"] or "")


def test_byoc_lite_provisioning_prerequisite_failures_are_actionable() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "BYOC Lite Prereq Failure Tenant"},
        headers={"Idempotency-Key": "tenant-prereq-fail", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::111111111111:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:222222222222:cluster/customer-shared",
            "eks_namespace": "SparkPilot-Team",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-prereq-fail", "X-Actor": "test-user"},
    )
    assert op.status_code == 201

    with SessionLocal() as db:
        processed = process_provisioning_once(db)
        assert processed == 1
        audit = db.execute(
            select(AuditEvent).where(
                and_(
                    AuditEvent.entity_type == "environment",
                    AuditEvent.entity_id == op.json()["environment_id"],
                    AuditEvent.action == "environment.byoc_lite_prerequisites_evaluated",
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
        details = audit.details_json
        assert details.get("ready") is False
        checks = details.get("checks")
        assert isinstance(checks, list)
        codes = {item.get("code") for item in checks if isinstance(item, dict)}
        assert "byoc_lite.eks_namespace_format" in codes
        assert "byoc_lite.account_alignment" in codes

    op_status = client.get(f"/v1/provisioning-operations/{op.json()['id']}").json()
    assert op_status["state"] == "failed"
    assert op_status["step"] == "failed"
    assert "BYOC-Lite prerequisites failed" in (op_status["message"] or "")
    assert "Remediation:" in (op_status["message"] or "")

    env = client.get(f"/v1/environments/{op.json()['environment_id']}").json()
    assert env["status"] == "failed"


def test_byoc_lite_namespace_length_over_63_fails_prerequisites() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "BYOC Lite Namespace Length Tenant"},
        headers={"Idempotency-Key": "tenant-ns-len", "X-Actor": "test-user"},
    ).json()
    namespace = "a" * 64
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": namespace,
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-ns-len", "X-Actor": "test-user"},
    )
    assert op.status_code == 201

    with SessionLocal() as db:
        processed = process_provisioning_once(db)
        assert processed == 1
        audit = db.execute(
            select(AuditEvent).where(
                and_(
                    AuditEvent.entity_type == "environment",
                    AuditEvent.entity_id == op.json()["environment_id"],
                    AuditEvent.action == "environment.byoc_lite_prerequisites_evaluated",
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
        checks = audit.details_json.get("checks")
        assert isinstance(checks, list)
        failing_namespace_check = next(
            (
                item
                for item in checks
                if isinstance(item, dict) and item.get("code") == "byoc_lite.eks_namespace_format"
            ),
            None,
        )
        assert failing_namespace_check is not None
        assert failing_namespace_check.get("status") == "fail"

    op_status = client.get(f"/v1/provisioning-operations/{op.json()['id']}").json()
    assert op_status["state"] == "failed"
    assert "max 63 chars" in (op_status["message"] or "")


def test_byoc_lite_namespace_collision_fails_fast_with_remediation(monkeypatch) -> None:
    monkeypatch.setattr(
        "sparkpilot.services.EmrEksClient.find_namespace_virtual_cluster_collision",
        lambda *_args, **_kwargs: {"id": "vc-collision", "name": "existing", "state": "RUNNING"},
    )

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "BYOC Lite Namespace Collision Tenant"},
        headers={"Idempotency-Key": "tenant-ns-collision", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-team",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-ns-collision", "X-Actor": "test-user"},
    )
    assert op.status_code == 201

    with SessionLocal() as db:
        processed = process_provisioning_once(db)
        assert processed == 1
        collision_audit = db.execute(
            select(AuditEvent).where(
                and_(
                    AuditEvent.entity_type == "environment",
                    AuditEvent.entity_id == op.json()["environment_id"],
                    AuditEvent.action == "environment.byoc_lite_namespace_collision",
                )
            )
        ).scalar_one_or_none()
        assert collision_audit is not None
        details = collision_audit.details_json
        assert details.get("collision_virtual_cluster_id") == "vc-collision"
        assert details.get("eks_namespace") == "sparkpilot-team"

    op_status = client.get(f"/v1/provisioning-operations/{op.json()['id']}").json()
    assert op_status["state"] == "failed"
    assert "BYOC-Lite namespace collision detected" in (op_status["message"] or "")
    assert "Remediation:" in (op_status["message"] or "")

    env = client.get(f"/v1/environments/{op.json()['environment_id']}").json()
    assert env["status"] == "failed"


def test_reconciler_marks_submitted_run_stale(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_SUBMITTED_STALE_MINUTES", "1")
    get_settings.cache_clear()

    def _submitted_state(*_args, **_kwargs):
        return "SUBMITTED", None

    monkeypatch.setattr("sparkpilot.services.EmrEksClient.describe_job_run", _submitted_state)

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Stale Submitted Tenant"},
        headers={"Idempotency-Key": "tenant-stale", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-stale", "X-Actor": "test-user"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": "job-stale",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
        },
        headers={"Idempotency-Key": "job-stale", "X-Actor": "test-user"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"requested_resources": {"driver_vcpu": 1, "driver_memory_gb": 4, "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1}},
        headers={"Idempotency-Key": "run-stale", "X-Actor": "test-user"},
    ).json()

    with SessionLocal() as db:
        row = db.get(Run, run["id"])
        assert row is not None
        row.state = "accepted"
        row.emr_job_run_id = "jr-stale"
        row.started_at = datetime.now(UTC) - timedelta(minutes=5)
        db.commit()
        process_reconciler_once(db)
        diagnostic = db.execute(
            select(AuditEvent).where(
                and_(
                    AuditEvent.entity_type == "run",
                    AuditEvent.entity_id == run["id"],
                    AuditEvent.action == "run.preflight_diagnostic",
                )
            )
        ).scalar_one_or_none()
        assert diagnostic is not None

    stale = client.get(f"/v1/runs/{run['id']}").json()
    assert stale["state"] == "failed"
    assert "EMR SUBMITTED" in (stale["error_message"] or "")
    get_settings.cache_clear()


def test_reconciler_marks_accepted_run_stale(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ACCEPTED_STALE_MINUTES", "1")
    get_settings.cache_clear()

    def _pending_state(*_args, **_kwargs):
        return "PENDING", None

    monkeypatch.setattr("sparkpilot.services.EmrEksClient.describe_job_run", _pending_state)

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Stale Accepted Tenant"},
        headers={"Idempotency-Key": "tenant-accepted", "X-Actor": "test-user"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-accepted", "X-Actor": "test-user"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": "job-accepted",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
        },
        headers={"Idempotency-Key": "job-accepted", "X-Actor": "test-user"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"requested_resources": {"driver_vcpu": 1, "driver_memory_gb": 4, "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1}},
        headers={"Idempotency-Key": "run-accepted", "X-Actor": "test-user"},
    ).json()

    with SessionLocal() as db:
        row = db.get(Run, run["id"])
        assert row is not None
        row.state = "accepted"
        row.emr_job_run_id = "jr-accepted"
        row.started_at = datetime.now(UTC) - timedelta(minutes=20)
        db.commit()
        process_reconciler_once(db)

    stale = client.get(f"/v1/runs/{run['id']}").json()
    assert stale["state"] == "failed"
    assert "accepted state for more than 1 minutes" in (stale["error_message"] or "")
    get_settings.cache_clear()


def test_scheduler_retries_transient_dispatch_failure(monkeypatch) -> None:
    class _TransientDispatchError(Exception):
        def __init__(self) -> None:
            self.response = {
                "Error": {
                    "Code": "ThrottlingException",
                    "Message": "Rate exceeded",
                }
            }
            super().__init__("ThrottlingException: Rate exceeded")

    calls = {"count": 0}

    def _start_job_run(_self, environment, job, run):
        calls["count"] += 1
        if calls["count"] == 1:
            raise _TransientDispatchError()
        return EmrDispatchResult(
            emr_job_run_id="jr-retry-success",
            log_group=f"/sparkpilot/runs/{environment.id}",
            log_stream_prefix=f"{run.id}/attempt-{run.attempt}",
            driver_log_uri=f"cloudwatch:///sparkpilot/runs/{environment.id}/{run.id}/attempt-{run.attempt}/driver",
            spark_ui_uri=None,
        )

    monkeypatch.setattr("sparkpilot.services.EmrEksClient.start_job_run", _start_job_run)

    client = TestClient(app)
    _, _, _, run = _create_ready_environment_and_run(client, suffix="retry-transient", retry_max_attempts=2)

    with SessionLocal() as db:
        processed = process_scheduler_once(db)
        assert processed == 1
        retry_audit = db.execute(
            select(AuditEvent).where(
                and_(
                    AuditEvent.entity_type == "run",
                    AuditEvent.entity_id == run["id"],
                    AuditEvent.action == "run.dispatch_retry_scheduled",
                )
            )
        ).scalar_one_or_none()
        assert retry_audit is not None

    retried = client.get(f"/v1/runs/{run['id']}").json()
    assert retried["state"] == "queued"
    assert retried["attempt"] == 2
    assert "Retry scheduled as attempt 2." in (retried["error_message"] or "")

    with SessionLocal() as db:
        processed = process_scheduler_once(db)
        assert processed == 1

    accepted = client.get(f"/v1/runs/{run['id']}").json()
    assert accepted["state"] == "accepted"
    assert accepted["attempt"] == 2
    assert accepted["emr_job_run_id"] == "jr-retry-success"


def test_scheduler_fails_non_transient_dispatch_without_retry(monkeypatch) -> None:
    def _start_job_run(*_args, **_kwargs):
        raise ValueError("AccessDenied: emr-containers:StartJobRun")

    monkeypatch.setattr("sparkpilot.services.EmrEksClient.start_job_run", _start_job_run)

    client = TestClient(app)
    _, _, _, run = _create_ready_environment_and_run(client, suffix="retry-nontransient", retry_max_attempts=3)

    with SessionLocal() as db:
        processed = process_scheduler_once(db)
        assert processed == 1
        failure_audit = db.execute(
            select(AuditEvent).where(
                and_(
                    AuditEvent.entity_type == "run",
                    AuditEvent.entity_id == run["id"],
                    AuditEvent.action == "run.dispatch_failed",
                )
            )
        ).scalar_one_or_none()
        assert failure_audit is not None
        assert failure_audit.details_json.get("transient") is False

    failed = client.get(f"/v1/runs/{run['id']}").json()
    assert failed["state"] == "failed"
    assert failed["attempt"] == 1
    assert "AccessDenied" in (failed["error_message"] or "")


def test_scheduler_exhausts_transient_dispatch_retries(monkeypatch) -> None:
    class _TransientDispatchError(Exception):
        def __init__(self) -> None:
            self.response = {
                "Error": {
                    "Code": "ServiceUnavailableException",
                    "Message": "Service unavailable",
                }
            }
            super().__init__("ServiceUnavailableException: temporary outage")

    def _start_job_run(*_args, **_kwargs):
        raise _TransientDispatchError()

    monkeypatch.setattr("sparkpilot.services.EmrEksClient.start_job_run", _start_job_run)

    client = TestClient(app)
    _, _, _, run = _create_ready_environment_and_run(client, suffix="retry-exhausted", retry_max_attempts=2)

    with SessionLocal() as db:
        processed = process_scheduler_once(db)
        assert processed == 1

    first_retry = client.get(f"/v1/runs/{run['id']}").json()
    assert first_retry["state"] == "queued"
    assert first_retry["attempt"] == 2

    with SessionLocal() as db:
        processed = process_scheduler_once(db)
        assert processed == 1
        failure_audit = db.execute(
            select(AuditEvent).where(
                and_(
                    AuditEvent.entity_type == "run",
                    AuditEvent.entity_id == run["id"],
                    AuditEvent.action == "run.dispatch_failed",
                )
            )
        ).scalar_one_or_none()
        assert failure_audit is not None
        assert failure_audit.details_json.get("transient") is True

    final = client.get(f"/v1/runs/{run['id']}").json()
    assert final["state"] == "failed"
    assert final["attempt"] == 2
    assert "ServiceUnavailableException" in (final["error_message"] or "")


def test_cancel_run_from_queued_is_immediate() -> None:
    client = TestClient(app)
    _, _, _, run = _create_ready_environment_and_run(client, suffix="cancel-queued", retry_max_attempts=1)

    cancelled = client.post(
        f"/v1/runs/{run['id']}/cancel",
        headers={"Idempotency-Key": "cancel-queued", "X-Actor": "test-user"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert cancelled.json()["cancellation_requested"] is False


def test_cancel_run_from_accepted_transitions_to_cancelled(monkeypatch) -> None:
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.cancel_job_run", lambda *_args, **_kwargs: "req-cancel-accepted")
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.describe_job_run", lambda *_args, **_kwargs: ("CANCELLED", None))

    client = TestClient(app)
    _, _, _, run = _create_ready_environment_and_run(client, suffix="cancel-accepted", retry_max_attempts=1)

    with SessionLocal() as db:
        row = db.get(Run, run["id"])
        assert row is not None
        row.state = "accepted"
        row.emr_job_run_id = "jr-cancel-accepted"
        row.started_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    cancel_response = client.post(
        f"/v1/runs/{run['id']}/cancel",
        headers={"Idempotency-Key": "cancel-accepted", "X-Actor": "test-user"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["state"] == "accepted"
    assert cancel_response.json()["cancellation_requested"] is True

    with SessionLocal() as db:
        processed = process_reconciler_once(db)
        assert processed == 1
        cancel_dispatched = db.execute(
            select(AuditEvent).where(
                and_(
                    AuditEvent.entity_type == "run",
                    AuditEvent.entity_id == run["id"],
                    AuditEvent.action == "run.cancel.dispatched",
                )
            )
        ).scalar_one_or_none()
        assert cancel_dispatched is not None

    final = client.get(f"/v1/runs/{run['id']}").json()
    assert final["state"] == "cancelled"


def test_cancel_run_from_running_transitions_to_cancelled(monkeypatch) -> None:
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.cancel_job_run", lambda *_args, **_kwargs: "req-cancel-running")
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.describe_job_run", lambda *_args, **_kwargs: ("CANCELLED", None))

    client = TestClient(app)
    _, _, _, run = _create_ready_environment_and_run(client, suffix="cancel-running", retry_max_attempts=1)

    with SessionLocal() as db:
        row = db.get(Run, run["id"])
        assert row is not None
        row.state = "running"
        row.emr_job_run_id = "jr-cancel-running"
        row.started_at = datetime.now(UTC) - timedelta(minutes=3)
        db.commit()

    cancel_response = client.post(
        f"/v1/runs/{run['id']}/cancel",
        headers={"Idempotency-Key": "cancel-running", "X-Actor": "test-user"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["state"] == "running"
    assert cancel_response.json()["cancellation_requested"] is True

    with SessionLocal() as db:
        processed = process_reconciler_once(db)
        assert processed == 1

    final = client.get(f"/v1/runs/{run['id']}").json()
    assert final["state"] == "cancelled"


def test_structured_streaming_lifecycle_heartbeat_cancel_restart(monkeypatch) -> None:
    run_state_by_emr_id: dict[str, str] = {}

    def _start_job_run(_self, environment, _job, run):
        emr_id = f"jr-stream-{run.id[:8]}"
        run_state_by_emr_id[emr_id] = "RUNNING"
        return EmrDispatchResult(
            emr_job_run_id=emr_id,
            log_group=f"/sparkpilot/runs/{environment.id}",
            log_stream_prefix=f"{run.id}/attempt-{run.attempt}",
            driver_log_uri=f"cloudwatch:///sparkpilot/runs/{environment.id}/{run.id}/attempt-{run.attempt}/driver",
            spark_ui_uri=f"https://spark-ui.local/{run.id}",
            aws_request_id=f"req-{run.id[:8]}",
        )

    def _describe_job_run(_self, _environment, run):
        if not run.emr_job_run_id:
            return ("FAILED", "Missing emr_job_run_id")
        return (run_state_by_emr_id.get(run.emr_job_run_id, "RUNNING"), None)

    monkeypatch.setattr("sparkpilot.services.EmrEksClient.start_job_run", _start_job_run)
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.describe_job_run", _describe_job_run)
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.cancel_job_run", lambda *_args, **_kwargs: "req-stream-cancel")

    client = TestClient(app)
    _, _, job, run = _create_ready_environment_and_run(client, suffix="streaming-lifecycle", retry_max_attempts=2)

    # Dispatch queued run and reconcile to running.
    with SessionLocal() as db:
        assert process_scheduler_once(db) == 1
    with SessionLocal() as db:
        assert process_reconciler_once(db) == 1

    running = client.get(f"/v1/runs/{run['id']}").json()
    assert running["state"] == "running"
    assert running["last_heartbeat_at"] is not None
    first_heartbeat = datetime.fromisoformat(running["last_heartbeat_at"])
    first_emr_id = running["emr_job_run_id"]
    assert first_emr_id is not None

    # Simulate sustained runtime and verify heartbeat refresh.
    with SessionLocal() as db:
        row = db.get(Run, run["id"])
        assert row is not None
        row.last_heartbeat_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
    with SessionLocal() as db:
        assert process_reconciler_once(db) == 1

    running_again = client.get(f"/v1/runs/{run['id']}").json()
    assert running_again["state"] == "running"
    refreshed_heartbeat = datetime.fromisoformat(running_again["last_heartbeat_at"])
    assert refreshed_heartbeat > first_heartbeat

    # Logs remain accessible while run is still active.
    logs = client.get(
        f"/v1/runs/{run['id']}/logs",
        params={"limit": 25},
        headers={"X-Actor": "test-user"},
    )
    assert logs.status_code == 200
    assert logs.json()["log_group"] is not None
    assert len(logs.json()["lines"]) > 0

    # Cancellation is deterministic: request cancel, reconcile to cancelled.
    cancel_response = client.post(
        f"/v1/runs/{run['id']}/cancel",
        headers={"Idempotency-Key": "cancel-streaming-run", "X-Actor": "test-user"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["cancellation_requested"] is True
    run_state_by_emr_id[first_emr_id] = "CANCELLED"
    with SessionLocal() as db:
        assert process_reconciler_once(db) == 1
    cancelled = client.get(f"/v1/runs/{run['id']}").json()
    assert cancelled["state"] == "cancelled"
    assert cancelled["ended_at"] is not None

    # Restart semantics: submit a fresh run for the same job and observe running state.
    restarted = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"timeout_seconds": 3600},
        headers={"Idempotency-Key": "run-streaming-restart", "X-Actor": "test-user"},
    )
    assert restarted.status_code == 201
    restarted_run = restarted.json()
    assert restarted_run["id"] != run["id"]

    with SessionLocal() as db:
        assert process_scheduler_once(db) == 1
    with SessionLocal() as db:
        assert process_reconciler_once(db) == 1

    restarted_current = client.get(f"/v1/runs/{restarted_run['id']}").json()
    assert restarted_current["state"] == "running"
    assert restarted_current["last_heartbeat_at"] is not None


def test_multi_tenant_concurrent_runs_enforce_isolation_invariants(monkeypatch) -> None:
    def _start_job_run(_self, environment, job, run):
        return EmrDispatchResult(
            emr_job_run_id=f"jr-{environment.id[:8]}-{run.id[:8]}",
            log_group=f"/sparkpilot/runs/{environment.id}",
            log_stream_prefix=f"{run.id}/attempt-{run.attempt}",
            driver_log_uri=f"cloudwatch:///sparkpilot/runs/{environment.id}/{run.id}/attempt-{run.attempt}/driver",
            spark_ui_uri=None,
        )

    log_calls: list[dict[str, object]] = []

    def _fetch_lines(_self, *, role_arn, region, log_group, log_stream_prefix, limit):
        log_calls.append(
            {
                "role_arn": role_arn,
                "region": region,
                "log_group": log_group,
                "log_stream_prefix": log_stream_prefix,
                "limit": limit,
            }
        )
        return [f"{log_stream_prefix} line 1"]

    monkeypatch.setattr("sparkpilot.services.EmrEksClient.start_job_run", _start_job_run)
    monkeypatch.setattr("sparkpilot.services.CloudWatchLogsProxy.fetch_lines", _fetch_lines)

    client = TestClient(app)

    tenant_a = client.post(
        "/v1/tenants",
        json={"name": "Tenant Isolation A"},
        headers={"Idempotency-Key": "tenant-isolation-a", "X-Actor": "test-user"},
    ).json()
    tenant_b = client.post(
        "/v1/tenants",
        json={"name": "Tenant Isolation B"},
        headers={"Idempotency-Key": "tenant-isolation-b", "X-Actor": "test-user"},
    ).json()

    env_a_op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant_a["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::111111111111:role/SparkPilotCustomerRoleA",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-isolation-a", "X-Actor": "test-user"},
    ).json()
    env_b_op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant_b["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::222222222222:role/SparkPilotCustomerRoleB",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-isolation-b", "X-Actor": "test-user"},
    ).json()

    with SessionLocal() as db:
        processed = process_provisioning_once(db)
        assert processed == 2

    env_a = client.get(f"/v1/environments/{env_a_op['environment_id']}").json()
    env_b = client.get(f"/v1/environments/{env_b_op['environment_id']}").json()
    assert env_a["status"] == "ready"
    assert env_b["status"] == "ready"

    job_a = client.post(
        "/v1/jobs",
        json={
            "environment_id": env_a["id"],
            "name": "job-isolation-a",
            "artifact_uri": "s3://tenant-a/jobs/main.py",
            "artifact_digest": "sha256:aaa111",
            "entrypoint": "main.py",
            "args": ["s3://tenant-a/input/events.json", "s3://tenant-a/output/run-a/"],
        },
        headers={"Idempotency-Key": "job-isolation-a", "X-Actor": "test-user"},
    ).json()
    job_b = client.post(
        "/v1/jobs",
        json={
            "environment_id": env_b["id"],
            "name": "job-isolation-b",
            "artifact_uri": "s3://tenant-b/jobs/main.py",
            "artifact_digest": "sha256:bbb222",
            "entrypoint": "main.py",
            "args": ["s3://tenant-b/input/events.json", "s3://tenant-b/output/run-b/"],
        },
        headers={"Idempotency-Key": "job-isolation-b", "X-Actor": "test-user"},
    ).json()

    run_a = client.post(
        f"/v1/jobs/{job_a['id']}/runs",
        json={
            "requested_resources": {
                "driver_vcpu": 1,
                "driver_memory_gb": 4,
                "executor_vcpu": 1,
                "executor_memory_gb": 4,
                "executor_instances": 1,
            }
        },
        headers={"Idempotency-Key": "run-isolation-a", "X-Actor": "test-user"},
    ).json()
    run_b = client.post(
        f"/v1/jobs/{job_b['id']}/runs",
        json={
            "requested_resources": {
                "driver_vcpu": 1,
                "driver_memory_gb": 4,
                "executor_vcpu": 1,
                "executor_memory_gb": 4,
                "executor_instances": 1,
            }
        },
        headers={"Idempotency-Key": "run-isolation-b", "X-Actor": "test-user"},
    ).json()

    with SessionLocal() as db:
        scheduled = process_scheduler_once(db)
        assert scheduled == 2

    run_a_current = client.get(f"/v1/runs/{run_a['id']}").json()
    run_b_current = client.get(f"/v1/runs/{run_b['id']}").json()
    assert run_a_current["state"] == "accepted"
    assert run_b_current["state"] == "accepted"
    assert run_a_current["environment_id"] == env_a["id"]
    assert run_b_current["environment_id"] == env_b["id"]
    assert env_a["id"] in (run_a_current["log_group"] or "")
    assert env_b["id"] in (run_b_current["log_group"] or "")
    assert env_b["id"] not in (run_a_current["log_group"] or "")
    assert env_a["id"] not in (run_b_current["log_group"] or "")

    tenant_a_runs = client.get(f"/v1/runs?tenant_id={tenant_a['id']}").json()
    tenant_b_runs = client.get(f"/v1/runs?tenant_id={tenant_b['id']}").json()
    assert {item["id"] for item in tenant_a_runs} == {run_a["id"]}
    assert {item["id"] for item in tenant_b_runs} == {run_b["id"]}

    logs_a = client.get(f"/v1/runs/{run_a['id']}/logs")
    logs_b = client.get(f"/v1/runs/{run_b['id']}/logs")
    assert logs_a.status_code == 200
    assert logs_b.status_code == 200
    assert len(log_calls) == 2

    call_by_stream = {str(item["log_stream_prefix"]): item for item in log_calls}
    assert run_a_current["log_stream_prefix"] in call_by_stream
    assert run_b_current["log_stream_prefix"] in call_by_stream
    assert call_by_stream[run_a_current["log_stream_prefix"]]["role_arn"] == env_a["customer_role_arn"]
    assert call_by_stream[run_b_current["log_stream_prefix"]]["role_arn"] == env_b["customer_role_arn"]
    assert call_by_stream[run_a_current["log_stream_prefix"]]["log_group"] == run_a_current["log_group"]
    assert call_by_stream[run_b_current["log_stream_prefix"]]["log_group"] == run_b_current["log_group"]

    with SessionLocal() as db:
        dispatched_events = list(
            db.execute(
                select(AuditEvent).where(
                    and_(
                        AuditEvent.action == "run.dispatched",
                        AuditEvent.entity_id.in_([run_a["id"], run_b["id"]]),
                    )
                )
            ).scalars()
        )
        assert len(dispatched_events) == 2
        event_tenant_by_run = {event.entity_id: event.tenant_id for event in dispatched_events}
        assert event_tenant_by_run[run_a["id"]] == tenant_a["id"]
        assert event_tenant_by_run[run_b["id"]] == tenant_b["id"]


# ---------------------------------------------------------------------------
# Issue #51 – EMR Job Templates API
# ---------------------------------------------------------------------------

def test_create_job_template() -> None:
    client = TestClient(app)
    _, op, _, _ = _create_ready_environment_and_run(client, suffix="jt1")
    environment_id = op["environment_id"]

    resp = client.post(
        f"/v1/environments/{environment_id}/job-templates",
        json={
            "name": "my-spark-template",
            "description": "Daily ETL template",
            "job_driver": {
                "sparkSubmitJobDriver": {
                    "entryPoint": "s3://bucket/job.py",
                    "sparkSubmitParameters": "--conf spark.executor.cores=2",
                }
            },
            "configuration_overrides": {},
            "tags": {"team": "analytics"},
        },
        headers={"X-Actor": "test-user"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "my-spark-template"
    assert body["description"] == "Daily ETL template"
    assert body["environment_id"] == environment_id
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body
    # In dry_run_mode the emr_template_id is None
    assert "emr_template_id" in body


def test_list_job_templates_empty() -> None:
    client = TestClient(app)
    _, op, _, _ = _create_ready_environment_and_run(client, suffix="jt2")
    environment_id = op["environment_id"]

    resp = client.get(
        f"/v1/environments/{environment_id}/job-templates",
        headers={"X-Actor": "test-user"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_job_templates_returns_created() -> None:
    client = TestClient(app)
    _, op, _, _ = _create_ready_environment_and_run(client, suffix="jt3")
    environment_id = op["environment_id"]

    client.post(
        f"/v1/environments/{environment_id}/job-templates",
        json={"name": "template-alpha", "job_driver": {}, "configuration_overrides": {}, "tags": {}},
        headers={"X-Actor": "test-user"},
    )
    resp = client.get(
        f"/v1/environments/{environment_id}/job-templates",
        headers={"X-Actor": "test-user"},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "template-alpha"


# ---------------------------------------------------------------------------
# Issue #47 – Spark History Server link
# ---------------------------------------------------------------------------

def test_run_response_includes_spark_history_url() -> None:
    client = TestClient(app)
    _, op, job, run = _create_ready_environment_and_run(client, suffix="hist1")
    environment_id = op["environment_id"]

    # Set spark_history_server_url on the environment
    with SessionLocal() as db:
        env = db.get(Environment, environment_id)
        env.spark_history_server_url = "https://spark-history.example.com"
        db.commit()

    # Schedule the run so it gets an emr_job_run_id
    with SessionLocal() as db:
        process_scheduler_once(db)

    current = client.get(f"/v1/runs/{run['id']}", headers={"X-Actor": "test-user"}).json()
    assert "spark_history_url" in current
    # The run should have spark_ui_uri from dry-run OR the history server URL computed
    if current["spark_ui_uri"]:
        assert current["spark_history_url"] == current["spark_ui_uri"]
    elif current["emr_job_run_id"]:
        assert current["spark_history_url"] == (
            f"https://spark-history.example.com/history/{current['emr_job_run_id']}"
        )


# ---------------------------------------------------------------------------
# Issue #42 – YuniKorn queue scheduling
# ---------------------------------------------------------------------------

def test_yunikorn_queue_capacity_check_blocks_oversize_run() -> None:
    client = TestClient(app)
    _, op, job, _ = _create_ready_environment_and_run(client, suffix="yuni1")
    environment_id = op["environment_id"]

    # Set a very small YuniKorn queue max so the next run is blocked
    with SessionLocal() as db:
        env = db.get(Environment, environment_id)
        env.yunikorn_queue = "root.analytics"
        env.yunikorn_queue_max_vcpu = 2  # tiny limit
        db.commit()

    # Submit a run that requests more vCPU than the queue max
    oversize_run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={
            "requested_resources": {
                "driver_vcpu": 2,
                "driver_memory_gb": 4,
                "executor_vcpu": 4,
                "executor_memory_gb": 8,
                "executor_instances": 2,
            }
        },
        headers={"Idempotency-Key": "run-yuni-oversize", "X-Actor": "test-user"},
    )
    assert oversize_run.status_code == 201
    oversize_run_id = oversize_run.json()["id"]

    # Preflight for this run should flag the yunikorn_queue_capacity as fail
    preflight = client.get(
        f"/v1/environments/{environment_id}/preflight?run_id={oversize_run_id}",
        headers={"X-Actor": "test-user"},
    )
    assert preflight.status_code == 200
    pf = preflight.json()
    assert pf["ready"] is False
    check_codes = {c["code"] for c in pf["checks"]}
    assert "yunikorn_queue_capacity" in check_codes
    yunikorn_check = next(c for c in pf["checks"] if c["code"] == "yunikorn_queue_capacity")
    assert yunikorn_check["status"] == "fail"


def test_queue_utilization_endpoint() -> None:
    client = TestClient(app)
    _, op, _, _ = _create_ready_environment_and_run(client, suffix="qu1")
    environment_id = op["environment_id"]

    resp = client.get(
        f"/v1/environments/{environment_id}/queue-utilization",
        headers={"X-Actor": "test-user"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["environment_id"] == environment_id
    assert "active_run_count" in body
    assert "used_vcpu" in body
    assert "max_vcpu" in body


# ---------------------------------------------------------------------------
# Issue #41 – Interactive Endpoints (Managed Endpoints)
# ---------------------------------------------------------------------------

def test_create_interactive_endpoint() -> None:
    client = TestClient(app)
    _, op, _, _ = _create_ready_environment_and_run(client, suffix="ep1")
    environment_id = op["environment_id"]

    resp = client.post(
        f"/v1/environments/{environment_id}/endpoints",
        json={
            "name": "jupyter-endpoint",
            "execution_role_arn": "arn:aws:iam::123456789012:role/EmrExecutionRole",
            "release_label": "emr-6.15.0-latest",
            "idle_timeout_minutes": 30,
        },
        headers={"X-Actor": "test-user"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "jupyter-endpoint"
    assert body["release_label"] == "emr-6.15.0-latest"
    assert body["idle_timeout_minutes"] == 30
    assert body["status"] == "creating"
    assert body["environment_id"] == environment_id
    assert "id" in body


def test_list_interactive_endpoints_empty() -> None:
    client = TestClient(app)
    _, op, _, _ = _create_ready_environment_and_run(client, suffix="ep2")
    environment_id = op["environment_id"]

    resp = client.get(
        f"/v1/environments/{environment_id}/endpoints",
        headers={"X-Actor": "test-user"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_interactive_endpoints_returns_created() -> None:
    client = TestClient(app)
    _, op, _, _ = _create_ready_environment_and_run(client, suffix="ep3")
    environment_id = op["environment_id"]

    client.post(
        f"/v1/environments/{environment_id}/endpoints",
        json={
            "name": "endpoint-beta",
            "execution_role_arn": "arn:aws:iam::123456789012:role/EmrExecutionRole",
            "release_label": "emr-7.0.0-latest",
        },
        headers={"X-Actor": "test-user"},
    )
    resp = client.get(
        f"/v1/environments/{environment_id}/endpoints",
        headers={"X-Actor": "test-user"},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "endpoint-beta"


# ---------------------------------------------------------------------------
# RBAC permission matrix unit tests (#35)
# ---------------------------------------------------------------------------

def _setup_rbac_fixtures(client: TestClient, monkeypatch) -> dict:
    """Create tenant, team, env, operator, and user identities for RBAC tests."""
    from conftest import issue_test_token

    tenant = client.post(
        "/v1/tenants",
        json={"name": "RBAC Test Tenant"},
        headers={"Idempotency-Key": "rbac-tenant"},
    ).json()

    team = client.post(
        "/v1/teams",
        json={"name": "RBAC Team Alpha", "tenant_id": tenant["id"]},
        headers={"Idempotency-Key": "rbac-team"},
    ).json()

    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotRBAC",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "rbac-env"},
    ).json()

    with SessionLocal() as db:
        process_provisioning_once(db)

    env = client.get(f"/v1/environments/{op['environment_id']}").json()

    # Scope team to environment
    client.post(f"/v1/teams/{team['id']}/environments/{env['id']}")

    # Create operator identity (sub=operator-alice)
    client.post(
        "/v1/user-identities",
        json={
            "actor": "operator-alice",
            "role": "operator",
            "tenant_id": tenant["id"],
            "team_id": team["id"],
            "active": True,
        },
    )

    # Create user identity (sub=user-bob)
    client.post(
        "/v1/user-identities",
        json={
            "actor": "user-bob",
            "role": "user",
            "tenant_id": tenant["id"],
            "team_id": team["id"],
            "active": True,
        },
    )

    return {
        "tenant": tenant,
        "team": team,
        "env": env,
        "operator_token": issue_test_token("operator-alice"),
        "user_token": issue_test_token("user-bob"),
        "admin_token": issue_test_token("test-user"),
    }


def test_rbac_operator_cannot_create_tenant(monkeypatch) -> None:
    """Operators must not be able to create tenants (admin-only) (#35)."""
    client = TestClient(app)
    fixtures = _setup_rbac_fixtures(client, monkeypatch)

    resp = client.post(
        "/v1/tenants",
        json={"name": "Forbidden Tenant"},
        headers={
            "Authorization": f"Bearer {fixtures['operator_token']}",
            "Idempotency-Key": "op-forbidden-tenant",
        },
    )
    assert resp.status_code == 403


def test_rbac_user_cannot_list_identities(monkeypatch) -> None:
    """Regular users must not be able to list user identities (admin-only) (#35)."""
    client = TestClient(app)
    fixtures = _setup_rbac_fixtures(client, monkeypatch)

    resp = client.get(
        "/v1/user-identities",
        headers={"Authorization": f"Bearer {fixtures['user_token']}"},
    )
    assert resp.status_code == 403


def test_rbac_user_can_list_environments_within_scope(monkeypatch) -> None:
    """Users should see environments within their team scope (#35)."""
    client = TestClient(app)
    fixtures = _setup_rbac_fixtures(client, monkeypatch)

    resp = client.get(
        "/v1/environments",
        headers={"Authorization": f"Bearer {fixtures['user_token']}"},
    )
    assert resp.status_code == 200
    envs = resp.json()
    env_ids = {e["id"] for e in envs}
    assert fixtures["env"]["id"] in env_ids


def test_rbac_auth_me_returns_correct_context(monkeypatch) -> None:
    """GET /v1/auth/me returns the correct identity context for each role (#35, #75)."""
    client = TestClient(app)
    fixtures = _setup_rbac_fixtures(client, monkeypatch)

    # Admin
    admin_resp = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {fixtures['admin_token']}"},
    )
    assert admin_resp.status_code == 200
    assert admin_resp.json()["role"] == "admin"

    # Operator
    op_resp = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {fixtures['operator_token']}"},
    )
    assert op_resp.status_code == 200
    op_body = op_resp.json()
    assert op_body["role"] == "operator"
    assert op_body["actor"] == "operator-alice"
    assert fixtures["env"]["id"] in op_body["scoped_environment_ids"]

    # User
    user_resp = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {fixtures['user_token']}"},
    )
    assert user_resp.status_code == 200
    user_body = user_resp.json()
    assert user_body["role"] == "user"
    assert user_body["actor"] == "user-bob"


def test_rbac_cross_team_run_isolation(monkeypatch) -> None:
    """User A from Team Alpha cannot see User B's runs in Team Beta (#35).

    This is the core RBAC isolation test: two teams, two environments, two
    users — each should only see runs in their own team-scoped environment.
    """
    from conftest import issue_test_token

    def _mock_start(self, environment, job, run):
        return EmrDispatchResult(
            emr_job_run_id=f"jr-{run.id[:8]}",
            log_group=f"/sparkpilot/runs/{environment.id}",
            log_stream_prefix=f"{run.id}/attempt-{run.attempt}",
            driver_log_uri=None,
            spark_ui_uri=None,
        )
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.start_job_run", _mock_start)

    client = TestClient(app)

    # Create two tenants, teams, and environments
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Isolation Corp"},
        headers={"Idempotency-Key": "iso-ten"},
    ).json()

    team_alpha = client.post(
        "/v1/teams",
        json={"name": "Team Alpha", "tenant_id": tenant["id"]},
        headers={"Idempotency-Key": "iso-team-alpha"},
    ).json()
    team_beta = client.post(
        "/v1/teams",
        json={"name": "Team Beta", "tenant_id": tenant["id"]},
        headers={"Idempotency-Key": "iso-team-beta"},
    ).json()

    env_a_op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::111111111111:role/RoleAlpha",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 3600},
        },
        headers={"Idempotency-Key": "iso-env-a"},
    ).json()
    env_b_op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::222222222222:role/RoleBeta",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 3600},
        },
        headers={"Idempotency-Key": "iso-env-b"},
    ).json()

    with SessionLocal() as db:
        process_provisioning_once(db)

    env_a = client.get(f"/v1/environments/{env_a_op['environment_id']}").json()
    env_b = client.get(f"/v1/environments/{env_b_op['environment_id']}").json()

    # Scope teams to environments
    client.post(f"/v1/teams/{team_alpha['id']}/environments/{env_a['id']}")
    client.post(f"/v1/teams/{team_beta['id']}/environments/{env_b['id']}")

    # Create user identities
    client.post("/v1/user-identities", json={
        "actor": "alice-alpha", "role": "user",
        "tenant_id": tenant["id"], "team_id": team_alpha["id"], "active": True,
    })
    client.post("/v1/user-identities", json={
        "actor": "bob-beta", "role": "user",
        "tenant_id": tenant["id"], "team_id": team_beta["id"], "active": True,
    })

    alice_token = issue_test_token("alice-alpha")
    bob_token = issue_test_token("bob-beta")

    # Create jobs in each environment (as admin)
    job_a = client.post("/v1/jobs", json={
        "environment_id": env_a["id"],
        "name": "job-alpha",
        "artifact_uri": "s3://alpha/main.py",
        "artifact_digest": "sha256:aaa",
        "entrypoint": "main.py",
    }, headers={"Idempotency-Key": "iso-job-a"}).json()

    job_b = client.post("/v1/jobs", json={
        "environment_id": env_b["id"],
        "name": "job-beta",
        "artifact_uri": "s3://beta/main.py",
        "artifact_digest": "sha256:bbb",
        "entrypoint": "main.py",
    }, headers={"Idempotency-Key": "iso-job-b"}).json()

    # Alice submits a run in env_a
    run_a_resp = client.post(
        f"/v1/jobs/{job_a['id']}/runs",
        json={
            "requested_resources": {
                "driver_vcpu": 1, "driver_memory_gb": 4,
                "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1,
            },
            "timeout_seconds": 3500,
        },
        headers={"Idempotency-Key": "iso-run-a", "Authorization": f"Bearer {alice_token}"},
    )
    assert run_a_resp.status_code == 201, f"Alice run fail: {run_a_resp.status_code} {run_a_resp.text}"
    run_a = run_a_resp.json()

    # Bob submits a run in env_b
    run_b_resp = client.post(
        f"/v1/jobs/{job_b['id']}/runs",
        json={
            "requested_resources": {
                "driver_vcpu": 1, "driver_memory_gb": 4,
                "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1,
            },
            "timeout_seconds": 3500,
        },
        headers={"Idempotency-Key": "iso-run-b", "Authorization": f"Bearer {bob_token}"},
    )
    assert run_b_resp.status_code == 201, f"Bob run fail: {run_b_resp.status_code} {run_b_resp.text}"
    run_b = run_b_resp.json()

    # Alice can see env_a but not env_b
    alice_envs = client.get(
        "/v1/environments",
        headers={"Authorization": f"Bearer {alice_token}"},
    ).json()
    alice_env_ids = {e["id"] for e in alice_envs}
    assert env_a["id"] in alice_env_ids
    assert env_b["id"] not in alice_env_ids

    # Bob can see env_b but not env_a
    bob_envs = client.get(
        "/v1/environments",
        headers={"Authorization": f"Bearer {bob_token}"},
    ).json()
    bob_env_ids = {e["id"] for e in bob_envs}
    assert env_b["id"] in bob_env_ids
    assert env_a["id"] not in bob_env_ids

    # Alice cannot view Bob's run (different team scope)
    alice_view_bob_run = client.get(
        f"/v1/runs/{run_b['id']}",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert alice_view_bob_run.status_code == 403

    # Bob cannot view Alice's run
    bob_view_alice_run = client.get(
        f"/v1/runs/{run_a['id']}",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert bob_view_alice_run.status_code == 403

    # Each can view their own run
    assert client.get(
        f"/v1/runs/{run_a['id']}",
        headers={"Authorization": f"Bearer {alice_token}"},
    ).status_code == 200
    assert client.get(
        f"/v1/runs/{run_b['id']}",
        headers={"Authorization": f"Bearer {bob_token}"},
    ).status_code == 200


# ---------------------------------------------------------------------------
# Policy Engine unit tests (#39)
# ---------------------------------------------------------------------------


def _create_ready_env_for_policy(client: TestClient, suffix: str = "pol") -> dict:
    """Helper: create a ready environment for policy tests."""
    tenant = client.post(
        "/v1/tenants",
        json={"name": f"Policy Corp {suffix}"},
        headers={"Idempotency-Key": f"pol-ten-{suffix}"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/PolicyRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": f"pol-env-{suffix}"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)
    env = client.get(f"/v1/environments/{op['environment_id']}").json()
    return {"tenant": tenant, "env": env}


def test_policy_crud_lifecycle() -> None:
    """Admin can create, list, get, and delete a policy (#39)."""
    client = TestClient(app)
    fixtures = _create_ready_env_for_policy(client, "crud")

    # Create
    resp = client.post("/v1/policies", json={
        "name": "Max Runtime 1h",
        "scope": "global",
        "rule_type": "max_runtime_seconds",
        "config": {"max_seconds": 3600},
        "enforcement": "hard",
    })
    assert resp.status_code == 201
    policy = resp.json()
    assert policy["name"] == "Max Runtime 1h"
    assert policy["rule_type"] == "max_runtime_seconds"
    assert policy["enforcement"] == "hard"
    assert policy["active"] is True

    # List
    resp = client.get("/v1/policies")
    assert resp.status_code == 200
    policies = resp.json()
    assert any(p["id"] == policy["id"] for p in policies)

    # Get by ID
    resp = client.get(f"/v1/policies/{policy['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == policy["id"]

    # Delete (deactivate)
    resp = client.delete(f"/v1/policies/{policy['id']}")
    assert resp.status_code == 204

    # Verify deactivated
    resp = client.get(f"/v1/policies/{policy['id']}")
    assert resp.status_code == 200
    assert resp.json()["active"] is False


def test_policy_max_runtime_blocks_run(monkeypatch) -> None:
    """A hard max_runtime_seconds policy blocks runs that exceed the limit (#39)."""
    def _mock_start(self, environment, job, run):
        return EmrDispatchResult(
            emr_job_run_id=f"jr-{run.id[:8]}",
            log_group=f"/sparkpilot/runs/{environment.id}",
            log_stream_prefix=f"{run.id}/attempt-{run.attempt}",
            driver_log_uri=None,
            spark_ui_uri=None,
        )
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.start_job_run", _mock_start)

    client = TestClient(app)
    fixtures = _create_ready_env_for_policy(client, "maxrt")
    env = fixtures["env"]

    # Create policy: max runtime 1800s
    client.post("/v1/policies", json={
        "name": "Max 30min Runtime",
        "scope": "environment",
        "scope_id": env["id"],
        "rule_type": "max_runtime_seconds",
        "config": {"max_seconds": 1800},
        "enforcement": "hard",
    })

    # Create a job
    job = client.post("/v1/jobs", json={
        "environment_id": env["id"],
        "name": "policy-test-job",
        "artifact_uri": "s3://test/main.py",
        "artifact_digest": "sha256:aaa",
        "entrypoint": "main.py",
    }, headers={"Idempotency-Key": "pol-job-maxrt"}).json()

    # Submit run with timeout exceeding policy
    resp = client.post(f"/v1/jobs/{job['id']}/runs", json={
        "requested_resources": {
            "driver_vcpu": 1, "driver_memory_gb": 4,
            "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1,
        },
        "timeout_seconds": 3600,
    }, headers={"Idempotency-Key": "pol-run-maxrt-fail"})
    assert resp.status_code == 422
    assert "Policy violation" in resp.json()["detail"]

    # Submit run within policy limit — should succeed
    resp = client.post(f"/v1/jobs/{job['id']}/runs", json={
        "requested_resources": {
            "driver_vcpu": 1, "driver_memory_gb": 4,
            "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1,
        },
        "timeout_seconds": 1500,
    }, headers={"Idempotency-Key": "pol-run-maxrt-ok"})
    assert resp.status_code == 201


def test_policy_max_vcpu_blocks_run(monkeypatch) -> None:
    """A hard max_vcpu policy blocks runs that exceed vCPU limit (#39)."""
    def _mock_start(self, environment, job, run):
        return EmrDispatchResult(
            emr_job_run_id=f"jr-{run.id[:8]}",
            log_group=f"/sparkpilot/runs/{environment.id}",
            log_stream_prefix=f"{run.id}/attempt-{run.attempt}",
            driver_log_uri=None,
            spark_ui_uri=None,
        )
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.start_job_run", _mock_start)

    client = TestClient(app)
    fixtures = _create_ready_env_for_policy(client, "maxvcpu")
    env = fixtures["env"]

    client.post("/v1/policies", json={
        "name": "Max 8 vCPU",
        "scope": "environment",
        "scope_id": env["id"],
        "rule_type": "max_vcpu",
        "config": {"max_vcpu": 8},
        "enforcement": "hard",
    })

    job = client.post("/v1/jobs", json={
        "environment_id": env["id"],
        "name": "vcpu-test-job",
        "artifact_uri": "s3://test/vcpu.py",
        "artifact_digest": "sha256:bbb",
        "entrypoint": "vcpu.py",
    }, headers={"Idempotency-Key": "pol-job-vcpu"}).json()

    # 1 driver + 10 executors * 2 vCPU = 21 vCPU — exceeds 8
    resp = client.post(f"/v1/jobs/{job['id']}/runs", json={
        "requested_resources": {
            "driver_vcpu": 1, "driver_memory_gb": 4,
            "executor_vcpu": 2, "executor_memory_gb": 4, "executor_instances": 10,
        },
        "timeout_seconds": 3600,
    }, headers={"Idempotency-Key": "pol-run-vcpu-fail"})
    assert resp.status_code == 422
    assert "Policy violation" in resp.json()["detail"]


def test_policy_soft_enforcement_warns_in_preflight() -> None:
    """A soft-enforcement policy produces a warning in preflight, not a block (#39)."""
    client = TestClient(app)
    fixtures = _create_ready_env_for_policy(client, "soft")
    env = fixtures["env"]

    client.post("/v1/policies", json={
        "name": "Soft Max Memory",
        "scope": "environment",
        "scope_id": env["id"],
        "rule_type": "max_memory_gb",
        "config": {"max_memory_gb": 16},
        "enforcement": "soft",
    })

    resp = client.get(f"/v1/environments/{env['id']}/preflight")
    assert resp.status_code == 200
    preflight = resp.json()
    # Soft policies should not make preflight fail
    assert preflight["ready"] is True


def test_policy_required_tags_blocks_run(monkeypatch) -> None:
    """A required_tags policy blocks runs missing required tags (#39)."""
    def _mock_start(self, environment, job, run):
        return EmrDispatchResult(
            emr_job_run_id=f"jr-{run.id[:8]}",
            log_group=f"/sparkpilot/runs/{environment.id}",
            log_stream_prefix=f"{run.id}/attempt-{run.attempt}",
            driver_log_uri=None,
            spark_ui_uri=None,
        )
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.start_job_run", _mock_start)

    client = TestClient(app)
    fixtures = _create_ready_env_for_policy(client, "tags")
    env = fixtures["env"]

    client.post("/v1/policies", json={
        "name": "Required Cost Center",
        "scope": "environment",
        "scope_id": env["id"],
        "rule_type": "required_tags",
        "config": {"tags": {"cost-center": ""}},
        "enforcement": "hard",
    })

    job = client.post("/v1/jobs", json={
        "environment_id": env["id"],
        "name": "tags-test-job",
        "artifact_uri": "s3://test/tags.py",
        "artifact_digest": "sha256:ccc",
        "entrypoint": "tags.py",
    }, headers={"Idempotency-Key": "pol-job-tags"}).json()

    # Run without tags — blocked
    resp = client.post(f"/v1/jobs/{job['id']}/runs", json={
        "requested_resources": {
            "driver_vcpu": 1, "driver_memory_gb": 4,
            "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1,
        },
        "timeout_seconds": 3600,
    }, headers={"Idempotency-Key": "pol-run-tags-fail"})
    assert resp.status_code == 422
    assert "Policy violation" in resp.json()["detail"]

    # Run with tags — allowed
    resp = client.post(f"/v1/jobs/{job['id']}/runs", json={
        "requested_resources": {
            "driver_vcpu": 1, "driver_memory_gb": 4,
            "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1,
        },
        "spark_conf": {
            "spark.kubernetes.driver.label.cost-center": "engineering",
        },
        "timeout_seconds": 3600,
    }, headers={"Idempotency-Key": "pol-run-tags-ok"})
    assert resp.status_code == 201


def test_policy_allowed_golden_paths() -> None:
    """An allowed_golden_paths policy controls golden path usage (#39)."""
    client = TestClient(app)
    fixtures = _create_ready_env_for_policy(client, "gp")
    env = fixtures["env"]

    resp = client.post("/v1/policies", json={
        "name": "Only Standard Paths",
        "scope": "environment",
        "scope_id": env["id"],
        "rule_type": "allowed_golden_paths",
        "config": {"allowed": ["standard-etl", "ml-training"], "require_golden_path": True},
        "enforcement": "hard",
    })
    assert resp.status_code == 201
    # Verify the policy evaluates correctly via preflight
    resp = client.get(f"/v1/environments/{env['id']}/preflight")
    assert resp.status_code == 200


def test_policy_evaluation_creates_audit_events() -> None:
    """Every policy evaluation writes an audit event (#39)."""
    client = TestClient(app)
    fixtures = _create_ready_env_for_policy(client, "audit")
    env = fixtures["env"]

    client.post("/v1/policies", json={
        "name": "Audit Test Policy",
        "scope": "environment",
        "scope_id": env["id"],
        "rule_type": "max_vcpu",
        "config": {"max_vcpu": 64},
        "enforcement": "hard",
    })

    # Trigger preflight which evaluates policies
    client.get(f"/v1/environments/{env['id']}/preflight")

    # Check audit events
    with SessionLocal() as db:
        from sparkpilot.models import AuditEvent
        events = db.execute(
            select(AuditEvent).where(AuditEvent.action == "policy.evaluated")
        ).scalars().all()
        assert len(events) >= 1
        assert events[0].entity_type == "policy"


def test_policy_integration_blocks_violating_run(monkeypatch) -> None:
    """End-to-end: policy blocks a run and returns clear remediation (#39)."""
    def _mock_start(self, environment, job, run):
        return EmrDispatchResult(
            emr_job_run_id=f"jr-{run.id[:8]}",
            log_group=f"/sparkpilot/runs/{environment.id}",
            log_stream_prefix=f"{run.id}/attempt-{run.attempt}",
            driver_log_uri=None,
            spark_ui_uri=None,
        )
    monkeypatch.setattr("sparkpilot.services.EmrEksClient.start_job_run", _mock_start)

    client = TestClient(app)
    fixtures = _create_ready_env_for_policy(client, "integ")
    env = fixtures["env"]

    # Create multiple policies
    client.post("/v1/policies", json={
        "name": "Max 4 vCPU",
        "scope": "environment",
        "scope_id": env["id"],
        "rule_type": "max_vcpu",
        "config": {"max_vcpu": 4},
        "enforcement": "hard",
    })
    client.post("/v1/policies", json={
        "name": "Max 1h Runtime",
        "scope": "global",
        "rule_type": "max_runtime_seconds",
        "config": {"max_seconds": 3600},
        "enforcement": "hard",
    })

    job = client.post("/v1/jobs", json={
        "environment_id": env["id"],
        "name": "integ-test-job",
        "artifact_uri": "s3://test/integ.py",
        "artifact_digest": "sha256:ddd",
        "entrypoint": "integ.py",
    }, headers={"Idempotency-Key": "pol-job-integ"}).json()

    # Run violating vCPU policy
    resp = client.post(f"/v1/jobs/{job['id']}/runs", json={
        "requested_resources": {
            "driver_vcpu": 2, "driver_memory_gb": 8,
            "executor_vcpu": 4, "executor_memory_gb": 8, "executor_instances": 5,
        },
        "timeout_seconds": 3600,
    }, headers={"Idempotency-Key": "pol-run-integ-fail"})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "Max 4 vCPU" in detail
    assert "Policy violation" in detail

    # Run within all policies — should succeed
    resp = client.post(f"/v1/jobs/{job['id']}/runs", json={
        "requested_resources": {
            "driver_vcpu": 1, "driver_memory_gb": 4,
            "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1,
        },
        "timeout_seconds": 1800,
    }, headers={"Idempotency-Key": "pol-run-integ-ok"})
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Lake Formation FGAC tests (#38)
# ---------------------------------------------------------------------------

def _create_fgac_env(client, suffix: str, *, lake_formation_enabled: bool = True):
    """Helper to create a tenant+env with FGAC configuration."""
    tenant = client.post(
        "/v1/tenants",
        json={"name": f"FGAC Tenant {suffix}"},
        headers={"Idempotency-Key": f"t-fgac-{suffix}", "X-Actor": "test-user"},
    ).json()
    op_resp = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/test",
            "eks_namespace": f"fgac-ns-{suffix}",
            "lake_formation_enabled": lake_formation_enabled,
            "lf_catalog_id": "123456789012",
            "lf_data_access_scope": {"databases": ["analytics"]},
        },
        headers={"Idempotency-Key": f"e-fgac-{suffix}", "X-Actor": "test-user"},
    )
    assert op_resp.status_code == 201, op_resp.text
    env_id = op_resp.json()["environment_id"]
    with SessionLocal() as db:
        process_provisioning_once(db)
    return {"tenant": tenant, "env_id": env_id}


def test_fgac_environment_fields_persisted() -> None:
    """FGAC config fields are stored and returned in environment response (#38)."""
    client = TestClient(app)
    fixtures = _create_fgac_env(client, "persist")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}")
    assert resp.status_code == 200
    env = resp.json()
    assert env["lake_formation_enabled"] is True
    assert env["lf_catalog_id"] == "123456789012"
    assert env["lf_data_access_scope"] == {"databases": ["analytics"]}


def test_fgac_disabled_no_checks() -> None:
    """When FGAC is disabled, no fgac.* checks appear (#38)."""
    client = TestClient(app)
    fixtures = _create_fgac_env(client, "disabled", lake_formation_enabled=False)
    resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
    assert resp.status_code == 200
    checks = resp.json()["checks"]
    fgac_checks = [c for c in checks if c["code"].startswith("fgac.")]
    assert len(fgac_checks) == 0


def test_fgac_emr_release_check_passes(monkeypatch) -> None:
    """When FGAC is enabled and release >= 7.7, EMR release check passes (#38)."""
    monkeypatch.setenv("SPARKPILOT_EMR_RELEASE_LABEL", "emr-7.7.0")
    # Mock AWS calls to avoid real API hits
    monkeypatch.setattr(
        "sparkpilot.services.lake_formation.check_lf_service_linked_role_exists",
        lambda region: {"exists": True, "role_name": "AWSServiceRoleForLakeFormationDataAccess", "error": None},
    )
    monkeypatch.setattr(
        "sparkpilot.services.lake_formation.check_execution_role_lf_permissions",
        lambda region, role_arn, catalog_id=None: {
            "has_permissions": True, "permission_count": 3,
            "databases": ["db1"], "tables": ["t1"], "error": None,
        },
    )
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        fixtures = _create_fgac_env(client, "release-ok")
        resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
        assert resp.status_code == 200
        checks = {c["code"]: c for c in resp.json()["checks"]}
        assert "fgac.emr_release" in checks
        assert checks["fgac.emr_release"]["status"] == "pass"
    finally:
        get_settings.cache_clear()


def test_fgac_emr_release_too_old_blocks(monkeypatch) -> None:
    """When FGAC is enabled but release < 7.7, EMR release check fails (#38)."""
    monkeypatch.setenv("SPARKPILOT_EMR_RELEASE_LABEL", "emr-6.15.0")
    # Mock AWS calls
    monkeypatch.setattr(
        "sparkpilot.services.lake_formation.check_lf_service_linked_role_exists",
        lambda region: {"exists": True, "role_name": "AWSServiceRoleForLakeFormationDataAccess", "error": None},
    )
    monkeypatch.setattr(
        "sparkpilot.services.lake_formation.check_execution_role_lf_permissions",
        lambda region, role_arn, catalog_id=None: {
            "has_permissions": True, "permission_count": 1,
            "databases": [], "tables": [], "error": None,
        },
    )
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        fixtures = _create_fgac_env(client, "release-old")
        resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
        assert resp.status_code == 200
        checks = {c["code"]: c for c in resp.json()["checks"]}
        assert checks["fgac.emr_release"]["status"] == "fail"
        assert "7.7" in checks["fgac.emr_release"]["message"]
    finally:
        get_settings.cache_clear()


def test_fgac_slr_missing_blocks(monkeypatch) -> None:
    """When LF service-linked role is missing, check fails (#38)."""
    monkeypatch.setenv("SPARKPILOT_EMR_EXECUTION_ROLE_ARN", "arn:aws:iam::123456789012:role/emr-exec")
    monkeypatch.setattr(
        "sparkpilot.services.lake_formation.check_lf_service_linked_role_exists",
        lambda region: {"exists": False, "role_name": "AWSServiceRoleForLakeFormationDataAccess", "error": None},
    )
    monkeypatch.setattr(
        "sparkpilot.services.lake_formation.check_execution_role_lf_permissions",
        lambda region, role_arn, catalog_id=None: {
            "has_permissions": True, "permission_count": 1,
            "databases": [], "tables": [], "error": None,
        },
    )
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        fixtures = _create_fgac_env(client, "slr-missing")
        resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
        assert resp.status_code == 200
        checks = {c["code"]: c for c in resp.json()["checks"]}
        assert checks["fgac.service_linked_role"]["status"] == "fail"
        assert "service-linked role" in checks["fgac.service_linked_role"]["message"].lower()
    finally:
        get_settings.cache_clear()


def test_fgac_no_permissions_blocks(monkeypatch) -> None:
    """When execution role has no LF permissions, check fails (#38)."""
    monkeypatch.setenv("SPARKPILOT_EMR_EXECUTION_ROLE_ARN", "arn:aws:iam::123456789012:role/emr-exec")
    monkeypatch.setattr(
        "sparkpilot.services.lake_formation.check_lf_service_linked_role_exists",
        lambda region: {"exists": True, "role_name": "AWSServiceRoleForLakeFormationDataAccess", "error": None},
    )
    monkeypatch.setattr(
        "sparkpilot.services.lake_formation.check_execution_role_lf_permissions",
        lambda region, role_arn, catalog_id=None: {
            "has_permissions": False, "permission_count": 0,
            "databases": [], "tables": [], "error": None,
        },
    )
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        fixtures = _create_fgac_env(client, "no-perms")
        resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
        assert resp.status_code == 200
        checks = {c["code"]: c for c in resp.json()["checks"]}
        assert checks["fgac.lf_permissions"]["status"] == "fail"
        assert "no Lake Formation" in checks["fgac.lf_permissions"]["message"]
    finally:
        get_settings.cache_clear()


def test_fgac_all_checks_pass(monkeypatch) -> None:
    """When all FGAC prerequisites are met, all checks pass (#38)."""
    monkeypatch.setenv("SPARKPILOT_EMR_EXECUTION_ROLE_ARN", "arn:aws:iam::123456789012:role/emr-exec")
    monkeypatch.setattr(
        "sparkpilot.services.lake_formation.check_lf_service_linked_role_exists",
        lambda region: {"exists": True, "role_name": "AWSServiceRoleForLakeFormationDataAccess", "error": None},
    )
    monkeypatch.setattr(
        "sparkpilot.services.lake_formation.check_execution_role_lf_permissions",
        lambda region, role_arn, catalog_id=None: {
            "has_permissions": True, "permission_count": 5,
            "databases": ["analytics", "reporting"], "tables": ["events", "users"],
            "error": None,
        },
    )
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        fixtures = _create_fgac_env(client, "all-pass")
        resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
        assert resp.status_code == 200
        checks = {c["code"]: c for c in resp.json()["checks"]}
        assert checks["fgac.emr_release"]["status"] == "pass"
        assert checks["fgac.service_linked_role"]["status"] == "pass"
        assert checks["fgac.lf_permissions"]["status"] == "pass"
    finally:
        get_settings.cache_clear()


def test_fgac_golden_path_data_access_scope() -> None:
    """Golden paths can declare a data access scope (#38)."""
    client = TestClient(app)
    resp = client.post("/v1/golden-paths", json={
        "name": "fgac-etl-scope",
        "description": "ETL pipeline with FGAC scope",
        "driver_resources": {"vcpu": 2, "memory_gb": 8},
        "executor_resources": {"vcpu": 4, "memory_gb": 16},
        "executor_count": 5,
        "data_access_scope": {
            "databases": ["analytics_db"],
            "tables": ["analytics_db.events"],
            "description": "Read access to analytics events",
        },
    })
    assert resp.status_code == 201
    gp = resp.json()
    assert gp["data_access_scope"]["databases"] == ["analytics_db"]
    assert gp["data_access_scope"]["description"] == "Read access to analytics events"

    # Verify retrieval
    resp = client.get(f"/v1/golden-paths/{gp['id']}")
    assert resp.status_code == 200
    assert resp.json()["data_access_scope"] is not None


# ---------------------------------------------------------------------------
# EKS Pod Identity & Access Entry tests (#52)
# ---------------------------------------------------------------------------

def _create_byoc_lite_env(client, suffix: str):
    """Helper to create a BYOC-Lite tenant+env for Pod Identity tests."""
    tenant = client.post(
        "/v1/tenants",
        json={"name": f"PodId Tenant {suffix}"},
        headers={"Idempotency-Key": f"t-podid-{suffix}", "X-Actor": "test-user"},
    ).json()
    op_resp = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/test-pod-id",
            "eks_namespace": f"podid-ns-{suffix}",
        },
        headers={"Idempotency-Key": f"e-podid-{suffix}", "X-Actor": "test-user"},
    )
    assert op_resp.status_code == 201, op_resp.text
    env_id = op_resp.json()["environment_id"]
    with SessionLocal() as db:
        process_provisioning_once(db)
    return {"tenant": tenant, "env_id": env_id}


def test_pod_identity_readiness_pass(monkeypatch) -> None:
    """Pod Identity check passes when addon is ACTIVE (#52)."""
    monkeypatch.setattr(
        "sparkpilot.services.preflight_byoc.EmrEksClient.check_pod_identity_agent",
        lambda self, env: {
            "cluster_name": "test", "addon_installed": True,
            "addon_status": "ACTIVE", "addon_version": "v1.3.4-eksbuild.1",
        },
    )
    monkeypatch.setattr(
        "sparkpilot.services.preflight_byoc.EmrEksClient.check_cluster_access_mode",
        lambda self, env: {
            "cluster_name": "test", "authentication_mode": "API_AND_CONFIG_MAP",
            "access_entries_supported": True,
        },
    )
    client = TestClient(app)
    fixtures = _create_byoc_lite_env(client, "pod-pass")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
    assert resp.status_code == 200
    checks = {c["code"]: c for c in resp.json()["checks"]}
    assert checks["byoc_lite.pod_identity_readiness"]["status"] == "pass"
    assert "active" in checks["byoc_lite.pod_identity_readiness"]["message"].lower()


def test_pod_identity_not_installed_warns(monkeypatch) -> None:
    """Pod Identity check warns when addon is not installed (#52)."""
    monkeypatch.setattr(
        "sparkpilot.services.preflight_byoc.EmrEksClient.check_pod_identity_agent",
        lambda self, env: {
            "cluster_name": "test", "addon_installed": False,
            "addon_status": "NOT_INSTALLED",
        },
    )
    monkeypatch.setattr(
        "sparkpilot.services.preflight_byoc.EmrEksClient.check_cluster_access_mode",
        lambda self, env: {
            "cluster_name": "test", "authentication_mode": "API_AND_CONFIG_MAP",
            "access_entries_supported": True,
        },
    )
    client = TestClient(app)
    fixtures = _create_byoc_lite_env(client, "pod-missing")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
    assert resp.status_code == 200
    checks = {c["code"]: c for c in resp.json()["checks"]}
    assert checks["byoc_lite.pod_identity_readiness"]["status"] == "warning"
    assert "IRSA" in checks["byoc_lite.pod_identity_readiness"]["message"]


def test_access_entry_mode_pass(monkeypatch) -> None:
    """Access entry mode check passes when API_AND_CONFIG_MAP (#52)."""
    monkeypatch.setattr(
        "sparkpilot.services.preflight_byoc.EmrEksClient.check_pod_identity_agent",
        lambda self, env: {
            "cluster_name": "test", "addon_installed": True,
            "addon_status": "ACTIVE", "addon_version": "v1.3.4-eksbuild.1",
        },
    )
    monkeypatch.setattr(
        "sparkpilot.services.preflight_byoc.EmrEksClient.check_cluster_access_mode",
        lambda self, env: {
            "cluster_name": "test", "authentication_mode": "API_AND_CONFIG_MAP",
            "access_entries_supported": True,
        },
    )
    client = TestClient(app)
    fixtures = _create_byoc_lite_env(client, "access-pass")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
    assert resp.status_code == 200
    checks = {c["code"]: c for c in resp.json()["checks"]}
    assert checks["byoc_lite.access_entry_mode"]["status"] == "pass"


def test_access_entry_mode_config_map_warns(monkeypatch) -> None:
    """Access entry mode warns for CONFIG_MAP only mode (#52)."""
    monkeypatch.setattr(
        "sparkpilot.services.preflight_byoc.EmrEksClient.check_pod_identity_agent",
        lambda self, env: {
            "cluster_name": "test", "addon_installed": False,
            "addon_status": "NOT_INSTALLED",
        },
    )
    monkeypatch.setattr(
        "sparkpilot.services.preflight_byoc.EmrEksClient.check_cluster_access_mode",
        lambda self, env: {
            "cluster_name": "test", "authentication_mode": "CONFIG_MAP",
            "access_entries_supported": False,
        },
    )
    client = TestClient(app)
    fixtures = _create_byoc_lite_env(client, "access-warn")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
    assert resp.status_code == 200
    checks = {c["code"]: c for c in resp.json()["checks"]}
    assert checks["byoc_lite.access_entry_mode"]["status"] == "warning"
    assert "CONFIG_MAP" in checks["byoc_lite.access_entry_mode"]["message"]


def test_identity_mode_field_returned() -> None:
    """Environment response includes identity_mode field (#52)."""
    client = TestClient(app)
    fixtures = _create_byoc_lite_env(client, "id-mode")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}")
    assert resp.status_code == 200
    env = resp.json()
    assert "identity_mode" in env


# ---------------------------------------------------------------------------
# EMR Security Configuration tests (#53)
# ---------------------------------------------------------------------------


def _create_env_with_sec_config(client, suffix: str, sec_config_id: str | None = None):
    """Helper to create a tenant+env optionally with security_configuration_id."""
    tenant = client.post(
        "/v1/tenants",
        json={"name": f"SecConfig Tenant {suffix}"},
        headers={"Idempotency-Key": f"t-sc-{suffix}", "X-Actor": "test-user"},
    ).json()
    env_payload = {
        "tenant_id": tenant["id"],
        "region": "us-east-1",
        "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
    }
    if sec_config_id:
        env_payload["security_configuration_id"] = sec_config_id
    op_resp = client.post(
        "/v1/environments",
        json=env_payload,
        headers={"Idempotency-Key": f"e-sc-{suffix}", "X-Actor": "test-user"},
    )
    assert op_resp.status_code == 201, op_resp.text
    env_id = op_resp.json()["environment_id"]
    with SessionLocal() as db:
        process_provisioning_once(db)
    return {"tenant": tenant, "env_id": env_id}


def test_security_configuration_id_persisted_on_environment() -> None:
    """Environment response includes security_configuration_id field (#53)."""
    client = TestClient(app)
    fixtures = _create_env_with_sec_config(client, "persist", sec_config_id="sc-test-abc123")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}")
    assert resp.status_code == 200
    env = resp.json()
    assert env["security_configuration_id"] == "sc-test-abc123"


def test_security_configuration_id_null_by_default() -> None:
    """Environment response has null security_configuration_id when not set (#53)."""
    client = TestClient(app)
    fixtures = _create_env_with_sec_config(client, "null-sc")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}")
    assert resp.status_code == 200
    assert resp.json()["security_configuration_id"] is None


def test_security_configuration_preflight_pass(monkeypatch) -> None:
    """Preflight passes when security configuration exists (#53)."""
    monkeypatch.setattr(
        "sparkpilot.aws_clients.EmrEksClient.describe_security_configuration",
        lambda self, env, sc_id: {
            "id": sc_id,
            "name": "test-sec-config",
            "securityConfigurationData": {},
        },
    )
    client = TestClient(app)
    fixtures = _create_env_with_sec_config(client, "pf-pass", sec_config_id="sc-pf-pass")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
    assert resp.status_code == 200
    checks = {c["code"]: c for c in resp.json()["checks"]}
    assert checks["emr.security_configuration"]["status"] == "pass"
    assert "exists" in checks["emr.security_configuration"]["message"].lower()


def test_security_configuration_preflight_fail(monkeypatch) -> None:
    """Preflight fails when security configuration not found (#53)."""
    monkeypatch.setattr(
        "sparkpilot.aws_clients.EmrEksClient.describe_security_configuration",
        lambda self, env, sc_id: (_ for _ in ()).throw(
            ValueError(f"Security configuration '{sc_id}' not found.")
        ),
    )
    client = TestClient(app)
    fixtures = _create_env_with_sec_config(client, "pf-fail", sec_config_id="sc-nonexistent")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
    assert resp.status_code == 200
    checks = {c["code"]: c for c in resp.json()["checks"]}
    assert checks["emr.security_configuration"]["status"] == "fail"
    assert "not found" in checks["emr.security_configuration"]["message"].lower()


def test_security_configuration_policy_blocks_disallowed() -> None:
    """Policy engine blocks disallowed security configuration (#53)."""
    client = TestClient(app)
    fixtures = _create_env_with_sec_config(client, "policy-block", sec_config_id="sc-unapproved")

    # Create policy allowing only specific configs
    policy_resp = client.post(
        "/v1/policies",
        json={
            "name": "Allowed SecConfigs",
            "scope": "global",
            "rule_type": "allowed_security_configurations",
            "config": {"allowed": ["sc-approved-1", "sc-approved-2"]},
            "enforcement": "hard",
        },
        headers={"X-Actor": "test-user"},
    )
    assert policy_resp.status_code == 201

    resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
    assert resp.status_code == 200
    checks = {c["code"]: c for c in resp.json()["checks"]}
    assert checks["policy.allowed_security_configurations"]["status"] == "fail"
    assert "not in the allowed list" in checks["policy.allowed_security_configurations"]["message"]


def test_security_configuration_policy_passes_approved() -> None:
    """Policy engine passes approved security configuration (#53)."""
    client = TestClient(app)
    fixtures = _create_env_with_sec_config(client, "policy-pass", sec_config_id="sc-approved-1")

    client.post(
        "/v1/policies",
        json={
            "name": "Allowed SecConfigs Pass",
            "scope": "global",
            "rule_type": "allowed_security_configurations",
            "config": {"allowed": ["sc-approved-1", "sc-approved-2"]},
            "enforcement": "hard",
        },
        headers={"X-Actor": "test-user"},
    )

    resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
    assert resp.status_code == 200
    checks = {c["code"]: c for c in resp.json()["checks"]}
    assert checks["policy.allowed_security_configurations"]["status"] == "pass"


def test_security_configuration_policy_requires_config() -> None:
    """Policy engine fails when security configuration is required but missing (#53)."""
    client = TestClient(app)
    fixtures = _create_env_with_sec_config(client, "policy-require")  # no sec config

    client.post(
        "/v1/policies",
        json={
            "name": "Require SecConfig",
            "scope": "global",
            "rule_type": "allowed_security_configurations",
            "config": {"require_security_configuration": True},
            "enforcement": "hard",
        },
        headers={"X-Actor": "test-user"},
    )

    resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
    assert resp.status_code == 200
    checks = {c["code"]: c for c in resp.json()["checks"]}
    assert checks["policy.allowed_security_configurations"]["status"] == "fail"
    assert "required by policy" in checks["policy.allowed_security_configurations"]["message"]


def test_security_configuration_create_endpoint() -> None:
    """Create security configuration endpoint returns result (#53)."""
    client = TestClient(app)
    fixtures = _create_env_with_sec_config(client, "create-ep")
    resp = client.post(
        f"/v1/environments/{fixtures['env_id']}/security-configurations",
        json={
            "name": "test-sec-config",
            "virtual_cluster_id": "vc-test-123",
            "encryption_config": {"inTransitEncryptionConfiguration": {}},
        },
        headers={"X-Actor": "test-user"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-sec-config"
    assert data["id"]


def test_security_configuration_list_endpoint() -> None:
    """List security configurations endpoint returns list (#53)."""
    client = TestClient(app)
    fixtures = _create_env_with_sec_config(client, "list-ep")
    resp = client.get(
        f"/v1/environments/{fixtures['env_id']}/security-configurations",
        headers={"X-Actor": "test-user"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# IAM credential chain validation tests (#76)
# ---------------------------------------------------------------------------


def test_iam_runtime_identity_preflight_check() -> None:
    """Preflight includes iam.runtime_identity check (#76)."""
    client = TestClient(app)
    fixtures = _create_env_with_sec_config(client, "iam-rt")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
    assert resp.status_code == 200
    checks = {c["code"]: c for c in resp.json()["checks"]}
    assert "iam.runtime_identity" in checks
    assert checks["iam.runtime_identity"]["status"] == "pass"


def test_iam_assume_role_preflight_check() -> None:
    """Preflight includes iam.assume_role_chain check (#76)."""
    client = TestClient(app)
    fixtures = _create_env_with_sec_config(client, "iam-ar")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}/preflight")
    assert resp.status_code == 200
    checks = {c["code"]: c for c in resp.json()["checks"]}
    assert "iam.assume_role_chain" in checks
    assert checks["iam.assume_role_chain"]["status"] == "pass"


def test_iam_validation_endpoint() -> None:
    """GET /v1/iam-validation returns runtime identity (#76)."""
    client = TestClient(app)
    resp = client.get("/v1/iam-validation")
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_valid" in data
    assert data["overall_valid"] is True
    assert data["runtime_identity"]["valid"] is True


def test_iam_environment_validation_endpoint() -> None:
    """GET /v1/environments/{id}/iam-validation includes assume_role (#76)."""
    client = TestClient(app)
    fixtures = _create_env_with_sec_config(client, "iam-env-val")
    resp = client.get(f"/v1/environments/{fixtures['env_id']}/iam-validation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["environment_id"] == fixtures["env_id"]
    assert data["overall_valid"] is True
    assert "assume_role" in data
    assert data["assume_role"]["success"] is True


def test_iam_static_credentials_check(monkeypatch) -> None:
    """Static credentials detection warns in preflight (#76)."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fakesecretkey")
    # Remove session token to simulate long-lived static creds
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)

    from sparkpilot.services.iam_validation import check_static_credentials
    result = check_static_credentials()
    assert result["static_credentials_detected"] is True
    assert result["compliant"] is False
    assert result["remediation"] is not None