from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from sparkpilot.api import _oidc_verifier, app
from sparkpilot.config import get_settings
from sparkpilot.db import Base, SessionLocal, engine
from sparkpilot.models import MagicLinkLog, MagicLinkToken, User, UserIdentity
from tests.conftest import _BaseTestClient, issue_test_token
from tests.db_test_utils import reset_sqlite_test_db


def _reset_db() -> None:
    reset_sqlite_test_db(base=Base, engine=engine, session_local=SessionLocal)


def _set_internal_admin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKPILOT_INTERNAL_ADMINS", "ops@sparkpilot.cloud")
    monkeypatch.setenv(
        "SPARKPILOT_COGNITO_HOSTED_UI_URL", "https://auth.example.com/oauth2/authorize"
    )
    monkeypatch.setenv("SPARKPILOT_MAGIC_LINK_TTL_HOURS", "24")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()


def _auth_headers(subject: str, email: str) -> dict[str, str]:
    token = issue_test_token(subject, extra_claims={"email": email})
    return {"Authorization": f"Bearer {token}"}


def test_require_internal_admin_dependency_enforces_authn_and_email_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    _set_internal_admin_env(monkeypatch)

    with _BaseTestClient(app) as client:
        unauthenticated = client.get("/v1/internal/tenants")
        assert unauthenticated.status_code == 401

        non_internal = client.get(
            "/v1/internal/tenants",
            headers=_auth_headers("staff-subject", "staff@sparkpilot.cloud"),
        )
        assert non_internal.status_code == 403
        assert non_internal.json()["detail"] == "Internal admin access required"

        internal = client.get(
            "/v1/internal/tenants",
            headers=_auth_headers("ops-subject", "ops@sparkpilot.cloud"),
        )
        assert internal.status_code == 200
        assert internal.json() == []


def test_internal_tenant_invite_happy_path_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "ops@sparkpilot.cloud")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Acme Corp",
                "admin_email": "admin@acme.example",
                "federation_type": "oidc",
                "idp_metadata": {"issuer": "https://idp.example.com"},
            },
            headers=internal_headers,
        )
        assert create.status_code == 201, create.text
        created = create.json()
        tenant_id = created["tenant_id"]
        user_id = created["user_id"]
        magic_link_url = created["magic_link_url"]
        assert "/v1/invite/accept?token=" in magic_link_url
        token = parse_qs(urlsplit(magic_link_url).query)["token"][0]

        listed = client.get("/v1/internal/tenants", headers=internal_headers)
        assert listed.status_code == 200
        assert listed.json()[0]["tenant_id"] == tenant_id
        assert listed.json()[0]["admin_email"] == "admin@acme.example"
        assert listed.json()[0]["last_login_at"] is None

        detail = client.get(
            f"/v1/internal/tenants/{tenant_id}", headers=internal_headers
        )
        assert detail.status_code == 200
        detail_payload = detail.json()
        assert detail_payload["tenant_id"] == tenant_id
        assert detail_payload["federation_type"] == "oidc"
        assert len(detail_payload["users"]) == 1
        assert detail_payload["users"][0]["id"] == user_id
        assert detail_payload["users"][0]["email"] == "admin@acme.example"
        assert detail_payload["users"][0]["role"] == "admin"
        assert detail_payload["users"][0]["invite_consumed_at"] is None

        with SessionLocal() as db:
            logs = list(
                db.execute(
                    select(MagicLinkLog).where(MagicLinkLog.user_id == user_id)
                ).scalars()
            )
            assert len(logs) == 1
            assert token in logs[0].magic_link_url

        accept = client.get(
            "/v1/invite/accept",
            params={"token": token},
            follow_redirects=False,
        )
        assert accept.status_code == 307
        location = accept.headers["location"]
        state = parse_qs(urlsplit(location).query)["state"][0]

        invited_headers = _auth_headers("cognito-user-subject-1", "admin@acme.example")
        callback = client.get(
            "/auth/callback",
            params={"state": state},
            headers=invited_headers,
        )
        assert callback.status_code == 200
        callback_payload = callback.json()
        assert callback_payload["invite_applied"] is True
        assert callback_payload["tenant_id"] == tenant_id
        assert callback_payload["user_id"] == user_id

        me = client.get("/v1/auth/me", headers=invited_headers)
        assert me.status_code == 200, me.text
        me_payload = me.json()
        assert me_payload["actor"] == "cognito-user-subject-1"
        assert me_payload["role"] == "admin"
        assert me_payload["tenant_id"] == tenant_id

        with SessionLocal() as db:
            user = db.get(User, user_id)
            assert user is not None
            assert user.invite_consumed_at is not None
            assert user.last_login_at is not None
            identity = db.execute(
                select(UserIdentity).where(UserIdentity.user_id == user_id)
            ).scalar_one_or_none()
            assert identity is not None
            assert identity.actor == "cognito-user-subject-1"
            assert identity.role == "admin"
            assert identity.tenant_id == tenant_id


