from __future__ import annotations

import os

import conftest
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

os.environ.setdefault("SPARKPILOT_DATABASE_URL", "sqlite:///./sparkpilot_test.db")

from sparkpilot.api import app  # noqa: E402
from sparkpilot.db import Base, SessionLocal, engine  # noqa: E402
from sparkpilot.models import AuditEvent, UserIdentity  # noqa: E402
from sparkpilot.services import process_provisioning_once  # noqa: E402


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


def _headers(actor: str, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {conftest.issue_test_token(actor)}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _create_tenant(client: TestClient, *, actor: str, suffix: str) -> dict[str, object]:
    response = client.post(
        "/v1/tenants",
        json={"name": f"Tenant {suffix}"},
        headers=_headers(actor, f"tenant-{suffix}"),
    )
    assert response.status_code == 201
    return response.json()


def _create_environment(client: TestClient, *, actor: str, tenant_id: str, suffix: str) -> dict[str, object]:
    response = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant_id,
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": f"arn:aws:eks:us-east-1:123456789012:cluster/customer-{suffix}",
            "eks_namespace": f"sparkpilot-team-{suffix}",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers=_headers(actor, f"env-{suffix}"),
    )
    assert response.status_code == 201
    return response.json()


def _create_job(client: TestClient, *, actor: str, environment_id: str, suffix: str) -> dict[str, object]:
    response = client.post(
        "/v1/jobs",
        json={
            "environment_id": environment_id,
            "name": f"job-{suffix}",
            "artifact_uri": "s3://bucket/job.py",
            "artifact_digest": "sha256:abcd1234",
            "entrypoint": "main",
        },
        headers=_headers(actor, f"job-{suffix}"),
    )
    assert response.status_code == 201
    return response.json()


def _submit_run(client: TestClient, *, actor: str, job_id: str, suffix: str) -> dict[str, object]:
    response = client.post(
        f"/v1/jobs/{job_id}/runs",
        json={},
        headers=_headers(actor, f"run-{suffix}"),
    )
    assert response.status_code == 201
    return response.json()


def test_rbac_user_cannot_view_other_team_runs() -> None:
    client = TestClient(app)

    tenant = _create_tenant(client, actor="bootstrap-admin", suffix="rbac-a")
    env_a = _create_environment(client, actor="bootstrap-admin", tenant_id=str(tenant["id"]), suffix="rbac-a")
    env_b = _create_environment(client, actor="bootstrap-admin", tenant_id=str(tenant["id"]), suffix="rbac-b")
    with SessionLocal() as db:
        process_provisioning_once(db)
        process_provisioning_once(db)

    team_a = client.post(
        "/v1/teams",
        json={"tenant_id": tenant["id"], "name": "team-a"},
        headers=_headers("bootstrap-admin"),
    )
    assert team_a.status_code == 201
    team_b = client.post(
        "/v1/teams",
        json={"tenant_id": tenant["id"], "name": "team-b"},
        headers=_headers("bootstrap-admin"),
    )
    assert team_b.status_code == 201

    admin_identity = client.post(
        "/v1/user-identities",
        json={"actor": "bootstrap-admin", "role": "admin", "active": True},
        headers=_headers("bootstrap-admin"),
    )
    assert admin_identity.status_code == 201

    operator_a = client.post(
        "/v1/user-identities",
        json={
            "actor": "operator-a",
            "role": "operator",
            "tenant_id": tenant["id"],
            "team_id": team_a.json()["id"],
            "active": True,
        },
        headers=_headers("bootstrap-admin"),
    )
    assert operator_a.status_code == 201
    operator_b = client.post(
        "/v1/user-identities",
        json={
            "actor": "operator-b",
            "role": "operator",
            "tenant_id": tenant["id"],
            "team_id": team_b.json()["id"],
            "active": True,
        },
        headers=_headers("bootstrap-admin"),
    )
    assert operator_b.status_code == 201
    user_a = client.post(
        "/v1/user-identities",
        json={
            "actor": "user-a",
            "role": "user",
            "tenant_id": tenant["id"],
            "team_id": team_a.json()["id"],
            "active": True,
        },
        headers=_headers("bootstrap-admin"),
    )
    assert user_a.status_code == 201
    user_b = client.post(
        "/v1/user-identities",
        json={
            "actor": "user-b",
            "role": "user",
            "tenant_id": tenant["id"],
            "team_id": team_b.json()["id"],
            "active": True,
        },
        headers=_headers("bootstrap-admin"),
    )
    assert user_b.status_code == 201

    scope_a = client.post(
        f"/v1/teams/{team_a.json()['id']}/environments/{env_a['environment_id']}",
        headers=_headers("bootstrap-admin"),
    )
    assert scope_a.status_code == 201
    scope_b = client.post(
        f"/v1/teams/{team_b.json()['id']}/environments/{env_b['environment_id']}",
        headers=_headers("bootstrap-admin"),
    )
    assert scope_b.status_code == 201

    job_a = _create_job(client, actor="bootstrap-admin", environment_id=str(env_a["environment_id"]), suffix="rbac-a")
    job_b = _create_job(client, actor="bootstrap-admin", environment_id=str(env_b["environment_id"]), suffix="rbac-b")
    run_a = _submit_run(client, actor="user-a", job_id=str(job_a["id"]), suffix="rbac-a")
    run_b = _submit_run(client, actor="user-b", job_id=str(job_b["id"]), suffix="rbac-b")

    user_a_runs = client.get("/v1/runs", headers=_headers("user-a"))
    assert user_a_runs.status_code == 200
    assert {item["id"] for item in user_a_runs.json()} == {run_a["id"]}

    user_a_blocked = client.get(f"/v1/runs/{run_b['id']}", headers=_headers("user-a"))
    assert user_a_blocked.status_code == 403

    operator_a_runs = client.get(f"/v1/runs?tenant_id={tenant['id']}", headers=_headers("operator-a"))
    assert operator_a_runs.status_code == 200
    assert {item["id"] for item in operator_a_runs.json()} == {run_a["id"]}

    operator_a_blocked = client.get(f"/v1/runs/{run_b['id']}", headers=_headers("operator-a"))
    assert operator_a_blocked.status_code == 403


