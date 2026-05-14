import pytest

from sparkpilot.config import get_settings, validate_runtime_settings


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def _set_valid_non_dev_runtime_env(monkeypatch, *, environment: str = "production") -> None:
    monkeypatch.setenv("SPARKPILOT_ENVIRONMENT", environment)
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv(
        "SPARKPILOT_DATABASE_URL",
        "postgresql+psycopg://sparkpilot:sparkpilot@db.example.com:5432/sparkpilot",
    )
    monkeypatch.setenv("SPARKPILOT_CORS_ORIGINS", "https://app.sparkpilot.cloud")
    monkeypatch.setenv("SPARKPILOT_BOOTSTRAP_SECRET", "0123456789abcdef")
    monkeypatch.setenv("SPARKPILOT_CONTACT_SUBMIT_TOKEN", "c" * 32)
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::123456789012:role/SparkPilotExecRole",
    )
    monkeypatch.setenv("SPARKPILOT_CUSTOMER_OIDC_ISSUER", "https://customer.example.invalid")
    monkeypatch.setenv("SPARKPILOT_CUSTOMER_OIDC_AUDIENCE", "customer-audience")
    monkeypatch.setenv("SPARKPILOT_CUSTOMER_OIDC_JWKS_URI", "file:///tmp/customer-jwks.json")
    monkeypatch.setenv("SPARKPILOT_INTERNAL_OIDC_ISSUER", "https://internal.example.invalid")
    monkeypatch.setenv("SPARKPILOT_INTERNAL_OIDC_AUDIENCE", "internal-audience")
    monkeypatch.setenv("SPARKPILOT_INTERNAL_OIDC_JWKS_URI", "file:///tmp/internal-jwks.json")


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