def test_invite_accept_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_db()
    _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "ops@sparkpilot.cloud")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Expired Tenant",
                "admin_email": "expired@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        token = parse_qs(urlsplit(create.json()["magic_link_url"]).query)["token"][0]
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        with SessionLocal() as db:
            row = db.execute(
                select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash)
            ).scalar_one()
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            db.commit()

        expired = client.get("/v1/invite/accept", params={"token": token})
        assert expired.status_code == 410
        assert "expired" in expired.json()["detail"].lower()


def test_invite_accept_rejects_consumed_and_wrong_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "ops@sparkpilot.cloud")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Consumed Tenant",
                "admin_email": "consumed@tenant.example",
                "federation_type": "saml",
            },
            headers=internal_headers,
        )
        token = parse_qs(urlsplit(create.json()["magic_link_url"]).query)["token"][0]

        first = client.get(
            "/v1/invite/accept",
            params={"token": token},
            follow_redirects=False,
        )
        assert first.status_code == 307

        consumed = client.get("/v1/invite/accept", params={"token": token})
        assert consumed.status_code == 410
        assert "consumed" in consumed.json()["detail"].lower()

        wrong = client.get(
            "/v1/invite/accept", params={"token": "definitely-not-valid"}
        )
        assert wrong.status_code == 404
        assert "not found" in wrong.json()["detail"].lower()


def test_regenerate_invite_after_consumption_invalidates_old_token_and_issues_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "ops@sparkpilot.cloud")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Regen Tenant",
                "admin_email": "regen@tenant.example",
                "federation_type": "cognito_password",
            },
            headers=internal_headers,
        )
        tenant_id = create.json()["tenant_id"]
        user_id = create.json()["user_id"]
        old_token = parse_qs(urlsplit(create.json()["magic_link_url"]).query)["token"][
            0
        ]

        consumed = client.get(
            "/v1/invite/accept",
            params={"token": old_token},
            follow_redirects=False,
        )
        assert consumed.status_code == 307

        regenerate = client.post(
            f"/v1/internal/tenants/{tenant_id}/users/{user_id}/regenerate-invite",
            headers=internal_headers,
        )
        assert regenerate.status_code == 200, regenerate.text
        new_token = parse_qs(urlsplit(regenerate.json()["magic_link_url"]).query)[
            "token"
        ][0]
        assert new_token != old_token

        old_again = client.get("/v1/invite/accept", params={"token": old_token})
        assert old_again.status_code == 410

        new_accept = client.get(
            "/v1/invite/accept",
            params={"token": new_token},
            follow_redirects=False,
        )
        assert new_accept.status_code == 307


def test_bootstrap_flow_returns_410_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    monkeypatch.setenv("SPARKPILOT_BOOTSTRAP_FLOW", "disabled")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()

    with _BaseTestClient(app) as client:
        token = issue_test_token("bootstrap-candidate")
        response = client.post(
            "/v1/bootstrap/user-identities",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Bootstrap-Secret": "sparkpilot-bootstrap-secret-for-tests",
            },
        )
        assert response.status_code == 410
        assert "disabled" in response.json()["detail"].lower()


def test_bootstrap_flow_defaults_by_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SPARKPILOT_BOOTSTRAP_FLOW", raising=False)
    monkeypatch.setenv("SPARKPILOT_ENVIRONMENT", "production")
    get_settings.cache_clear()
    assert get_settings().bootstrap_flow_enabled is False

    monkeypatch.delenv("SPARKPILOT_BOOTSTRAP_FLOW", raising=False)
    monkeypatch.setenv("SPARKPILOT_ENVIRONMENT", "test")
    get_settings.cache_clear()
    assert get_settings().bootstrap_flow_enabled is True
