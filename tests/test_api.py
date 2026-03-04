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
        headers={"Idempotency-Key": f"tenant-{suffix}"},
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
        headers={"Idempotency-Key": f"env-{suffix}"},
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
        headers={"Idempotency-Key": f"job-{suffix}"},
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
        headers={"Idempotency-Key": f"run-{suffix}"},
    ).json()
    return tenant, op, job, run


def test_tenant_create_idempotent() -> None:
    client = TestClient(app)
    headers = {"Idempotency-Key": "tenant-create-key"}
    payload = {"name": "Acme Data"}
    first = client.post("/v1/tenants", json=payload, headers=headers)
    assert first.status_code == 201
    second = client.post("/v1/tenants", json=payload, headers=headers)
    assert second.status_code == 201
    assert second.headers.get("X-Idempotent-Replay") == "true"
    assert first.json()["id"] == second.json()["id"]


def test_api_requires_valid_oidc_bearer_token(oidc_token) -> None:
    client = TestClient(app)

    missing = client.get("/v1/runs", headers={"Authorization": ""})
    assert missing.status_code == 401

    invalid = client.get("/v1/runs", headers={"Authorization": "Bearer invalid-token"})
    assert invalid.status_code == 401

    valid = client.get("/v1/runs", headers={"Authorization": f"Bearer {oidc_token('test-user')}"})
    assert valid.status_code == 200


def test_actor_header_does_not_override_authenticated_subject(oidc_token) -> None:
    client = TestClient(app)

    tenant = client.post(
        "/v1/tenants",
        json={"name": "header-ignore"},
        headers={"Idempotency-Key": "tenant-header-ignore"},
    )
    assert tenant.status_code == 201

    team = client.post(
        "/v1/teams",
        json={"tenant_id": tenant.json()["id"], "name": "header-ignore-team"},
    )
    assert team.status_code == 201

    user = client.post(
        "/v1/user-identities",
        json={
            "actor": "header-ignore-user",
            "role": "user",
            "tenant_id": tenant.json()["id"],
            "team_id": team.json()["id"],
            "active": True,
        },
    )
    assert user.status_code == 201

    escalated = client.post(
        "/v1/tenants",
        json={"name": "forbidden-by-subject"},
        headers={
            "Authorization": f"Bearer {oidc_token('header-ignore-user')}",
            "X-Actor": "test-user",
            "Idempotency-Key": "tenant-header-escalate",
        },
    )
    assert escalated.status_code == 403