def test_dry_run_is_blocked_outside_dev_like_environments(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ENVIRONMENT", "production")
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "true")
    monkeypatch.setenv(
        "SPARKPILOT_DATABASE_URL",
        "postgresql+psycopg://sparkpilot:sparkpilot@localhost:5432/sparkpilot",
    )
    _clear_settings_cache()
    with pytest.raises(ValueError, match="SPARKPILOT_DRY_RUN_MODE=true is not allowed in production"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_sqlite_is_blocked_outside_dev_like_environments(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ENVIRONMENT", "staging")
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv("SPARKPILOT_DATABASE_URL", "sqlite:///./sparkpilot.db")
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::123456789012:role/SparkPilotExecRole",
    )
    _clear_settings_cache()
    with pytest.raises(ValueError, match="SQLite is only supported in development/test"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_auth_mode_must_be_oidc(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_AUTH_MODE", "legacy")
    _clear_settings_cache()
    with pytest.raises(ValueError, match="AUTH_MODE must be 'oidc'|Input should be 'oidc'"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_oidc_issuer_is_required(monkeypatch) -> None:
    monkeypatch.delenv("SPARKPILOT_CUSTOMER_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("SPARKPILOT_OIDC_ISSUER", raising=False)
    _clear_settings_cache()
    with pytest.raises(ValueError, match="SPARKPILOT_CUSTOMER_OIDC_ISSUER is required"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_oidc_jwks_uri_must_be_valid(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_CUSTOMER_OIDC_JWKS_URI", "not-a-valid-uri")
    monkeypatch.setenv("SPARKPILOT_OIDC_JWKS_URI", "not-a-valid-uri")
    _clear_settings_cache()
    with pytest.raises(
        ValueError, match="SPARKPILOT_CUSTOMER_OIDC_JWKS_URI must be a valid"
    ):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_legacy_customer_oidc_aliases_are_accepted(monkeypatch) -> None:
    monkeypatch.delenv("SPARKPILOT_CUSTOMER_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("SPARKPILOT_CUSTOMER_OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("SPARKPILOT_CUSTOMER_OIDC_JWKS_URI", raising=False)
    monkeypatch.setenv("SPARKPILOT_OIDC_ISSUER", "https://legacy-customer-issuer")
    monkeypatch.setenv("SPARKPILOT_OIDC_AUDIENCE", "legacy-customer-audience")
    monkeypatch.setenv("SPARKPILOT_OIDC_JWKS_URI", "file:///tmp/legacy-jwks.json")
    _clear_settings_cache()
    settings = get_settings()
    assert settings.customer_oidc_issuer_effective == "https://legacy-customer-issuer"
    assert settings.customer_oidc_audience_effective == "legacy-customer-audience"
    assert settings.customer_oidc_jwks_uri_effective == "file:///tmp/legacy-jwks.json"
    assert settings.legacy_customer_oidc_aliases_in_use == [
        "SPARKPILOT_OIDC_ISSUER",
        "SPARKPILOT_OIDC_AUDIENCE",
        "SPARKPILOT_OIDC_JWKS_URI",
    ]
    _clear_settings_cache()


def test_bootstrap_secret_must_be_configured(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_BOOTSTRAP_SECRET", "short")
    _clear_settings_cache()
    with pytest.raises(ValueError, match="BOOTSTRAP_SECRET must be set and at least"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_contact_submit_token_is_required_outside_dev(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ENVIRONMENT", "staging")
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv(
        "SPARKPILOT_DATABASE_URL",
        "postgresql+psycopg://sparkpilot:sparkpilot@db.example.com:5432/sparkpilot",
    )
    monkeypatch.setenv("SPARKPILOT_CORS_ORIGINS", "https://app.sparkpilot.cloud")
    monkeypatch.setenv("SPARKPILOT_BOOTSTRAP_SECRET", "0123456789abcdef")
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::123456789012:role/SparkPilotExecRole",
    )
    monkeypatch.delenv("SPARKPILOT_CONTACT_SUBMIT_TOKEN", raising=False)
    _clear_settings_cache()
    with pytest.raises(ValueError, match="SPARKPILOT_CONTACT_SUBMIT_TOKEN must be set"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_internal_admins_are_required_outside_dev(monkeypatch) -> None:
    _set_valid_non_dev_runtime_env(monkeypatch)
    monkeypatch.delenv("SPARKPILOT_INTERNAL_ADMINS", raising=False)
    monkeypatch.delenv("INTERNAL_ADMINS", raising=False)
    _clear_settings_cache()
    with pytest.raises(ValueError, match="SPARKPILOT_INTERNAL_ADMINS must include"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_internal_admins_reject_malformed_emails_outside_dev(monkeypatch) -> None:
    _set_valid_non_dev_runtime_env(monkeypatch)
    monkeypatch.setenv("SPARKPILOT_INTERNAL_ADMINS", "jmcqueary@sparkpilot.cloud,bad-email")
    monkeypatch.delenv("INTERNAL_ADMINS", raising=False)
    _clear_settings_cache()
    with pytest.raises(ValueError, match="invalid email addresses: bad-email"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_contact_submit_token_requires_minimum_length(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_CONTACT_SUBMIT_TOKEN", "too-short")
    _clear_settings_cache()
    with pytest.raises(ValueError, match="SPARKPILOT_CONTACT_SUBMIT_TOKEN must be at least"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_cors_rejects_wildcard_origin(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_CORS_ORIGINS", "*")
    _clear_settings_cache()
    with pytest.raises(ValueError, match="wildcard origins"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_pricing_cache_seconds_must_be_positive(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_PRICING_CACHE_SECONDS", "0")
    _clear_settings_cache()
    with pytest.raises(ValueError, match="SPARKPILOT_PRICING_CACHE_SECONDS must be greater than 0"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_cost_center_policy_json_must_be_valid(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_COST_CENTER_POLICY_JSON", "{invalid-json")
    _clear_settings_cache()
    with pytest.raises(ValueError, match="SPARKPILOT_COST_CENTER_POLICY_JSON is invalid"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_cost_center_policy_json_rejects_unsupported_keys(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_COST_CENTER_POLICY_JSON", '{"by_cluster":{"a":"b"}}')
    _clear_settings_cache()
    with pytest.raises(ValueError, match="unsupported keys"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_assume_role_external_id_setting(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_ASSUME_ROLE_EXTERNAL_ID", "tenant-external-id-123")
    _clear_settings_cache()
    assert get_settings().assume_role_external_id == "tenant-external-id-123"
    _clear_settings_cache()
