from __future__ import annotations

from sparkpilot.api import app
from sparkpilot.db import Base, SessionLocal, engine
from tests.conftest import TEST_BOOTSTRAP_SECRET, _BaseTestClient, issue_test_token
from tests.db_test_utils import reset_sqlite_test_db


def test_oidc_bootstrap_and_auth_me_flow_e2e() -> None:
    reset_sqlite_test_db(base=Base, engine=engine, session_local=SessionLocal)

    actor = "e2e-cognito-admin-subject"
    token = issue_test_token(actor)
    auth_headers = {"Authorization": f"Bearer {token}"}

    with _BaseTestClient(app) as client:
        unauthenticated = client.get("/v1/environments")
        assert unauthenticated.status_code == 401

        unknown_actor = client.get("/v1/environments", headers=auth_headers)
        assert unknown_actor.status_code == 403
        assert unknown_actor.json()["detail"] == "Unknown or inactive actor."

        bootstrap = client.post(
            "/v1/bootstrap/user-identities",
            headers={
                **auth_headers,
                "X-Bootstrap-Secret": TEST_BOOTSTRAP_SECRET,
            },
        )
        assert bootstrap.status_code == 201
        bootstrap_payload = bootstrap.json()
        assert bootstrap_payload["actor"] == actor
        assert bootstrap_payload["role"] == "admin"
        assert bootstrap_payload["active"] is True

        auth_me = client.get("/v1/auth/me", headers=auth_headers)
        assert auth_me.status_code == 200
        auth_me_payload = auth_me.json()
        assert auth_me_payload["actor"] == actor
        assert auth_me_payload["role"] == "admin"

        tenant = client.post(
            "/v1/tenants",
            json={"name": "OIDC Bootstrap E2E Tenant"},
            headers={**auth_headers, "Idempotency-Key": "oidc-e2e-tenant"},
        )
        assert tenant.status_code == 201
        tenant_id = tenant.json()["id"]

        environment = client.post(
            "/v1/environments",
            json={
                "tenant_id": tenant_id,
                "provisioning_mode": "byoc_lite",
                "region": "us-east-1",
                "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
                "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/e2e-test-cluster",
                "eks_namespace": "sparkpilot-e2e",
            },
            headers={**auth_headers, "Idempotency-Key": "oidc-e2e-environment"},
        )
        assert environment.status_code == 201
