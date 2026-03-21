from __future__ import annotations

import base64

from tests import conftest
import jwt

from sparkpilot import mock_oidc


def _basic_auth_header(client_id: str, client_secret: str) -> dict[str, str]:
    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}


def _token_claims(access_token: str) -> dict[str, object]:
    return jwt.decode(
        access_token,
        options={"verify_signature": False, "verify_aud": False, "verify_iss": False},
    )


def test_mock_oidc_defaults_subject_to_service_client() -> None:
    with conftest._BaseTestClient(mock_oidc.app) as client:
        response = client.post(
            "/oauth/token",
            data={"grant_type": "client_credentials", "audience": mock_oidc.MOCK_AUDIENCE},
            headers=_basic_auth_header("sparkpilot-cli", "sparkpilot-cli-secret"),
        )
    assert response.status_code == 200
    body = response.json()
    claims = _token_claims(body["access_token"])
    assert claims["sub"] == "service:sparkpilot-cli"


def test_mock_oidc_allows_subject_override_by_default() -> None:
    with conftest._BaseTestClient(mock_oidc.app) as client:
        response = client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "audience": mock_oidc.MOCK_AUDIENCE,
                "subject": "user:demo-admin",
            },
            headers=_basic_auth_header("sparkpilot-cli", "sparkpilot-cli-secret"),
        )
    assert response.status_code == 200
    body = response.json()
    claims = _token_claims(body["access_token"])
    assert claims["sub"] == "user:demo-admin"


def test_mock_oidc_rejects_subject_override_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(mock_oidc, "MOCK_ALLOW_SUBJECT_OVERRIDE", False)
    with conftest._BaseTestClient(mock_oidc.app) as client:
        response = client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "audience": mock_oidc.MOCK_AUDIENCE,
                "subject": "user:forbidden",
            },
            headers=_basic_auth_header("sparkpilot-cli", "sparkpilot-cli-secret"),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "subject override is disabled for this mock OIDC deployment."
