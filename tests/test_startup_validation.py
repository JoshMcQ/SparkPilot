from __future__ import annotations

import httpx
import pytest

from sparkpilot.api import app
from sparkpilot.config import get_settings
from tests.conftest import _BaseTestClient


def _set_valid_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ENV", "production")
    monkeypatch.setenv("SPARKPILOT_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "SPARKPILOT_DATABASE_URL",
        "postgresql+psycopg://sparkpilot:sparkpilot@db.example.com:5432/sparkpilot",
    )
    monkeypatch.setenv("SPARKPILOT_AUTH_MODE", "oidc")
    monkeypatch.setenv(
        "SPARKPILOT_CUSTOMER_OIDC_ISSUER",
        "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example",
    )
    monkeypatch.setenv("SPARKPILOT_CUSTOMER_OIDC_AUDIENCE", "sparkpilot-api")
    monkeypatch.setenv(
        "SPARKPILOT_CUSTOMER_OIDC_JWKS_URI",
        "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example/.well-known/jwks.json",
    )
    monkeypatch.setenv(
        "SPARKPILOT_INTERNAL_OIDC_ISSUER",
        "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_internal",
    )
    monkeypatch.setenv("SPARKPILOT_INTERNAL_OIDC_AUDIENCE", "sparkpilot-internal-api")
    monkeypatch.setenv(
        "SPARKPILOT_INTERNAL_OIDC_JWKS_URI",
        "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_internal/.well-known/jwks.json",
    )
    monkeypatch.setenv("SPARKPILOT_BOOTSTRAP_SECRET", "0123456789abcdef")
    monkeypatch.setenv("SPARKPILOT_RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv(
        "SPARKPILOT_INVITE_EMAIL_FROM",
        "SparkPilot <invites@example.invalid>",
    )
    monkeypatch.setenv(
        "SPARKPILOT_COGNITO_HOSTED_UI_URL",
        "https://auth.example.invalid/oauth2/authorize",
    )
    monkeypatch.setenv("SPARKPILOT_CORS_ORIGINS", "https://app.sparkpilot.cloud")
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv("SPARKPILOT_ENABLE_FULL_BYOC_MODE", "false")
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::123456789012:role/SparkPilotExecRole",
    )
    get_settings.cache_clear()


def _expect_startup_failure(match: str) -> None:
    with pytest.raises(RuntimeError, match=match):
        with _BaseTestClient(app):
            pass


@pytest.mark.parametrize(
    ("env_var", "expected_check"),
    [
        ("SPARKPILOT_CUSTOMER_OIDC_ISSUER", "customer_pool_oidc_issuer_present"),
        ("SPARKPILOT_CUSTOMER_OIDC_AUDIENCE", "customer_pool_oidc_audience_present"),
        ("SPARKPILOT_CUSTOMER_OIDC_JWKS_URI", "customer_pool_oidc_jwks_uri_present"),
        ("SPARKPILOT_INTERNAL_OIDC_ISSUER", "internal_pool_oidc_issuer_present"),
        ("SPARKPILOT_INTERNAL_OIDC_AUDIENCE", "internal_pool_oidc_audience_present"),
        ("SPARKPILOT_INTERNAL_OIDC_JWKS_URI", "internal_pool_oidc_jwks_uri_present"),
    ],
)
def test_production_startup_fails_when_required_oidc_env_missing(
    monkeypatch: pytest.MonkeyPatch,
    env_var: str,
    expected_check: str,
) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setattr(
        "sparkpilot.api._fetch_jwks_json", lambda *_args, **_kwargs: {"keys": []}
    )
    monkeypatch.delenv(env_var, raising=False)
    legacy_alias_by_customer_var = {
        "SPARKPILOT_CUSTOMER_OIDC_ISSUER": "SPARKPILOT_OIDC_ISSUER",
        "SPARKPILOT_CUSTOMER_OIDC_AUDIENCE": "SPARKPILOT_OIDC_AUDIENCE",
        "SPARKPILOT_CUSTOMER_OIDC_JWKS_URI": "SPARKPILOT_OIDC_JWKS_URI",
    }
    legacy_alias = legacy_alias_by_customer_var.get(env_var)
    if legacy_alias:
        monkeypatch.delenv(legacy_alias, raising=False)
    get_settings.cache_clear()

    _expect_startup_failure(expected_check)