def test_rbac_admin_with_identity_can_list_runs() -> None:
    client = TestClient(app)

    tenant = _create_tenant(client, actor="bootstrap-admin", suffix="rbac-admin-list")
    env = _create_environment(
        client,
        actor="bootstrap-admin",
        tenant_id=str(tenant["id"]),
        suffix="rbac-admin-list",
    )
    with SessionLocal() as db:
        process_provisioning_once(db)

    admin_identity = client.post(
        "/v1/user-identities",
        json={"actor": "bootstrap-admin", "role": "admin", "active": True},
        headers=_headers("bootstrap-admin"),
    )
    assert admin_identity.status_code == 201

    job = _create_job(
        client,
        actor="bootstrap-admin",
        environment_id=str(env["environment_id"]),
        suffix="rbac-admin-list",
    )
    run = _submit_run(client, actor="bootstrap-admin", job_id=str(job["id"]), suffix="rbac-admin-list")

    listed = client.get("/v1/runs", headers=_headers("bootstrap-admin"))
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} == {run["id"]}


def test_rbac_operator_job_listing_is_scope_filtered() -> None:
    client = TestClient(app)

    tenant = _create_tenant(client, actor="bootstrap-admin", suffix="rbac-jobscope")
    env_a = _create_environment(
        client,
        actor="bootstrap-admin",
        tenant_id=str(tenant["id"]),
        suffix="rbac-jobscope-a",
    )
    env_b = _create_environment(
        client,
        actor="bootstrap-admin",
        tenant_id=str(tenant["id"]),
        suffix="rbac-jobscope-b",
    )
    with SessionLocal() as db:
        process_provisioning_once(db)
        process_provisioning_once(db)

    team = client.post(
        "/v1/teams",
        json={"tenant_id": tenant["id"], "name": "team-jobscope"},
        headers=_headers("bootstrap-admin"),
    )
    assert team.status_code == 201

    operator_identity = client.post(
        "/v1/user-identities",
        json={
            "actor": "operator-jobscope",
            "role": "operator",
            "tenant_id": tenant["id"],
            "team_id": team.json()["id"],
            "active": True,
        },
        headers=_headers("bootstrap-admin"),
    )
    assert operator_identity.status_code == 201

    scope = client.post(
        f"/v1/teams/{team.json()['id']}/environments/{env_a['environment_id']}",
        headers=_headers("bootstrap-admin"),
    )
    assert scope.status_code == 201

    job_a = _create_job(
        client,
        actor="bootstrap-admin",
        environment_id=str(env_a["environment_id"]),
        suffix="rbac-jobscope-a",
    )
    _create_job(
        client,
        actor="bootstrap-admin",
        environment_id=str(env_b["environment_id"]),
        suffix="rbac-jobscope-b",
    )

    listed = client.get("/v1/jobs", headers=_headers("operator-jobscope"))
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} == {job_a["id"]}

    filtered_allowed = client.get(
        f"/v1/jobs?environment_id={env_a['environment_id']}",
        headers=_headers("operator-jobscope"),
    )
    assert filtered_allowed.status_code == 200
    assert {item["id"] for item in filtered_allowed.json()} == {job_a["id"]}

    filtered_forbidden = client.get(
        f"/v1/jobs?environment_id={env_b['environment_id']}",
        headers=_headers("operator-jobscope"),
    )
    assert filtered_forbidden.status_code == 403


