from datetime import UTC, datetime, timedelta
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SPARKPILOT_DATABASE_URL", "sqlite:///./sparkpilot_test.db")

from sparkpilot.api import app  # noqa: E402
from sparkpilot.db import Base, SessionLocal, engine  # noqa: E402
from sparkpilot.models import Run  # noqa: E402
from sparkpilot.services import _diagnostics_from_log_lines, process_provisioning_once, process_reconciler_once, process_scheduler_once  # noqa: E402
from tests.db_test_utils import reset_sqlite_test_db  # noqa: E402


def setup_function() -> None:
    reset_sqlite_test_db(base=Base, engine=engine, session_local=SessionLocal)


@pytest.mark.parametrize(
    ("line", "category"),
    [
        ("java.lang.OutOfMemoryError: Java heap space", "oom"),
        ("FetchFailedException: shuffle block fetch failed", "shuffle_fetch_failure"),
        ("Amazon S3 AccessDenied (403 Forbidden)", "s3_access_denied"),
        ("AnalysisException: cannot resolve column", "schema_mismatch"),
        ("Run exceeded timeout_seconds", "timeout"),
        ("Spot interruption termination notice received", "spot_interruption"),
    ],
)
def test_diagnostic_pattern_matching(line: str, category: str) -> None:
    result = _diagnostics_from_log_lines([line])
    assert any(item["category"] == category for item in result)


def test_reconciler_persists_diagnostics_and_api_exposes_them(monkeypatch) -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Diagnostics Tenant"},
        headers={"Idempotency-Key": "tenant-diag"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-diag"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": "job-diag",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
        },
        headers={"Idempotency-Key": "job-diag"},
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
        headers={"Idempotency-Key": "run-diag"},
    ).json()

    with SessionLocal() as db:
        process_scheduler_once(db)

    def _failed_state(*_args, **_kwargs):
        return "FAILED", "Run failed due to OutOfMemoryError"

    monkeypatch.setattr("sparkpilot.services.EmrEksClient.describe_job_run", _failed_state)
    monkeypatch.setattr(
        "sparkpilot.services.CloudWatchLogsProxy.fetch_lines",
        lambda *_args, **_kwargs: ["java.lang.OutOfMemoryError: Java heap space"],
    )

    with SessionLocal() as db:
        row = db.get(Run, run["id"])
        assert row is not None
        row.state = "accepted"
        row.started_at = datetime.now(UTC) - timedelta(minutes=2)
        db.commit()
        process_reconciler_once(db)

    diag = client.get(f"/v1/runs/{run['id']}/diagnostics")
    assert diag.status_code == 200
    payload = diag.json()
    assert payload["run_id"] == run["id"]
    assert len(payload["items"]) >= 1
    assert any(item["category"] == "oom" for item in payload["items"])

    paged = client.get(f"/v1/runs/{run['id']}/diagnostics?limit=1&offset=0")
    assert paged.status_code == 200
    assert len(paged.json()["items"]) == 1


def test_reconciler_records_unknown_failure_from_error_message_when_logs_empty(monkeypatch) -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Diagnostics Unknown Tenant"},
        headers={"Idempotency-Key": "tenant-diag-unknown"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-diag-unknown"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": "job-diag-unknown",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
        },
        headers={"Idempotency-Key": "job-diag-unknown"},
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
        headers={"Idempotency-Key": "run-diag-unknown"},
    ).json()

    with SessionLocal() as db:
        process_scheduler_once(db)

    expected_error = "Unhandled infrastructure fault without known signature"

    monkeypatch.setattr(
        "sparkpilot.services.EmrEksClient.describe_job_run",
        lambda *_args, **_kwargs: ("FAILED", expected_error),
    )
    monkeypatch.setattr(
        "sparkpilot.services.CloudWatchLogsProxy.fetch_lines",
        lambda *_args, **_kwargs: [],
    )

    with SessionLocal() as db:
        row = db.get(Run, run["id"])
        assert row is not None
        row.state = "accepted"
        row.started_at = datetime.now(UTC) - timedelta(minutes=2)
        db.commit()
        process_reconciler_once(db)

    diag = client.get(f"/v1/runs/{run['id']}/diagnostics")
    assert diag.status_code == 200
    payload = diag.json()
    assert any(item["category"] == "unknown_failure" for item in payload["items"])
    unknown = next(item for item in payload["items"] if item["category"] == "unknown_failure")
    assert expected_error in (unknown["log_snippet"] or "")


def test_reconciler_timeout_path_records_timeout_diagnostic(monkeypatch) -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Diagnostics Timeout Tenant"},
        headers={"Idempotency-Key": "tenant-diag-timeout"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-diag-timeout"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": "job-diag-timeout",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
            "timeout_seconds": 60,
        },
        headers={"Idempotency-Key": "job-diag-timeout"},
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
            },
            "timeout_seconds": 60,
        },
        headers={"Idempotency-Key": "run-diag-timeout"},
    ).json()

    with SessionLocal() as db:
        process_scheduler_once(db)
        row = db.get(Run, run["id"])
        assert row is not None
        row.state = "accepted"
        row.started_at = datetime.now(UTC) - timedelta(minutes=5)
        db.commit()

    monkeypatch.setattr(
        "sparkpilot.services.CloudWatchLogsProxy.fetch_lines",
        lambda *_args, **_kwargs: [],
    )

    with SessionLocal() as db:
        process_reconciler_once(db)

    diag = client.get(f"/v1/runs/{run['id']}/diagnostics")
    assert diag.status_code == 200
    payload = diag.json()
    assert any(item["category"] == "timeout" for item in payload["items"])


def test_reconciler_records_log_collection_error_when_cloudwatch_fetch_fails(monkeypatch) -> None:
    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "Diagnostics Log Failure Tenant"},
        headers={"Idempotency-Key": "tenant-diag-log-fail"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": "env-diag-log-fail"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": "job-diag-log-fail",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
        },
        headers={"Idempotency-Key": "job-diag-log-fail"},
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
        headers={"Idempotency-Key": "run-diag-log-fail"},
    ).json()

    with SessionLocal() as db:
        process_scheduler_once(db)

    monkeypatch.setattr(
        "sparkpilot.services.EmrEksClient.describe_job_run",
        lambda *_args, **_kwargs: ("FAILED", "Synthetic failure message"),
    )

    def _raise_fetch_failure(*_args, **_kwargs):
        raise RuntimeError("simulated log access denied")

    monkeypatch.setattr("sparkpilot.services.CloudWatchLogsProxy.fetch_lines", _raise_fetch_failure)

    with SessionLocal() as db:
        row = db.get(Run, run["id"])
        assert row is not None
        row.state = "accepted"
        row.started_at = datetime.now(UTC) - timedelta(minutes=2)
        db.commit()
        process_reconciler_once(db)

    diag = client.get(f"/v1/runs/{run['id']}/diagnostics")
    assert diag.status_code == 200
    payload = diag.json()
    assert any(item["category"] == "log_collection_error" for item in payload["items"])
    item = next(entry for entry in payload["items"] if entry["category"] == "log_collection_error")
    assert "simulated log access denied" in (item["log_snippet"] or "")