@pytest.mark.parametrize(
    ("env_var", "legacy_alias", "expected_check"),
    [
        ("SPARKPILOT_RESEND_API_KEY", "RESEND_API_KEY", "resend_api_key_present"),
        (
            "SPARKPILOT_INVITE_EMAIL_FROM",
            "INVITE_EMAIL_FROM",
            "invite_email_from_present",
        ),
        (
            "SPARKPILOT_COGNITO_HOSTED_UI_URL",
            "COGNITO_HOSTED_UI_URL",
            "cognito_hosted_ui_url_present",
        ),
    ],
)
def test_production_startup_fails_when_invite_email_env_missing(
    monkeypatch: pytest.MonkeyPatch,
    env_var: str,
    legacy_alias: str,
    expected_check: str,
) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setattr(
        "sparkpilot.api._fetch_jwks_json", lambda *_args, **_kwargs: {"keys": []}
    )
    monkeypatch.delenv(env_var, raising=False)
    monkeypatch.delenv(legacy_alias, raising=False)
    get_settings.cache_clear()

    _expect_startup_failure(expected_check)


def test_production_startup_fails_when_jwks_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_env(monkeypatch)

    def _raise_unreachable(*_args, **_kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("sparkpilot.api._fetch_jwks_json", _raise_unreachable)

    _expect_startup_failure("customer_pool_oidc_jwks_reachable_json")


def test_production_startup_fails_when_jwks_not_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_env(monkeypatch)

    def _raise_non_json(*_args, **_kwargs):
        raise ValueError("invalid json")

    monkeypatch.setattr("sparkpilot.api._fetch_jwks_json", _raise_non_json)

    _expect_startup_failure("customer_pool_oidc_jwks_reachable_json")


def test_production_startup_fails_when_auth_mode_not_oidc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setattr(
        "sparkpilot.api._fetch_jwks_json", lambda *_args, **_kwargs: {"keys": []}
    )
    monkeypatch.setenv("SPARKPILOT_AUTH_MODE", "legacy")
    get_settings.cache_clear()

    _expect_startup_failure("auth_mode_oidc")


def test_production_startup_fails_when_bootstrap_secret_too_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setattr(
        "sparkpilot.api._fetch_jwks_json", lambda *_args, **_kwargs: {"keys": []}
    )
    monkeypatch.setenv("SPARKPILOT_BOOTSTRAP_SECRET", "short")
    get_settings.cache_clear()

    _expect_startup_failure("bootstrap_secret_min_length")


@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3000"])
def test_production_startup_fails_when_cors_contains_localhost_or_loopback(
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setattr(
        "sparkpilot.api._fetch_jwks_json", lambda *_args, **_kwargs: {"keys": []}
    )
    monkeypatch.setenv(
        "SPARKPILOT_CORS_ORIGINS", f"https://app.sparkpilot.cloud,{origin}"
    )
    get_settings.cache_clear()

    _expect_startup_failure("cors_no_localhost")


def test_production_startup_fails_when_dry_run_mode_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setattr(
        "sparkpilot.api._fetch_jwks_json", lambda *_args, **_kwargs: {"keys": []}
    )
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "true")
    get_settings.cache_clear()

    _expect_startup_failure("dry_run_disabled")


def test_production_startup_fails_when_full_byoc_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setattr(
        "sparkpilot.api._fetch_jwks_json", lambda *_args, **_kwargs: {"keys": []}
    )
    monkeypatch.setenv("SPARKPILOT_ENABLE_FULL_BYOC_MODE", "true")
    get_settings.cache_clear()

    _expect_startup_failure("full_byoc_disabled")


def test_production_startup_logs_pass_fail_for_each_check(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setattr(
        "sparkpilot.api._fetch_jwks_json", lambda *_args, **_kwargs: {"keys": []}
    )
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "true")
    get_settings.cache_clear()

    caplog.set_level("INFO")
    _expect_startup_failure("dry_run_disabled")

    messages = [
        record.getMessage()
        for record in caplog.records
        if "Production startup check [" in record.getMessage()
    ]
    assert any("[PASS]" in message for message in messages)
    assert any("[FAIL]" in message for message in messages)
    expected_checks = {
        "auth_mode_oidc",
        "customer_pool_oidc_issuer_present",
        "customer_pool_oidc_audience_present",
        "customer_pool_oidc_jwks_uri_present",
        "customer_pool_oidc_jwks_reachable_json",
        "internal_pool_oidc_issuer_present",
        "internal_pool_oidc_audience_present",
        "internal_pool_oidc_jwks_uri_present",
        "internal_pool_oidc_jwks_reachable_json",
        "resend_api_key_present",
        "invite_email_from_present",
        "bootstrap_secret_min_length",
        "cors_no_localhost",
        "dry_run_disabled",
        "full_byoc_disabled",
    }
    for check_name in expected_checks:
        assert any(check_name in message for message in messages)
