from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from sparkpilot.api import app
from sparkpilot.db import Base, SessionLocal, engine
from sparkpilot.services import ensure_default_golden_paths, process_provisioning_once


def setup_function() -> None:
    import sparkpilot.models  # noqa: F401 -- ensure model registry is loaded

    engine.dispose()
    url_str = str(engine.url)
    if "sqlite:///" in url_str:
        db_path = Path(url_str.split("sqlite:///", 1)[1])
        if db_path.exists():
            db_path.unlink()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_default_golden_paths(db)


def _create_tenant(client: TestClient, suffix: str) -> str:
    response = client.post(
        "/v1/tenants",
        json={"name": f"runtime-{suffix}", "slug": f"runtime-{suffix}"},
        headers={"Idempotency-Key": f"tenant-{suffix}", "X-Actor": "test-user"},
    )
    assert response.status_code == 201, response.json()
    return response.json()["id"]


@pytest.mark.parametrize("engine_name", ["emr_serverless", "emr_on_ec2"])
def test_non_eks_dry_run_environment_reaches_ready(engine_name: str) -> None:
    client = TestClient(app)
    tenant_id = _create_tenant(client, engine_name.replace("_", "-"))
    create = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant_id,
            "engine": engine_name,
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "warm_pool_enabled": False,
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": f"runtime-create-{engine_name}", "X-Actor": "test-user"},
    )
    assert create.status_code == 201, create.json()
    payload = create.json()
    environment_id = payload["environment_id"]

    with SessionLocal() as db:
        processed = process_provisioning_once(db, actor="worker:test")
        assert processed >= 1

    detail = client.get(f"/v1/environments/{environment_id}", headers={"X-Actor": "test-user"})
    assert detail.status_code == 200, detail.json()
    body = detail.json()
    assert body["engine"] == engine_name
    assert body["status"] == "ready"