def test_rbac_admin_can_paginate_team_environment_scopes() -> None:
    client = TestClient(app)

    tenant = _create_tenant(client, actor="bootstrap-admin", suffix="rbac-scope-page")
    env_a = _create_environment(
        client,
        actor="bootstrap-admin",
        tenant_id=str(tenant["id"]),
        suffix="rbac-scope-page-a",
    )
    env_b = _create_environment(
        client,
        actor="bootstrap-admin",
        tenant_id=str(tenant["id"]),
        suffix="rbac-scope-page-b",
    )
    with SessionLocal() as db:
        process_provisioning_once(db)
        process_provisioning_once(db)

    admin_identity = client.post(
        "/v1/user-identities",
        json={"actor": "bootstrap-admin", "role": "admin", "active": True},
        headers=_headers("bootstrap-admin"),
    )
    assert admin_identity.status_code == 201

    team = client.post(
        "/v1/teams",
        json={"tenant_id": tenant["id"], "name": "team-scope-page"},
        headers=_headers("bootstrap-admin"),
    )
    assert team.status_code == 201
    team_id = team.json()["id"]

    scope_a = client.post(
        f"/v1/teams/{team_id}/environments/{env_a['environment_id']}",
        headers=_headers("bootstrap-admin"),
    )
    assert scope_a.status_code == 201
    scope_b = client.post(
        f"/v1/teams/{team_id}/environments/{env_b['environment_id']}",
        headers=_headers("bootstrap-admin"),
    )
    assert scope_b.status_code == 201

    page_one = client.get(
        f"/v1/teams/{team_id}/environments?limit=1&offset=0",
        headers=_headers("bootstrap-admin"),
    )
    page_two = client.get(
        f"/v1/teams/{team_id}/environments?limit=1&offset=1",
        headers=_headers("bootstrap-admin"),
    )
    assert page_one.status_code == 200
    assert page_two.status_code == 200
    assert len(page_one.json()) == 1
    assert len(page_two.json()) == 1
    combined = {item["id"] for item in page_one.json()} | {item["id"] for item in page_two.json()}
    assert len(combined) == 2


def test_rbac_role_permissions_admin_operator_user() -> None:
    client = TestClient(app)

    tenant = _create_tenant(client, actor="bootstrap-admin", suffix="rbac-role")
    admin_identity = client.post(
        "/v1/user-identities",
        json={"actor": "bootstrap-admin", "role": "admin", "active": True},
        headers=_headers("bootstrap-admin"),
    )
    assert admin_identity.status_code == 201
    team = client.post(
        "/v1/teams",
        json={"tenant_id": tenant["id"], "name": "team-role"},
        headers=_headers("bootstrap-admin"),
    )
    assert team.status_code == 201

    operator_identity = client.post(
        "/v1/user-identities",
        json={
            "actor": "operator-role",
            "role": "operator",
            "tenant_id": tenant["id"],
            "team_id": team.json()["id"],
            "active": True,
        },
        headers=_headers("bootstrap-admin"),
    )
    assert operator_identity.status_code == 201
    user_identity = client.post(
        "/v1/user-identities",
        json={
            "actor": "user-role",
            "role": "user",
            "tenant_id": tenant["id"],
            "team_id": team.json()["id"],
            "active": True,
        },
        headers=_headers("bootstrap-admin"),
    )
    assert user_identity.status_code == 201

    operator_cannot_create_tenant = client.post(
        "/v1/tenants",
        json={"name": "Blocked Tenant"},
        headers=_headers("operator-role", "tenant-blocked"),
    )
    assert operator_cannot_create_tenant.status_code == 403

    operator_cannot_create_environment = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers=_headers("operator-role", "env-blocked"),
    )
    assert operator_cannot_create_environment.status_code == 403

    budget = client.post(
        "/v1/team-budgets",
        json={"team": tenant["id"], "monthly_budget_usd_micros": 100_000_000},
        headers=_headers("bootstrap-admin"),
    )
    assert budget.status_code == 201

    operator_budget = client.get(f"/v1/team-budgets/{tenant['id']}", headers=_headers("operator-role"))
    assert operator_budget.status_code == 200

    user_budget = client.get(f"/v1/team-budgets/{tenant['id']}", headers=_headers("user-role"))
    assert user_budget.status_code == 403

    user_cannot_create_job = client.post(
        "/v1/jobs",
        json={
            "environment_id": "missing",
            "name": "blocked",
            "artifact_uri": "s3://bucket/job.py",
            "artifact_digest": "sha256:abcd1234",
            "entrypoint": "main",
        },
        headers=_headers("user-role", "job-blocked"),
    )
    assert user_cannot_create_job.status_code == 403


