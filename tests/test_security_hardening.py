from pathlib import Path

from fastapi.testclient import TestClient

from sparkpilot.api import app
from sparkpilot.config import get_settings
from sparkpilot.db import Base, engine, init_db


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    init_db()


def teardown_function() -> None:
    get_settings.cache_clear()


def test_missing_bearer_token_is_rejected() -> None:
    client = TestClient(app)
    missing_auth = client.get("/v1/runs", headers={"Authorization": ""})
    assert missing_auth.status_code == 401


def test_invalid_bearer_token_is_rejected() -> None:
    client = TestClient(app)
    invalid = client.get("/v1/runs", headers={"Authorization": "Bearer invalid-token"})
    assert invalid.status_code == 401


def test_self_declared_actor_header_cannot_escalate_privileges(oidc_token) -> None:
    client = TestClient(app)

    tenant = client.post(
        "/v1/tenants",
        json={"name": "security-tenant"},
        headers={"Idempotency-Key": "security-tenant"},
    )
    assert tenant.status_code == 201

    team = client.post(
        "/v1/teams",
        json={"tenant_id": tenant.json()["id"], "name": "security-team"},
    )
    assert team.status_code == 201

    identity = client.post(
        "/v1/user-identities",
        json={
            "actor": "limited-user",
            "role": "user",
            "tenant_id": tenant.json()["id"],
            "team_id": team.json()["id"],
            "active": True,
        },
    )
    assert identity.status_code == 201

    # Token subject is limited-user; forged X-Actor admin header must be ignored.
    request = client.post(
        "/v1/tenants",
        json={"name": "should-fail"},
        headers={
            "Authorization": f"Bearer {oidc_token('limited-user')}",
            "X-Actor": "test-user",
            "Idempotency-Key": "security-escalation-attempt",
        },
    )
    assert request.status_code == 403


def test_live_full_mode_is_blocked_without_full_byoc_modules(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv("SPARKPILOT_ENABLE_FULL_BYOC_MODE", "true")
    monkeypatch.setenv("SPARKPILOT_EMR_EXECUTION_ROLE_ARN", "arn:aws:iam::123456789012:role/SparkPilotExecRole")
    monkeypatch.setattr("sparkpilot.services.crud.FULL_BYOC_TERRAFORM_ROOT", Path("infra/terraform/full-byoc-missing"))
    get_settings.cache_clear()

    client = TestClient(app)
    tenant = client.post(
        "/v1/tenants",
        json={"name": "full-mode-guard"},
        headers={"Idempotency-Key": "full-mode-tenant"},
    )
    assert tenant.status_code == 201
    tenant_id = tenant.json()["id"]

    environment = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant_id,
            "provisioning_mode": "full",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        },
        headers={"Idempotency-Key": "full-mode-env"},
    )
    assert environment.status_code == 422
    assert "missing Terraform modules" in environment.json()["detail"]
