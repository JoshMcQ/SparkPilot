from __future__ import annotations

import atexit
from collections.abc import Callable, Generator
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric import rsa
import fastapi.testclient as fastapi_testclient
import jwt
import pytest
import starlette.testclient as starlette_testclient

os.environ.setdefault("SPARKPILOT_ENVIRONMENT", "test")
os.environ.setdefault("SPARKPILOT_DATABASE_URL", "sqlite:///./sparkpilot_test.db")
os.environ.setdefault("SPARKPILOT_DRY_RUN_MODE", "true")
os.environ.setdefault("SPARKPILOT_ENABLE_FULL_BYOC_MODE", "true")
os.environ.setdefault("SPARKPILOT_AUTH_MODE", "oidc")
os.environ.setdefault("SPARKPILOT_OIDC_ISSUER", "https://sparkpilot.test-issuer")
os.environ.setdefault("SPARKPILOT_OIDC_AUDIENCE", "sparkpilot-api")
os.environ.setdefault(
    "SPARKPILOT_BOOTSTRAP_SECRET", "sparkpilot-bootstrap-secret-for-tests"
)
os.environ.setdefault("SPARKPILOT_BOOTSTRAP_FLOW", "enabled")

from sparkpilot.api import _oidc_verifier
from sparkpilot.config import get_settings


TEST_OIDC_ISSUER = "https://sparkpilot.test-issuer"
TEST_OIDC_AUDIENCE = "sparkpilot-api"
TEST_BOOTSTRAP_SECRET = "sparkpilot-bootstrap-secret-for-tests"
TEST_JWT_KID = "sparkpilot-test-kid"
DEFAULT_TEST_SUBJECT = "test-user"

_JWKS_PATH = Path(__file__).with_name(f".oidc-test-jwks-{os.getpid()}.json")
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_PRIVATE_KEY.public_key()))
_PUBLIC_JWK["kid"] = TEST_JWT_KID
_JWKS_PATH.write_text(json.dumps({"keys": [_PUBLIC_JWK]}), encoding="utf-8")


def _cleanup_jwks_file() -> None:
    try:
        _JWKS_PATH.unlink(missing_ok=True)
    except OSError:
        pass


atexit.register(_cleanup_jwks_file)


def _jwks_uri() -> str:
    return _JWKS_PATH.resolve().as_uri()


def issue_test_token(
    subject: str,
    *,
    issuer: str = TEST_OIDC_ISSUER,
    audience: str = TEST_OIDC_AUDIENCE,
    expires_in_seconds: int = 3600,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        _PRIVATE_KEY,
        algorithm="RS256",
        headers={"kid": TEST_JWT_KID, "typ": "JWT"},
    )


_BaseTestClient = starlette_testclient.TestClient


class PatchedTestClient(_BaseTestClient):
    def _ensure_bootstrap_identity(self) -> None:
        if getattr(self, "_sparkpilot_bootstrap_done", False):
            return
        bootstrap_token = issue_test_token(DEFAULT_TEST_SUBJECT)
        response = super().request(
            "POST",
            "/v1/user-identities",
            json={"actor": DEFAULT_TEST_SUBJECT, "role": "admin", "active": True},
            headers={
                "Authorization": f"Bearer {bootstrap_token}",
                "X-Bootstrap-Secret": os.getenv(
                    "SPARKPILOT_BOOTSTRAP_SECRET", TEST_BOOTSTRAP_SECRET
                ),
            },
        )
        if response.status_code not in {200, 201, 409, 403}:
            raise RuntimeError(
                f"Failed to create bootstrap test identity: {response.status_code} {response.text}"
            )
        if DEFAULT_TEST_SUBJECT != "bootstrap-admin":
            response = super().request(
                "POST",
                "/v1/user-identities",
                json={"actor": "bootstrap-admin", "role": "admin", "active": True},
                headers={
                    "Authorization": f"Bearer {bootstrap_token}",
                },
            )
            if response.status_code not in {200, 201, 409, 403}:
                raise RuntimeError(
                    f"Failed to create bootstrap-admin identity: {response.status_code} {response.text}"
                )
        self._sparkpilot_bootstrap_done = True

    @staticmethod
    def _is_user_identity_path(url: str) -> bool:
        return urlsplit(url).path == "/v1/user-identities"

    def request(self, method: str, url: str, **kwargs):  # type: ignore[override]
        headers = dict(kwargs.pop("headers", {}) or {})
        skip_bootstrap = str(headers.pop("X-Skip-Test-Bootstrap", "")).lower() in {
            "1",
            "true",
            "yes",
        }
        explicit_auth = "Authorization" in headers
        if not explicit_auth:
            headers["Authorization"] = (
                f"Bearer {issue_test_token(DEFAULT_TEST_SUBJECT)}"
            )
        else:
            auth_value = str(headers.get("Authorization", "")).strip()
            scheme, _, token = auth_value.partition(" ")
            token = token.strip()
            if (
                scheme.lower() == "bearer"
                and token
                and token != "invalid-token"
                and "." not in token
            ):
                headers["Authorization"] = (
                    f"Bearer {issue_test_token(DEFAULT_TEST_SUBJECT)}"
                )
        kwargs["headers"] = headers

        if not skip_bootstrap and not self._is_user_identity_path(url):
            self._ensure_bootstrap_identity()
        return super().request(method, url, **kwargs)


starlette_testclient.TestClient = PatchedTestClient
fastapi_testclient.TestClient = PatchedTestClient


@pytest.fixture(autouse=True)
def clear_settings_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    monkeypatch.setenv("SPARKPILOT_ENVIRONMENT", "test")
    monkeypatch.setenv("SPARKPILOT_AUTH_MODE", "oidc")
    monkeypatch.setenv("SPARKPILOT_OIDC_ISSUER", TEST_OIDC_ISSUER)
    monkeypatch.setenv("SPARKPILOT_OIDC_AUDIENCE", TEST_OIDC_AUDIENCE)
    monkeypatch.setenv("SPARKPILOT_OIDC_JWKS_URI", _jwks_uri())
    monkeypatch.setenv("SPARKPILOT_BOOTSTRAP_SECRET", TEST_BOOTSTRAP_SECRET)
    monkeypatch.setenv("SPARKPILOT_BOOTSTRAP_FLOW", "enabled")
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "true")
    monkeypatch.setenv("SPARKPILOT_ENABLE_FULL_BYOC_MODE", "true")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()
    yield
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()


@pytest.fixture
def oidc_token() -> Callable[[str], str]:
    return issue_test_token