def test_cors_allows_configured_local_ui_origin() -> None:
    client = TestClient(app)
    response = client.get("/v1/runs", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_environment_provisioning_run_and_usage() -> None:
    client = TestClient(app)

    tenant = client.post(
        "/v1/tenants",
        json={"name": "Pilot Corp"},
        headers={"Idempotency-Key": "tenant-1"},
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
        headers={"Idempotency-Key": "env-1"},
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
        headers={"Idempotency-Key": "job-1"},
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
        headers={"Idempotency-Key": "run-1"},
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

    op_status = client.get(f"/v1/provisioning-operations/{operation_id}")
    assert op_status.status_code == 200
    assert op_status.json()["state"] == "ready"


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
        headers={"Idempotency-Key": "tenant-gp"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-gp"},
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
        headers={"Idempotency-Key": "job-gp"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"golden_path": "medium-spot-graviton"},
        headers={"Idempotency-Key": "run-gp"},
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
        headers={"Idempotency-Key": "run-policy-block"},
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
        headers={"Idempotency-Key": "tenant-release-currency"},
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
        headers={"Idempotency-Key": "env-release-currency"},
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
        headers={"Idempotency-Key": "tenant-graviton-gate"},
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
        headers={"Idempotency-Key": "env-graviton-gate"},
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
        return TerraformApplyResult(
            ok=True,
            command=["terraform", "apply", context.stage],
            stdout_excerpt="ok",
            stderr_excerpt="",
            error=None,
        )

    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.plan", _plan)
    monkeypatch.setattr("sparkpilot.services.TerraformOrchestrator.apply", _apply)

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Full BYOC Checkpoint Tenant"},
        headers={"Idempotency-Key": "tenant-full-checkpoint"},
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
        headers={"Idempotency-Key": "env-full-checkpoint"},
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
        assert checkpoint.get("last_successful_stage") == "validating_runtime"

    assert plan_calls == ["provisioning_network", "provisioning_eks", "provisioning_emr"]
    assert apply_calls == ["provisioning_network", "provisioning_eks", "provisioning_emr"]


def test_full_byoc_plan_failure_preserves_prior_checkpoint(monkeypatch) -> None:
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
        headers={"Idempotency-Key": "tenant-plan-fail"},
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
        headers={"Idempotency-Key": "env-plan-fail"},
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
        headers={"Idempotency-Key": "tenant-apply-fail"},
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
        headers={"Idempotency-Key": "env-apply-fail"},
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
        json={"name": "Resume Tenant"},
        headers={"Idempotency-Key": "tenant-resume"},
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
        headers={"Idempotency-Key": "env-resume"},
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
        headers={"Idempotency-Key": "tenant-crash-durable"},
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
        headers={"Idempotency-Key": "env-crash-durable"},
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
        assert len(checkpoints) >= 2
        latest = checkpoints[-1]
        checkpoint = latest.details_json.get("checkpoint")
        assert isinstance(checkpoint, dict)
        assert checkpoint.get("last_successful_stage") == "provisioning_network"


def test_quota_enforcement() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Quota Inc"},
        headers={"Idempotency-Key": "tenant-q"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 1, "max_vcpu": 4, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-q"},
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
        headers={"Idempotency-Key": "job-q"},
    ).json()
    first = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"requested_resources": {"driver_vcpu": 1, "driver_memory_gb": 4, "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1}},
        headers={"Idempotency-Key": "run-q-1"},
    )
    assert first.status_code == 201
    second = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"requested_resources": {"driver_vcpu": 1, "driver_memory_gb": 4, "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1}},
        headers={"Idempotency-Key": "run-q-2"},
    )
    assert second.status_code == 429


def test_byoc_lite_environment_flow() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "BYOC Lite Tenant"},
        headers={"Idempotency-Key": "tenant-bl"},
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
        headers={"Idempotency-Key": "env-bl-1"},
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
        headers={"Idempotency-Key": "tenant-bl-trust"},
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
        headers={"Idempotency-Key": "env-bl-trust"},
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
        headers={"Idempotency-Key": "tenant-bl-trust-denied"},
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
        headers={"Idempotency-Key": "env-bl-trust-denied"},
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
        headers={"Idempotency-Key": "tenant-bl-oidc-missing"},
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
        headers={"Idempotency-Key": "env-bl-oidc-missing"},
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
        headers={"Idempotency-Key": "tenant-blv"},
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
        headers={"Idempotency-Key": "env-blv-1"},
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
        headers={"Idempotency-Key": "env-blv-2"},
    )
    assert missing_namespace.status_code == 422
    assert missing_namespace.json()["detail"] == "eks_namespace is required for byoc_lite."


def test_environment_preflight_endpoint_returns_checks() -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Preflight Tenant"},
        headers={"Idempotency-Key": "tenant-pf"},
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
        headers={"Idempotency-Key": "env-pf-1"},
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
        headers={"Idempotency-Key": "tenant-pf-run"},
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
        headers={"Idempotency-Key": "env-pf-run"},
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
        headers={"Idempotency-Key": "job-pf-run"},
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
        headers={"Idempotency-Key": "run-pf-run"},
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
        headers={"Idempotency-Key": "tenant-pf-mismatch"},
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
        headers={"Idempotency-Key": "env-pf-mismatch-a"},
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
        headers={"Idempotency-Key": "env-pf-mismatch-b"},
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
        headers={"Idempotency-Key": "job-pf-mismatch"},
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
        headers={"Idempotency-Key": "run-pf-mismatch"},
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
        headers={"Idempotency-Key": "tenant-pf-spot-warn"},
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
        headers={"Idempotency-Key": "env-pf-spot-warn"},
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
        headers={"Idempotency-Key": "tenant-spf"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-spf"},
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
        headers={"Idempotency-Key": "job-spf"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"requested_resources": {"driver_vcpu": 1, "driver_memory_gb": 4, "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1}},
        headers={"Idempotency-Key": "run-spf"},
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
        headers={"Idempotency-Key": "tenant-spf-dispatch"},
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
        headers={"Idempotency-Key": "env-spf-dispatch"},
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
        headers={"Idempotency-Key": "job-spf-dispatch"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"requested_resources": {"driver_vcpu": 1, "driver_memory_gb": 4, "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1}},
        headers={"Idempotency-Key": "run-spf-dispatch"},
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
        headers={"Idempotency-Key": "tenant-prereq-fail"},
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
        headers={"Idempotency-Key": "env-prereq-fail"},
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
        headers={"Idempotency-Key": "tenant-ns-len"},
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
        headers={"Idempotency-Key": "env-ns-len"},
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
        headers={"Idempotency-Key": "tenant-ns-collision"},
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
        headers={"Idempotency-Key": "env-ns-collision"},
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
        headers={"Idempotency-Key": "tenant-stale"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-stale"},
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
        headers={"Idempotency-Key": "job-stale"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"requested_resources": {"driver_vcpu": 1, "driver_memory_gb": 4, "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1}},
        headers={"Idempotency-Key": "run-stale"},
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
        headers={"Idempotency-Key": "tenant-accepted"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-accepted"},
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
        headers={"Idempotency-Key": "job-accepted"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={"requested_resources": {"driver_vcpu": 1, "driver_memory_gb": 4, "executor_vcpu": 1, "executor_memory_gb": 4, "executor_instances": 1}},
        headers={"Idempotency-Key": "run-accepted"},
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
        headers={"Idempotency-Key": "cancel-queued"},
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
        headers={"Idempotency-Key": "cancel-accepted"},
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
        headers={"Idempotency-Key": "cancel-running"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["state"] == "running"
    assert cancel_response.json()["cancellation_requested"] is True

    with SessionLocal() as db:
        processed = process_reconciler_once(db)
        assert processed == 1

    final = client.get(f"/v1/runs/{run['id']}").json()
    assert final["state"] == "cancelled"


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
        headers={"Idempotency-Key": "tenant-isolation-a"},
    ).json()
    tenant_b = client.post(
        "/v1/tenants",
        json={"name": "Tenant Isolation B"},
        headers={"Idempotency-Key": "tenant-isolation-b"},
    ).json()

    env_a_op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant_a["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::111111111111:role/SparkPilotCustomerRoleA",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-isolation-a"},
    ).json()
    env_b_op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant_b["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::222222222222:role/SparkPilotCustomerRoleB",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-isolation-b"},
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
        headers={"Idempotency-Key": "job-isolation-a"},
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
        headers={"Idempotency-Key": "job-isolation-b"},
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
        headers={"Idempotency-Key": "run-isolation-a"},
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
        headers={"Idempotency-Key": "run-isolation-b"},
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