def test_rbac_operator_without_scope_cannot_access_environment() -> None:
    client = TestClient(app)

    tenant = _create_tenant(client, actor="bootstrap-admin", suffix="rbac-noscope")
    env = _create_environment(client, actor="bootstrap-admin", tenant_id=str(tenant["id"]), suffix="rbac-noscope")
    with SessionLocal() as db:
        process_provisioning_once(db)

    admin_identity = client.post(
        "/v1/user-identities",
        json={"actor": "bootstrap-admin", "role": "admin", "active": True},
        headers=_headers("bootstrap-admin"),
    )
    assert admin_identity.status_code == 201
    team = client.post(
        "/v1/teams",
        json={"tenant_id": tenant["id"], "name": "team-noscope"},
        headers=_headers("bootstrap-admin"),
    )
    assert team.status_code == 201
    operator = client.post(
        "/v1/user-identities",
        json={
            "actor": "operator-noscope",
            "role": "operator",
            "tenant_id": tenant["id"],
            "team_id": team.json()["id"],
            "active": True,
        },
        headers=_headers("bootstrap-admin"),
    )
    assert operator.status_code == 201

    forbidden_env = client.get(
        f"/v1/environments/{env['environment_id']}",
        headers=_headers("operator-noscope"),
    )
    assert forbidden_env.status_code == 403


def test_rbac_mutations_are_audited() -> None:
    client = TestClient(app)

    tenant = _create_tenant(client, actor="bootstrap-admin", suffix="rbac-audit")
    env = _create_environment(client, actor="bootstrap-admin", tenant_id=str(tenant["id"]), suffix="rbac-audit")
    with SessionLocal() as db:
        process_provisioning_once(db)

    admin_identity = client.post(
        "/v1/user-identities",
        json={"actor": "bootstrap-admin", "role": "admin", "active": True},
        headers=_headers("bootstrap-admin"),
    )
    assert admin_identity.status_code == 201

    team = client.post(
        "/v1/teams",
        json={"tenant_id": tenant["id"], "name": "team-audit"},
        headers=_headers("bootstrap-admin"),
    )
    assert team.status_code == 201

    operator = client.post(
        "/v1/user-identities",
        json={
            "actor": "operator-audit",
            "role": "operator",
            "tenant_id": tenant["id"],
            "team_id": team.json()["id"],
            "active": True,
        },
        headers=_headers("bootstrap-admin"),
    )
    assert operator.status_code == 201

    scope = client.post(
        f"/v1/teams/{team.json()['id']}/environments/{env['environment_id']}",
        headers=_headers("bootstrap-admin"),
    )
    assert scope.status_code == 201

    with SessionLocal() as db:
        actions = [
            row[0]
            for row in db.execute(
                select(AuditEvent.action).where(
                    AuditEvent.action.in_(
                        {
                            "team.create",
                            "user_identity.create",
                            "team_environment_scope.create",
                        }
                    )
                )
            ).all()
        ]
    assert "team.create" in actions
    assert "user_identity.create" in actions
    assert "team_environment_scope.create" in actions


def test_first_identity_requires_bootstrap_secret_and_matching_subject(oidc_token) -> None:
    client = TestClient(app)
    create_first_identity = client.post(
        "/v1/user-identities",
        json={"actor": "bootstrap-admin", "role": "admin", "active": True},
        headers={
            "Authorization": f"Bearer {oidc_token('bootstrap-admin')}",
            "X-Skip-Test-Bootstrap": "true",
        },
    )
    assert create_first_identity.status_code == 401


def test_user_identity_role_check_constraint_rejects_invalid_value() -> None:
    with SessionLocal() as db:
        db.add(UserIdentity(actor="bad-role-actor", role="superadmin", active=True))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
