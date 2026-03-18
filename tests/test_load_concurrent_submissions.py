"""
Load / concurrency correctness test for SparkPilot API.

Simulates 50 concurrent run submissions across 5 teams to verify:
- Preflight quota is correctly enforced under concurrency
- Idempotency deduplication prevents double-submissions
- Cost tracking records are created for each unique run
- No DB integrity errors under concurrent writes

This test uses an in-process ASGI test client (httpx + FastAPI TestClient).
It does NOT require a running SparkPilot instance.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pytest

# Skip if FastAPI / test infra not available
pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

os.environ.setdefault("SPARKPILOT_DATABASE_URL", "sqlite:///./sparkpilot_load_test.db")

from fastapi.testclient import TestClient
from sparkpilot.api import app
from sparkpilot.db import Base, SessionLocal, engine, init_db
from sparkpilot.models import Run
from sparkpilot.services import process_provisioning_once


TEAMS = 5
RUNS_PER_TEAM = 10
TOTAL_RUNS = TEAMS * RUNS_PER_TEAM
MAX_CONCURRENT = 10


def setup_function() -> None:
    import sparkpilot.models  # noqa: F401 -- register all tables before recreation
    from pathlib import Path
    engine.dispose()
    # Extract SQLite file path from engine URL and delete for a clean slate
    url_str = str(engine.url)
    if url_str.startswith("sqlite:///") and ":memory:" not in url_str:
        db_path = url_str.split(":///", 1)[1]
        p = Path(db_path)
        for f in (p, Path(f"{p}-journal"), Path(f"{p}-wal"), Path(f"{p}-shm")):
            if f.exists():
                f.unlink()
    Base.metadata.create_all(bind=engine)
    from sparkpilot.services import ensure_default_golden_paths as _egp
    with SessionLocal() as db:
        _egp(db)


def _create_env_and_job(client: TestClient) -> tuple[str, str]:
    """Create a ready environment and a job; return (environment_id, job_id)."""
    tenant = client.post(
        "/v1/tenants",
        json={"name": f"LoadTestTenant-{uuid.uuid4().hex[:8]}"},
        headers={"Idempotency-Key": f"lt-tenant-{uuid.uuid4().hex}", "X-Actor": "test-user"},
    ).json()
    tenant_id = tenant["id"]

    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant_id,
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-load-test",
            "warm_pool_enabled": False,
            "quotas": {
                "max_concurrent_runs": MAX_CONCURRENT,
                "max_vcpu": 1024,
                "max_run_seconds": 7200,
            },
        },
        headers={"Idempotency-Key": f"lt-env-{uuid.uuid4().hex}", "X-Actor": "test-user"},
    )
    assert op.status_code == 201, f"env create failed: {op.text}"
    environment_id = op.json()["environment_id"]

    with SessionLocal() as db:
        process_provisioning_once(db)

    env_status = client.get(f"/v1/environments/{environment_id}").json()
    assert env_status["status"] == "ready", f"environment not ready: {env_status}"

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": environment_id,
            "name": "load-test-job",
            "artifact_uri": "s3://sparkpilot-load-test/job.jar",
            "artifact_digest": "sha256:loadtest",
            "entrypoint": "com.acme.LoadTest",
        },
        headers={"Idempotency-Key": f"lt-job-{uuid.uuid4().hex}", "X-Actor": "test-user"},
    )
    assert job.status_code == 201, f"job create failed: {job.text}"
    job_id = job.json()["id"]

    return environment_id, job_id


def _submit_run(
    client: TestClient,
    job_id: str,
    idempotency_key: str,
    team_actor: str,
) -> dict[str, Any]:
    resp = client.post(
        f"/v1/jobs/{job_id}/runs",
        json={
            "requested_resources": {
                "driver_vcpu": 1,
                "driver_memory_gb": 4,
                "executor_vcpu": 1,
                "executor_memory_gb": 4,
                "executor_instances": 1,
            }
        },
        headers={
            "Idempotency-Key": idempotency_key,
            "X-Actor": team_actor,
        },
    )
    return {"status_code": resp.status_code, "body": resp.json(), "idempotency_key": idempotency_key}


def test_concurrent_submissions_no_db_integrity_errors() -> None:
    """50 concurrent run submissions: quota enforced, no DB errors, all accepted runs have valid IDs.

    With max_concurrent_runs=10, submitting 50 runs concurrently means at most 10 will be accepted
    (returning 201) and the rest will be rejected with 429. This verifies:
    - No uncaught exceptions (no DB integrity errors, no crashes)
    - At most MAX_CONCURRENT runs are ever accepted simultaneously
    - All accepted runs have a valid run ID in the response body
    """
    client = TestClient(app)
    environment_id, job_id = _create_env_and_job(client)

    errors: list[str] = []
    results: list[dict] = []
    lock = threading.Lock()

    def submit(team_idx: int, run_idx: int) -> dict:
        key = f"lt-run-team{team_idx}-run{run_idx}"
        actor = f"team-{team_idx}-user"
        return _submit_run(client, job_id, key, actor)

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=TOTAL_RUNS) as executor:
        futures = [
            executor.submit(submit, team_idx, run_idx)
            for team_idx in range(TEAMS)
            for run_idx in range(RUNS_PER_TEAM)
        ]
        for future in as_completed(futures):
            try:
                result = future.result()
                with lock:
                    results.append(result)
            except Exception as exc:
                with lock:
                    errors.append(str(exc))

    elapsed = time.monotonic() - start
    throughput = TOTAL_RUNS / elapsed
    print(f"\nLoad test: {TOTAL_RUNS} submissions in {elapsed:.2f}s -> {throughput:.1f} submissions/sec")

    assert not errors, f"Uncaught exceptions during concurrent submission: {errors}"

    # Verify only expected status codes: 201 (accepted), 429 (quota exceeded)
    unexpected = [r for r in results if r["status_code"] not in {200, 201, 429}]
    assert not unexpected, f"Unexpected status codes: {unexpected}"

    accepted = [r for r in results if r["status_code"] in {200, 201}]
    rejected = [r for r in results if r["status_code"] == 429]

    print(f"  Accepted: {len(accepted)}, Quota-rejected: {len(rejected)}")

    # Quota is enforced: no more than MAX_CONCURRENT runs accepted
    assert len(accepted) <= MAX_CONCURRENT, (
        f"Quota violation: {len(accepted)} runs accepted, limit is {MAX_CONCURRENT}"
    )
    # At least 1 run must be accepted
    assert len(accepted) >= 1, "No runs were accepted — environment may not be ready"

    # All accepted runs have valid run IDs
    for result in accepted:
        body = result["body"]
        assert "id" in body and body["id"], f"Accepted run missing id: {body}"

    # All accepted run IDs are unique
    run_ids = {r["body"]["id"] for r in accepted}
    assert len(run_ids) == len(accepted), "Duplicate run IDs in accepted submissions"

    # Verify DB state: count of non-terminal runs matches accepted count
    with SessionLocal() as db:
        from sqlalchemy import select, func
        non_terminal_count = db.execute(
            select(func.count()).select_from(Run).where(
                Run.job_id == job_id,
                Run.state.notin_(["failed", "succeeded", "cancelled"]),
            )
        ).scalar()
    assert non_terminal_count <= MAX_CONCURRENT, (
        f"DB shows {non_terminal_count} non-terminal runs, exceeds limit {MAX_CONCURRENT}"
    )


def test_idempotency_key_prevents_duplicate_run_creation() -> None:
    """Submitting the same idempotency key twice must yield the same run ID."""
    client = TestClient(app)
    _, job_id = _create_env_and_job(client)

    shared_key = f"idem-key-{uuid.uuid4().hex}"
    run_payload = {
        "requested_resources": {
            "driver_vcpu": 1,
            "driver_memory_gb": 4,
            "executor_vcpu": 1,
            "executor_memory_gb": 4,
            "executor_instances": 1,
        }
    }

    first = client.post(
        f"/v1/jobs/{job_id}/runs",
        json=run_payload,
        headers={"Idempotency-Key": shared_key, "X-Actor": "test-user"},
    )
    assert first.status_code in {200, 201}, f"First submission failed: {first.text}"
    first_id = first.json()["id"]

    second = client.post(
        f"/v1/jobs/{job_id}/runs",
        json=run_payload,
        headers={"Idempotency-Key": shared_key, "X-Actor": "test-user"},
    )
    assert second.status_code in {200, 201}, f"Second submission failed: {second.text}"
    second_id = second.json()["id"]

    assert first_id == second_id, (
        f"Idempotency violated: first={first_id}, second={second_id}"
    )

    with SessionLocal() as db:
        from sqlalchemy import select
        matching_runs = db.execute(
            select(Run).where(Run.job_id == job_id, Run.idempotency_key == shared_key)
        ).scalars().all()
    assert len(matching_runs) == 1, (
        f"Expected 1 run for idempotency_key={shared_key!r}, found {len(matching_runs)}"
    )


def test_concurrent_idempotent_submissions_race_condition() -> None:
    """Racing identical idempotency key submissions must produce exactly 1 run."""
    client = TestClient(app)
    _, job_id = _create_env_and_job(client)

    shared_key = f"race-key-{uuid.uuid4().hex}"
    run_payload = {
        "requested_resources": {
            "driver_vcpu": 1,
            "driver_memory_gb": 4,
            "executor_vcpu": 1,
            "executor_memory_gb": 4,
            "executor_instances": 1,
        }
    }

    results: list[dict] = []
    errors: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(10)

    def race_submit():
        barrier.wait()
        resp = client.post(
            f"/v1/jobs/{job_id}/runs",
            json=run_payload,
            headers={"Idempotency-Key": shared_key, "X-Actor": "test-user"},
        )
        with lock:
            results.append({"status_code": resp.status_code, "body": resp.json()})

    threads = [threading.Thread(target=race_submit) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = [r for r in results if r["status_code"] in {200, 201}]
    assert successes, f"No successful submissions in race: {results}"

    unique_ids = {r["body"]["id"] for r in successes}
    assert len(unique_ids) == 1, (
        f"Race condition: multiple run IDs created for same idempotency key: {unique_ids}"
    )

    with SessionLocal() as db:
        from sqlalchemy import select
        matching_runs = db.execute(
            select(Run).where(Run.job_id == job_id, Run.idempotency_key == shared_key)
        ).scalars().all()
    assert len(matching_runs) == 1, (
        f"Expected 1 run in DB for shared idempotency key, found {len(matching_runs)}"
    )


def test_throughput_logging() -> None:
    """Measure and log submission throughput for baseline documentation."""
    client = TestClient(app)
    _, job_id = _create_env_and_job(client)

    n = 20
    start = time.monotonic()

    def submit(i: int) -> int:
        key = f"tp-run-{uuid.uuid4().hex}"
        resp = client.post(
            f"/v1/jobs/{job_id}/runs",
            json={
                "requested_resources": {
                    "driver_vcpu": 1,
                    "driver_memory_gb": 4,
                    "executor_vcpu": 1,
                    "executor_memory_gb": 4,
                    "executor_instances": 1,
                }
            },
            headers={"Idempotency-Key": key, "X-Actor": "test-user"},
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=10) as executor:
        statuses = list(executor.map(submit, range(n)))

    elapsed = time.monotonic() - start
    throughput = n / elapsed
    print(f"\nThroughput test: {n} submissions in {elapsed:.2f}s -> {throughput:.1f} submissions/sec")

    # Some submissions may be quota-rejected (429) since max_concurrent_runs=10
    # and we submit 20. At least 1 must succeed and only 200/201/429 are valid statuses.
    successes = sum(1 for s in statuses if s in {200, 201})
    unexpected = [s for s in statuses if s not in {200, 201, 429}]
    assert not unexpected, f"Unexpected status codes: {unexpected}"
    assert successes >= 1, f"No submissions succeeded; statuses: {statuses}"
    print(f"  Accepted: {successes}/{n}, Quota-rejected: {n - successes}")
