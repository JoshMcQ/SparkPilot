import pytest

from sparkpilot.config import get_settings, validate_runtime_settings


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_live_mode_requires_execution_role(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.delenv("SPARKPILOT_EMR_EXECUTION_ROLE_ARN", raising=False)
    _clear_settings_cache()
    with pytest.raises(ValueError, match="SPARKPILOT_EMR_EXECUTION_ROLE_ARN is required"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_live_mode_rejects_placeholder_execution_role(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::111111111111:role/SparkPilotEmrExecutionRole",
    )
    _clear_settings_cache()
    with pytest.raises(ValueError, match="placeholder execution role ARN"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_live_mode_rejects_malformed_execution_role(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv("SPARKPILOT_EMR_EXECUTION_ROLE_ARN", "not-an-arn")
    _clear_settings_cache()
    with pytest.raises(ValueError, match="must be a valid IAM role ARN"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_dry_run_allows_missing_execution_role(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "true")
    monkeypatch.delenv("SPARKPILOT_EMR_EXECUTION_ROLE_ARN", raising=False)
    _clear_settings_cache()
    validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_auth_mode_must_be_oidc(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_AUTH_MODE", "legacy")
    _clear_settings_cache()
    with pytest.raises(ValueError, match="AUTH_MODE must be 'oidc'|Input should be 'oidc'"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_oidc_issuer_is_required(monkeypatch) -> None:
    monkeypatch.delenv("SPARKPILOT_OIDC_ISSUER", raising=False)
    _clear_settings_cache()
    with pytest.raises(ValueError, match="OIDC_ISSUER is required"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_oidc_jwks_uri_must_be_valid(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_OIDC_JWKS_URI", "not-a-valid-uri")
    _clear_settings_cache()
    with pytest.raises(ValueError, match="OIDC_JWKS_URI must be a valid"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_bootstrap_secret_must_be_configured(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_BOOTSTRAP_SECRET", "short")
    _clear_settings_cache()
    with pytest.raises(ValueError, match="BOOTSTRAP_SECRET must be set and at least"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_cors_rejects_wildcard_origin(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_CORS_ORIGINS", "*")
    _clear_settings_cache()
    with pytest.raises(ValueError, match="wildcard origins"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()
