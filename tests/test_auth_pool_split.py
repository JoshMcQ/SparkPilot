from __future__ import annotations

import pytest

from sparkpilot.api import _oidc_verifier, _oidc_verifiers, app
from sparkpilot.config import get_settings
from tests.conftest import (
    TEST_CUSTOMER_OIDC_AUDIENCE,
    TEST_CUSTOMER_OIDC_ISSUER,
    TEST_INTERNAL_OIDC_AUDIENCE,
    TEST_INTERNAL_OIDC_ISSUER,
    _jwks_uri,
    _BaseTestClient,
    issue_test_token,
)


def _apply_pool_split_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKPILOT_CUSTOMER_OIDC_ISSUER", TEST_CUSTOMER_OIDC_ISSUER)
    monkeypatch.setenv(
        "SPARKPILOT_CUSTOMER_OIDC_AUDIENCE", TEST_CUSTOMER_OIDC_AUDIENCE
    )
    monkeypatch.setenv("SPARKPILOT_CUSTOMER_OIDC_JWKS_URI", _jwks_uri())
    monkeypatch.setenv("SPARKPILOT_INTERNAL_OIDC_ISSUER", TEST_INTERNAL_OIDC_ISSUER)
    monkeypatch.setenv(
        "SPARKPILOT_INTERNAL_OIDC_AUDIENCE", TEST_INTERNAL_OIDC_AUDIENCE
    )
    monkeypatch.setenv("SPARKPILOT_INTERNAL_OIDC_JWKS_URI", _jwks_uri())
    monkeypatch.setenv("SPARKPILOT_INTERNAL_ADMINS", "admin@example.invalid")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()
    _oidc_verifiers.cache_clear()


def _auth_headers(
    subject: str,
    *,
    pool: str,
    email: str,
) -> dict[str, str]:
    if pool == "internal":
        issuer = TEST_INTERNAL_OIDC_ISSUER
        audience = TEST_INTERNAL_OIDC_AUDIENCE
    else:
        issuer = TEST_CUSTOMER_OIDC_ISSUER
        audience = TEST_CUSTOMER_OIDC_AUDIENCE
    token = issue_test_token(
        subject,
        issuer=issuer,
        audience=audience,
        extra_claims={"email": email},
    )
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_customer_identity(client: _BaseTestClient, *, subject: str) -> None:
    headers = _auth_headers(
        subject,
        pool="customer",
        email="admin@example.invalid",
    )
    headers["X-Bootstrap-Secret"] = "sparkpilot-bootstrap-secret-for-tests"
    response = client.post(
        "/v1/user-identities",
        json={"actor": subject, "role": "admin", "active": True},
        headers=headers,
    )
    assert response.status_code in {200, 201, 409}, response.text


def test_auth_me_returns_email_and_internal_flag_for_customer_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _apply_pool_split_env(monkeypatch)
    headers = _auth_headers(
        "test-user",
        pool="customer",
        email="admin@example.invalid",
    )
    with _BaseTestClient(app) as client:
        _bootstrap_customer_identity(client, subject="test-user")
        response = client.get("/v1/auth/me", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["email"] == "admin@example.invalid"
    assert payload["is_internal_admin"] is False


def test_auth_me_returns_internal_admin_for_internal_pool_without_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _apply_pool_split_env(monkeypatch)
    headers = _auth_headers(
        "internal-admin-subject",
        pool="internal",
        email="admin@example.invalid",
    )
    with _BaseTestClient(app) as client:
        response = client.get("/v1/auth/me", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["actor"] == "internal-admin-subject"
    assert payload["email"] == "admin@example.invalid"
    assert payload["is_internal_admin"] is True
    assert payload["tenant_id"] is None
    assert payload["scoped_environment_ids"] == []


def test_internal_endpoint_rejects_customer_pool_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _apply_pool_split_env(monkeypatch)
    headers = _auth_headers(
        "test-user",
        pool="customer",
        email="admin@example.invalid",
    )
    with _BaseTestClient(app) as client:
        response = client.get("/v1/internal/tenants", headers=headers)
    assert response.status_code == 403


def test_customer_endpoint_rejects_internal_pool_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _apply_pool_split_env(monkeypatch)
    headers = _auth_headers(
        "internal-admin-subject",
        pool="internal",
        email="admin@example.invalid",
    )
    with _BaseTestClient(app) as client:
        response = client.get("/v1/environments", headers=headers)
    assert response.status_code == 403
