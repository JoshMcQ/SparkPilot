from datetime import UTC, datetime, timedelta
import os

from fastapi.testclient import TestClient

os.environ.setdefault("SPARKPILOT_DATABASE_URL", "sqlite:///./sparkpilot_test.db")

from sparkpilot.api import app  # noqa: E402
from sparkpilot.db import Base, SessionLocal, engine, init_db  # noqa: E402
from sparkpilot.models import AuditEvent, Environment, IdempotencyRecord, Job, ProvisioningOperation, Run, Tenant, UsageRecord  # noqa: E402
from sparkpilot.services import process_provisioning_once, process_reconciler_once, process_scheduler_once  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    init_db()


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

    op_status = client.get(f"/v1/provisioning-operations/{operation_id}")
    assert op_status.status_code == 200
    assert op_status.json()["state"] == "ready"


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
