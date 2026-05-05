from __future__ import annotations

import httpx
import pytest

from sparkpilot.config import get_settings, validate_runtime_settings
from sparkpilot.invite_email import (
    RESEND_EMAILS_URL,
    InviteEmailConfigurationError,
    InviteEmailDeliveryError,
    send_invite_email,
)


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_send_invite_email_posts_to_resend_with_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARKPILOT_RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv(
        "SPARKPILOT_INVITE_EMAIL_FROM",
        "SparkPilot <invites@example.invalid>",
    )
    _clear_settings_cache()
    captured: dict[str, object] = {}

    def _fake_post(
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        captured.update(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return httpx.Response(200, json={"id": "email_123"})

    monkeypatch.setattr("sparkpilot.invite_email.httpx.post", _fake_post)

    delivery = send_invite_email(
        recipient_email="admin@example.invalid",
        tenant_name="Acme Corp",
        invite_url="https://app.example.invalid/v1/invite/accept?token=secret-token",
        tenant_id="tenant-123",
        user_id="user-123",
        ttl_hours=24,
        idempotency_key="invite:token-row-123",
    )

    assert delivery.provider == "resend"
    assert delivery.recipient_email == "admin@example.invalid"
    assert delivery.status == "sent"
    assert delivery.provider_message_id == "email_123"
    assert delivery.failure_detail is None
    assert captured["url"] == RESEND_EMAILS_URL
    assert captured["timeout"] == 10.0
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer re_test_key"
    assert headers["Idempotency-Key"] == "invite:token-row-123"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["from"] == "SparkPilot <invites@example.invalid>"
    assert payload["to"] == ["admin@example.invalid"]
    assert payload["subject"] == "SparkPilot invite for Acme Corp"
    assert "secret-token" in str(payload["text"])
    assert "secret-token" in str(payload["html"])
    _clear_settings_cache()


def test_send_invite_email_requires_resend_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SPARKPILOT_RESEND_API_KEY", raising=False)
    monkeypatch.setenv(
        "SPARKPILOT_INVITE_EMAIL_FROM",
        "SparkPilot <invites@example.invalid>",
    )
    _clear_settings_cache()

    with pytest.raises(InviteEmailConfigurationError, match="RESEND_API_KEY"):
        send_invite_email(
            recipient_email="admin@example.invalid",
            tenant_name="Acme Corp",
            invite_url="https://app.example.invalid/v1/invite/accept?token=secret-token",
            tenant_id="tenant-123",
            user_id="user-123",
            ttl_hours=24,
            idempotency_key="invite:token-row-123",
        )
    _clear_settings_cache()


def test_send_invite_email_rejects_provider_errors_without_leaking_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARKPILOT_RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv(
        "SPARKPILOT_INVITE_EMAIL_FROM",
        "SparkPilot <invites@example.invalid>",
    )
    _clear_settings_cache()
    monkeypatch.setattr("sparkpilot.invite_email.time.sleep", lambda _seconds: None)

    def _fake_post(*_args, **_kwargs) -> httpx.Response:
        return httpx.Response(500, json={"message": "provider unavailable"})

    monkeypatch.setattr("sparkpilot.invite_email.httpx.post", _fake_post)

    with pytest.raises(InviteEmailDeliveryError) as exc_info:
        send_invite_email(
            recipient_email="admin@example.invalid",
            tenant_name="Acme Corp",
            invite_url="https://app.example.invalid/v1/invite/accept?token=secret-token",
            tenant_id="tenant-123",
            user_id="user-123",
            ttl_hours=24,
            idempotency_key="invite:token-row-123",
        )

    assert "secret-token" not in str(exc_info.value)
    _clear_settings_cache()


def test_send_invite_email_retries_transient_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARKPILOT_RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv(
        "SPARKPILOT_INVITE_EMAIL_FROM",
        "SparkPilot <invites@example.invalid>",
    )
    _clear_settings_cache()
    sleeps: list[float] = []
    idempotency_keys: list[str] = []

    def _fake_post(
        _url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        assert json["to"] == ["admin@example.invalid"]
        assert timeout == 10.0
        idempotency_keys.append(headers["Idempotency-Key"])
        if len(idempotency_keys) == 1:
            return httpx.Response(503, json={"message": "try again"})
        return httpx.Response(200, json={"id": "email_retry"})

    monkeypatch.setattr("sparkpilot.invite_email.httpx.post", _fake_post)
    monkeypatch.setattr(
        "sparkpilot.invite_email.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    delivery = send_invite_email(
        recipient_email="admin@example.invalid",
        tenant_name="Acme Corp",
        invite_url="https://app.example.invalid/v1/invite/accept?token=secret-token",
        tenant_id="tenant-123",
        user_id="user-123",
        ttl_hours=24,
        idempotency_key="invite:token-row-123",
    )

    assert delivery.provider_message_id == "email_retry"
    assert idempotency_keys == ["invite:token-row-123", "invite:token-row-123"]
    assert len(sleeps) == 1
    _clear_settings_cache()


def test_send_invite_email_retries_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARKPILOT_RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv(
        "SPARKPILOT_INVITE_EMAIL_FROM",
        "SparkPilot <invites@example.invalid>",
    )
    _clear_settings_cache()
    attempts = 0

    def _fake_post(*_args, **_kwargs) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary network failure")
        return httpx.Response(200, json={"id": "email_after_retry"})

    monkeypatch.setattr("sparkpilot.invite_email.httpx.post", _fake_post)
    monkeypatch.setattr("sparkpilot.invite_email.time.sleep", lambda _seconds: None)

    delivery = send_invite_email(
        recipient_email="admin@example.invalid",
        tenant_name="Acme Corp",
        invite_url="https://app.example.invalid/v1/invite/accept?token=secret-token",
        tenant_id="tenant-123",
        user_id="user-123",
        ttl_hours=24,
        idempotency_key="invite:token-row-123",
    )

    assert delivery.provider_message_id == "email_after_retry"
    assert attempts == 2
    _clear_settings_cache()


def test_invite_email_requires_hosted_ui_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARKPILOT_RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv(
        "SPARKPILOT_INVITE_EMAIL_FROM",
        "SparkPilot <invites@example.invalid>",
    )
    monkeypatch.delenv("SPARKPILOT_COGNITO_HOSTED_UI_URL", raising=False)
    _clear_settings_cache()

    with pytest.raises(ValueError, match="SPARKPILOT_COGNITO_HOSTED_UI_URL"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_invite_email_from_required_when_resend_key_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARKPILOT_RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("SPARKPILOT_INVITE_EMAIL_FROM", "")
    monkeypatch.setenv(
        "SPARKPILOT_COGNITO_HOSTED_UI_URL",
        "https://auth.example.invalid/oauth2/authorize",
    )
    monkeypatch.setenv("SPARKPILOT_APP_BASE_URL", "https://app.example.invalid")
    _clear_settings_cache()

    with pytest.raises(ValueError, match="SPARKPILOT_INVITE_EMAIL_FROM is required"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


@pytest.mark.parametrize(
    ("env_var", "value", "match"),
    [
        (
            "SPARKPILOT_INVITE_EMAIL_FROM",
            "Alice <alice@example.invalid>oops",
            "SPARKPILOT_INVITE_EMAIL_FROM",
        ),
        (
            "SPARKPILOT_INVITE_EMAIL_REPLY_TO",
            "reply@example.invalid>oops",
            "SPARKPILOT_INVITE_EMAIL_REPLY_TO",
        ),
    ],
)
def test_invite_email_settings_reject_malformed_addresses(
    monkeypatch: pytest.MonkeyPatch,
    env_var: str,
    value: str,
    match: str,
) -> None:
    monkeypatch.setenv("SPARKPILOT_RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv(
        "SPARKPILOT_INVITE_EMAIL_FROM",
        "SparkPilot <invites@example.invalid>",
    )
    monkeypatch.setenv(
        "SPARKPILOT_COGNITO_HOSTED_UI_URL",
        "https://auth.example.invalid/oauth2/authorize",
    )
    monkeypatch.setenv("SPARKPILOT_APP_BASE_URL", "https://app.example.invalid")
    monkeypatch.setenv(env_var, value)
    _clear_settings_cache()

    with pytest.raises(ValueError, match=match):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()


def test_invite_email_requires_app_base_url_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARKPILOT_RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv(
        "SPARKPILOT_INVITE_EMAIL_FROM",
        "SparkPilot <invites@example.invalid>",
    )
    monkeypatch.setenv(
        "SPARKPILOT_COGNITO_HOSTED_UI_URL",
        "https://auth.example.invalid/oauth2/authorize",
    )
    monkeypatch.delenv("SPARKPILOT_APP_BASE_URL", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.delenv("SPARKPILOT_UI_APP_BASE_URL", raising=False)
    monkeypatch.delenv("UI_APP_BASE_URL", raising=False)
    _clear_settings_cache()

    with pytest.raises(ValueError, match="SPARKPILOT_APP_BASE_URL"):
        validate_runtime_settings(get_settings())
    _clear_settings_cache()
