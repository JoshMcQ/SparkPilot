from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from sparkpilot.api import _oidc_verifier, _oidc_verifiers, app
from sparkpilot.config import get_settings, validate_runtime_settings
from sparkpilot.db import Base, SessionLocal, engine
from sparkpilot.invite_email import InviteEmailDelivery
from sparkpilot.models import (
    AuditEvent,
    MagicLinkLog,
    MagicLinkToken,
    Tenant,
    Team,
    User,
    UserIdentity,
)
from tests.conftest import (
    TEST_CUSTOMER_OIDC_AUDIENCE,
    TEST_CUSTOMER_OIDC_ISSUER,
    TEST_INTERNAL_OIDC_AUDIENCE,
    TEST_INTERNAL_OIDC_ISSUER,
    _BaseTestClient,
    issue_test_token,
)
from tests.db_test_utils import reset_sqlite_test_db


def _reset_db() -> None:
    reset_sqlite_test_db(base=Base, engine=engine, session_local=SessionLocal)


def _set_internal_admin_env(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    sent_invites: list[dict[str, str]] = []

    def _capture_invite_email(
        *,
        recipient_email: str,
        tenant_name: str,
        invite_url: str,
        tenant_id: str,
        user_id: str,
        ttl_hours: int,
        idempotency_key: str,
    ) -> InviteEmailDelivery:
        sent_invites.append(
            {
                "recipient_email": recipient_email,
                "tenant_name": tenant_name,
                "invite_url": invite_url,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "ttl_hours": str(ttl_hours),
                "idempotency_key": idempotency_key,
            }
        )
        return InviteEmailDelivery(
            provider="resend",
            recipient_email=recipient_email,
            status="sent",
            provider_message_id=f"email-{len(sent_invites)}",
        )

    monkeypatch.setenv("SPARKPILOT_INTERNAL_ADMINS", "admin@example.invalid")
    monkeypatch.setenv(
        "SPARKPILOT_COGNITO_HOSTED_UI_URL", "https://auth.example.com/oauth2/authorize"
    )
    monkeypatch.setenv("SPARKPILOT_MAGIC_LINK_TTL_HOURS", "24")
    monkeypatch.setenv(
        "SPARKPILOT_INVITE_STATE_SECRET",
        "sparkpilot-invite-state-secret-for-tests",
    )
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()
    _oidc_verifiers.cache_clear()
    monkeypatch.setattr(
        "sparkpilot.services.internal_admin.send_invite_email",
        _capture_invite_email,
    )
    return sent_invites


def _auth_headers(
    subject: str,
    email: str,
    *,
    pool: str = "internal",
) -> dict[str, str]:
    if pool == "internal":
        issuer = TEST_INTERNAL_OIDC_ISSUER
        audience = TEST_INTERNAL_OIDC_AUDIENCE
    elif pool == "customer":
        issuer = TEST_CUSTOMER_OIDC_ISSUER
        audience = TEST_CUSTOMER_OIDC_AUDIENCE
    else:
        raise ValueError("pool must be 'internal' or 'customer'.")
    token = issue_test_token(
        subject,
        issuer=issuer,
        audience=audience,
        extra_claims={"email": email},
    )
    return {"Authorization": f"Bearer {token}"}


def _invite_token_from_url(invite_url: str) -> str:
    return parse_qs(urlsplit(invite_url).query)["token"][0]


def test_issue_test_token_rejects_reserved_claim_overrides() -> None:
    with pytest.raises(ValueError):
        issue_test_token("subject", extra_claims={"sub": "override"})


def test_validate_runtime_settings_rejects_invalid_cognito_hosted_ui_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARKPILOT_COGNITO_HOSTED_UI_URL", "not-a-valid-url")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()
    _oidc_verifiers.cache_clear()

    with pytest.raises(
        ValueError,
        match="SPARKPILOT_COGNITO_HOSTED_UI_URL must be a valid http\\(s\\) URL",
    ):
        validate_runtime_settings(get_settings())


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
            headers=_auth_headers("ops-subject", "admin@example.invalid"),
        )
        assert internal.status_code == 200
        assert internal.json() == []


def test_internal_tenant_invite_happy_path_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

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
        assert created["invite_email_recipient"] == "admin@acme.example"
        assert created["invite_email_provider"] == "resend"
        assert created["invite_email_status"] == "sent"
        assert created["invite_email_provider_message_id"] == "email-1"
        assert created["invite_email_failure_detail"] is None
        assert "magic_link_url" not in created
        assert len(sent_invites) == 1
        magic_link_url = sent_invites[0]["invite_url"]
        assert "/v1/invite/accept?token=" in magic_link_url
        token = _invite_token_from_url(magic_link_url)

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
            assert "token=" not in logs[0].magic_link_url
            assert logs[0].magic_link_url == magic_link_url.split("?", 1)[0]

        accept = client.get(
            "/v1/invite/accept",
            params={"token": token},
            follow_redirects=False,
        )
        assert accept.status_code == 307
        location = accept.headers["location"]
        state = parse_qs(urlsplit(location).query)["state"][0]

        invited_headers = _auth_headers(
            "cognito-user-subject-1",
            "admin@acme.example",
            pool="customer",
        )
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


def test_internal_tenant_create_writes_internal_audit_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        response = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Audit Tenant",
                "admin_email": "audit@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert response.status_code == 201, response.text
        payload = response.json()

        with SessionLocal() as db:
            event = (
                db.execute(
                    select(AuditEvent)
                    .where(
                        AuditEvent.action == "tenant.create",
                        AuditEvent.tenant_id == payload["tenant_id"],
                    )
                    .order_by(AuditEvent.created_at.desc())
                )
                .scalars()
                .first()
            )
            assert event is not None
            assert event.actor == "admin@example.invalid"
            assert event.details_json.get("actor_pool") == "internal_pool"
            assert event.details_json.get("target_tenant_id") == payload["tenant_id"]
            assert event.details_json.get("target_user_id") == payload["user_id"]
            assert event.details_json.get("request_id")
            assert event.source_ip is not None

            email_event = (
                db.execute(
                    select(AuditEvent)
                    .where(
                        AuditEvent.action == "user.invite_email_sent",
                        AuditEvent.tenant_id == payload["tenant_id"],
                        AuditEvent.entity_id == payload["user_id"],
                    )
                    .order_by(AuditEvent.created_at.desc())
                )
                .scalars()
                .first()
            )
            assert email_event is not None
            assert email_event.actor == "admin@example.invalid"
            assert email_event.details_json == {
                "email": "audit@tenant.example",
                "provider": "resend",
                "provider_message_id": "email-1",
            }
            assert len(sent_invites) == 1


def test_internal_tenant_create_persists_invite_and_audits_email_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    _set_internal_admin_env(monkeypatch)
    monkeypatch.setenv("SPARKPILOT_CRM_WEBHOOK_URL", "https://crm.example/webhook")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()
    _oidc_verifiers.cache_clear()
    webhook_calls: list[dict[str, str]] = []

    from sparkpilot.invite_email import InviteEmailDeliveryError

    def _fail_invite_email(**_kwargs: object) -> InviteEmailDelivery:
        raise InviteEmailDeliveryError("provider rejected invite email")

    def _capture_webhook(_url: str, payload: dict[str, str]) -> None:
        webhook_calls.append(payload)

    monkeypatch.setattr(
        "sparkpilot.services.internal_admin.send_invite_email",
        _fail_invite_email,
    )
    monkeypatch.setattr("sparkpilot.crm_webhook._post_crm_webhook", _capture_webhook)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        response = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Email Failure Tenant",
                "admin_email": "email-failure@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["invite_email_recipient"] == "email-failure@tenant.example"
        assert payload["invite_email_provider"] == "resend"
        assert payload["invite_email_status"] == "failed"
        assert payload["invite_email_provider_message_id"] is None
        assert "provider rejected" not in payload["invite_email_failure_detail"]
        assert "token=" not in payload["invite_email_failure_detail"]
        assert "token=" not in response.text

    deadline = time.time() + 1.0
    while not webhook_calls and time.time() < deadline:
        time.sleep(0.01)
    assert webhook_calls
    assert webhook_calls[0]["event_type"] == "tenant.created"

    with SessionLocal() as db:
        user = db.execute(
            select(User).where(User.email == "email-failure@tenant.example")
        ).scalar_one_or_none()
        assert user is not None
        token = db.execute(
            select(MagicLinkToken).where(MagicLinkToken.user_id == user.id)
        ).scalar_one_or_none()
        assert token is not None
        event = (
            db.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.action == "user.invite_email_failed",
                    AuditEvent.entity_id == user.id,
                )
                .order_by(AuditEvent.created_at.desc())
            )
            .scalars()
            .first()
        )
        assert event is not None
        assert event.details_json == {
            "email": "email-failure@tenant.example",
            "provider": "resend",
            "error_type": "InviteEmailDeliveryError",
        }


def test_tenant_lifecycle_event_failure_does_not_block_invite_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)

    def _raise_emit_failure(**_kwargs: object) -> None:
        raise RuntimeError("webhook dispatch failed")

    monkeypatch.setattr(
        "sparkpilot.services.internal_admin.emit_tenant_lifecycle_event",
        _raise_emit_failure,
    )
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        response = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Webhook Failure Tenant",
                "admin_email": "webhook-failure@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["invite_email_recipient"] == "webhook-failure@tenant.example"
        assert payload["invite_email_status"] == "sent"

    assert len(sent_invites) == 1


def test_invite_email_audit_commit_failure_does_not_fail_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sparkpilot.services import internal_admin as internal_admin_service

    tenant = Tenant(id="tenant-123", name="Audit Commit Failure Tenant")
    user = User(
        id="user-123",
        tenant_id=tenant.id,
        email="audit-commit-failure@tenant.example",
        role="admin",
    )
    sent_delivery = InviteEmailDelivery(
        provider="resend",
        recipient_email=user.email,
        status="sent",
        provider_message_id="email-123",
    )

    class _AuditCommitFailureSession:
        rollback_called = False

        def add(self, _row: object) -> None:
            return None

        def commit(self) -> None:
            raise RuntimeError("audit commit failed")

        def rollback(self) -> None:
            self.rollback_called = True

    db = _AuditCommitFailureSession()
    monkeypatch.setattr(
        internal_admin_service,
        "send_invite_email",
        lambda **_kwargs: sent_delivery,
    )

    result = internal_admin_service._send_invite_email_and_audit(
        db,
        tenant=tenant,
        user=user,
        created_by="admin@example.invalid",
        source_ip=None,
        invite_url="https://app.example.invalid/v1/invite/accept?token=secret-token",
        ttl_hours=24,
        idempotency_key="invite:token-row-123",
        failure_detail="Invite email delivery failed.",
    )

    assert result is sent_delivery
    assert db.rollback_called is True


def test_internal_tenant_read_and_regenerate_write_audit_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Audit Coverage Tenant",
                "admin_email": "audit-coverage@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert create.status_code == 201, create.text
        payload = create.json()
        tenant_id = payload["tenant_id"]
        user_id = payload["user_id"]

        listed = client.get("/v1/internal/tenants", headers=internal_headers)
        assert listed.status_code == 200, listed.text

        detail = client.get(
            f"/v1/internal/tenants/{tenant_id}", headers=internal_headers
        )
        assert detail.status_code == 200, detail.text

        regenerate = client.post(
            f"/v1/internal/tenants/{tenant_id}/users/{user_id}/regenerate-invite",
            headers=internal_headers,
        )
        assert regenerate.status_code == 200, regenerate.text

    with SessionLocal() as db:
        actions = [
            row[0]
            for row in db.execute(
                select(AuditEvent.action).where(
                    AuditEvent.action.in_(
                        [
                            "tenant.create",
                            "tenant.list_view",
                            "tenant.detail_view",
                            "tenant.invite_regenerate",
                        ]
                    ),
                    AuditEvent.actor == "admin@example.invalid",
                )
            ).all()
        ]
        assert "tenant.create" in actions
        assert "tenant.list_view" in actions
        assert "tenant.detail_view" in actions
        assert "tenant.invite_regenerate" in actions


def test_tenant_created_webhook_fires_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    _set_internal_admin_env(monkeypatch)
    monkeypatch.setenv("SPARKPILOT_CRM_WEBHOOK_URL", "https://crm.example/webhook")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()
    _oidc_verifiers.cache_clear()
    calls: list[dict[str, str]] = []

    def _capture(url: str, payload: dict[str, str]) -> None:
        assert url == "https://crm.example/webhook"
        calls.append(payload)

    monkeypatch.setattr("sparkpilot.crm_webhook._post_crm_webhook", _capture)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        response = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Webhook Tenant",
                "admin_email": "webhook@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert response.status_code == 201, response.text
    deadline = time.time() + 1.0
    while not calls and time.time() < deadline:
        time.sleep(0.01)
    assert calls
    assert calls[0]["event_type"] == "tenant.created"
    assert calls[0]["tenant_name"] == "Webhook Tenant"
    assert calls[0]["admin_email"] == "webhook@tenant.example"
    assert calls[0]["actor_email"] == "admin@example.invalid"


def test_tenant_created_webhook_not_called_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    _set_internal_admin_env(monkeypatch)
    monkeypatch.setenv("SPARKPILOT_CRM_WEBHOOK_URL", "")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()
    _oidc_verifiers.cache_clear()
    calls: list[dict[str, str]] = []

    def _capture(_url: str, payload: dict[str, str]) -> None:
        calls.append(payload)

    monkeypatch.setattr("sparkpilot.crm_webhook._post_crm_webhook", _capture)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        response = client.post(
            "/v1/internal/tenants",
            json={
                "name": "No Webhook Tenant",
                "admin_email": "no-webhook@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert response.status_code == 201, response.text
    time.sleep(0.1)
    assert calls == []


def test_tenant_created_webhook_is_fire_and_forget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    _set_internal_admin_env(monkeypatch)
    monkeypatch.setenv("SPARKPILOT_CRM_WEBHOOK_URL", "https://crm.example/webhook")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()
    _oidc_verifiers.cache_clear()
    dispatched = threading.Event()

    def _slow_capture(_url: str, _payload: dict[str, str]) -> None:
        dispatched.set()
        time.sleep(1.0)

    monkeypatch.setattr("sparkpilot.crm_webhook._post_crm_webhook", _slow_capture)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        started = time.perf_counter()
        response = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Async Webhook Tenant",
                "admin_email": "async-webhook@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        elapsed = time.perf_counter() - started
        assert response.status_code == 201, response.text
        assert elapsed < 0.5
        assert dispatched.wait(timeout=1.0)


def test_tenant_invite_regenerated_webhook_fires_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    _set_internal_admin_env(monkeypatch)
    monkeypatch.setenv("SPARKPILOT_CRM_WEBHOOK_URL", "https://crm.example/webhook")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()
    _oidc_verifiers.cache_clear()
    calls: list[dict[str, str]] = []

    def _capture(_url: str, payload: dict[str, str]) -> None:
        calls.append(payload)

    monkeypatch.setattr("sparkpilot.crm_webhook._post_crm_webhook", _capture)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Regen Webhook Tenant",
                "admin_email": "regen-webhook@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert create.status_code == 201, create.text
        payload = create.json()
        regenerate = client.post(
            f"/v1/internal/tenants/{payload['tenant_id']}/users/{payload['user_id']}/regenerate-invite",
            headers=internal_headers,
        )
        assert regenerate.status_code == 200, regenerate.text

    deadline = time.time() + 1.0
    while len(calls) < 2 and time.time() < deadline:
        time.sleep(0.01)
    event_types = [call["event_type"] for call in calls]
    assert "tenant.invite_regenerated" in event_types


def test_tenant_admin_invite_consumed_webhook_fires_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    monkeypatch.setenv("SPARKPILOT_CRM_WEBHOOK_URL", "https://crm.example/webhook")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()
    _oidc_verifiers.cache_clear()
    calls: list[dict[str, str]] = []

    def _capture(_url: str, payload: dict[str, str]) -> None:
        calls.append(payload)

    monkeypatch.setattr("sparkpilot.crm_webhook._post_crm_webhook", _capture)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Consumed Webhook Tenant",
                "admin_email": "consumed-webhook@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert create.status_code == 201, create.text
        token = _invite_token_from_url(sent_invites[-1]["invite_url"])

        accept = client.get(
            "/v1/invite/accept",
            params={"token": token},
            follow_redirects=False,
        )
        assert accept.status_code == 307
        state = parse_qs(urlsplit(accept.headers["location"]).query)["state"][0]
        invited_headers = _auth_headers(
            "consumed-webhook-subject",
            "consumed-webhook@tenant.example",
            pool="customer",
        )
        callback = client.get(
            "/auth/callback",
            params={"state": state},
            headers=invited_headers,
        )
        assert callback.status_code == 200, callback.text

    deadline = time.time() + 1.0
    while len(calls) < 2 and time.time() < deadline:
        time.sleep(0.01)
    event_types = [call["event_type"] for call in calls]
    assert "tenant.admin_invite_consumed" in event_types


def test_invite_accept_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

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
        assert create.status_code == 201, create.text
        token = _invite_token_from_url(sent_invites[-1]["invite_url"])
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


def test_internal_tenant_create_rejects_invalid_admin_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        response = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Invalid Email Tenant",
                "admin_email": "not-an-email",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert response.status_code == 422


def test_invite_accept_rejects_consumed_and_wrong_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

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
        assert create.status_code == 201, create.text
        token = _invite_token_from_url(sent_invites[-1]["invite_url"])

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


def test_invite_accept_fails_closed_when_cognito_hosted_ui_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    monkeypatch.setenv("SPARKPILOT_COGNITO_HOSTED_UI_URL", "")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()
    _oidc_verifiers.cache_clear()
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Missing Hosted UI Tenant",
                "admin_email": "hosted-ui@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert create.status_code == 201, create.text
        token = _invite_token_from_url(sent_invites[-1]["invite_url"])
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        response = client.get("/v1/invite/accept", params={"token": token})
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"].lower()

        with SessionLocal() as db:
            row = db.execute(
                select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash)
            ).scalar_one()
            assert row.consumed_at is None


def test_regenerate_invite_after_consumption_invalidates_old_token_and_issues_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

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
        old_token = _invite_token_from_url(sent_invites[-1]["invite_url"])

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
        regenerated = regenerate.json()
        assert regenerated["invite_email_recipient"] == "regen@tenant.example"
        assert regenerated["invite_email_provider"] == "resend"
        assert regenerated["invite_email_status"] == "sent"
        assert "magic_link_url" not in regenerated
        new_token = _invite_token_from_url(sent_invites[-1]["invite_url"])
        assert new_token != old_token

        old_again = client.get("/v1/invite/accept", params={"token": old_token})
        assert old_again.status_code == 410

        new_accept = client.get(
            "/v1/invite/accept",
            params={"token": new_token},
            follow_redirects=False,
        )
        assert new_accept.status_code == 307


def test_invite_callback_rejects_reused_state_for_consumed_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Replay Tenant",
                "admin_email": "replay@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert create.status_code == 201, create.text
        token = _invite_token_from_url(sent_invites[-1]["invite_url"])
        accept = client.get(
            "/v1/invite/accept",
            params={"token": token},
            follow_redirects=False,
        )
        state = parse_qs(urlsplit(accept.headers["location"]).query)["state"][0]
        invited_headers = _auth_headers(
            "invite-user-sub", "replay@tenant.example", pool="customer"
        )

        first_callback = client.get(
            "/auth/callback",
            params={"state": state},
            headers=invited_headers,
        )
        assert first_callback.status_code == 200

        replayed = client.get(
            "/auth/callback",
            params={"state": state},
            headers=invited_headers,
        )
        assert replayed.status_code == 410
        assert "consumed" in replayed.json()["detail"].lower()


def test_invite_callback_rejects_tampered_state_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Tamper Tenant",
                "admin_email": "tamper@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert create.status_code == 201, create.text
        token = _invite_token_from_url(sent_invites[-1]["invite_url"])
        accept = client.get(
            "/v1/invite/accept",
            params={"token": token},
            follow_redirects=False,
        )
        state = parse_qs(urlsplit(accept.headers["location"]).query)["state"][0]
        prefix, body, _ = state.split(".")
        tampered_state = f"{prefix}.{body}.tampered-signature"
        invited_headers = _auth_headers(
            "invite-user-sub", "tamper@tenant.example", pool="customer"
        )

        callback = client.get(
            "/auth/callback",
            params={"state": tampered_state},
            headers=invited_headers,
        )
        assert callback.status_code == 401
        assert "invalid invite state" in callback.json()["detail"].lower()


def test_invite_callback_rejects_valid_signed_state_when_token_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Expired Callback Tenant",
                "admin_email": "expired-callback@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert create.status_code == 201, create.text
        token = _invite_token_from_url(sent_invites[-1]["invite_url"])
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        accept = client.get(
            "/v1/invite/accept",
            params={"token": token},
            follow_redirects=False,
        )
        state = parse_qs(urlsplit(accept.headers["location"]).query)["state"][0]

        with SessionLocal() as db:
            row = db.execute(
                select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash)
            ).scalar_one()
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            db.commit()

        invited_headers = _auth_headers(
            "invite-user-sub",
            "expired-callback@tenant.example",
            pool="customer",
        )
        callback = client.get(
            "/auth/callback",
            params={"state": state},
            headers=invited_headers,
        )
        assert callback.status_code == 410
        assert "expired" in callback.json()["detail"].lower()


def test_invite_callback_rejects_authenticated_email_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Mismatch Tenant",
                "admin_email": "expected@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert create.status_code == 201, create.text
        token = _invite_token_from_url(sent_invites[-1]["invite_url"])
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        accept = client.get(
            "/v1/invite/accept",
            params={"token": token},
            follow_redirects=False,
        )
        state = parse_qs(urlsplit(accept.headers["location"]).query)["state"][0]

        mismatch_headers = _auth_headers(
            "invite-user-sub", "wrong@tenant.example", pool="customer"
        )
        callback = client.get(
            "/auth/callback",
            params={"state": state},
            headers=mismatch_headers,
        )
        assert callback.status_code == 401
        assert "does not match" in callback.json()["detail"].lower()

        with SessionLocal() as db:
            row = db.execute(
                select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash)
            ).scalar_one()
            assert row.callback_consumed_at is None


def test_user_identity_user_id_is_unique(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Unique Identity Tenant",
                "admin_email": "unique@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        assert create.status_code == 201, create.text
        payload = create.json()
        tenant_id = payload["tenant_id"]
        user_id = payload["user_id"]
        token = _invite_token_from_url(sent_invites[-1]["invite_url"])

        accept = client.get(
            "/v1/invite/accept",
            params={"token": token},
            follow_redirects=False,
        )
        state = parse_qs(urlsplit(accept.headers["location"]).query)["state"][0]
        invited_headers = _auth_headers(
            "invite-user-sub", "unique@tenant.example", pool="customer"
        )
        callback = client.get(
            "/auth/callback",
            params={"state": state},
            headers=invited_headers,
        )
        assert callback.status_code == 200

        with SessionLocal() as db:
            db.add(
                UserIdentity(
                    actor="other-subject",
                    role="admin",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    active=True,
                )
            )
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()


def test_invite_callback_preserves_existing_team_assignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    sent_invites = _set_internal_admin_env(monkeypatch)
    internal_headers = _auth_headers("ops-subject", "admin@example.invalid")

    with _BaseTestClient(app) as client:
        create = client.post(
            "/v1/internal/tenants",
            json={
                "name": "Team Preserve Tenant",
                "admin_email": "team-preserve@tenant.example",
                "federation_type": "oidc",
            },
            headers=internal_headers,
        )
        create_payload = create.json()
        tenant_id = create_payload["tenant_id"]
        user_id = create_payload["user_id"]
        first_token = _invite_token_from_url(sent_invites[-1]["invite_url"])

        first_accept = client.get(
            "/v1/invite/accept",
            params={"token": first_token},
            follow_redirects=False,
        )
        first_state = parse_qs(urlsplit(first_accept.headers["location"]).query)[
            "state"
        ][0]
        invited_headers = _auth_headers(
            "team-preserve-subject",
            "team-preserve@tenant.example",
            pool="customer",
        )
        first_callback = client.get(
            "/auth/callback",
            params={"state": first_state},
            headers=invited_headers,
        )
        assert first_callback.status_code == 200

        with SessionLocal() as db:
            team = Team(tenant_id=tenant_id, name="Ops Team")
            db.add(team)
            db.flush()
            identity = db.execute(
                select(UserIdentity).where(UserIdentity.user_id == user_id)
            ).scalar_one()
            identity.team_id = team.id
            db.commit()

        regenerate = client.post(
            f"/v1/internal/tenants/{tenant_id}/users/{user_id}/regenerate-invite",
            headers=internal_headers,
        )
        assert regenerate.status_code == 200, regenerate.text
        second_token = _invite_token_from_url(sent_invites[-1]["invite_url"])

        second_accept = client.get(
            "/v1/invite/accept",
            params={"token": second_token},
            follow_redirects=False,
        )
        second_state = parse_qs(urlsplit(second_accept.headers["location"]).query)[
            "state"
        ][0]
        second_callback = client.get(
            "/auth/callback",
            params={"state": second_state},
            headers=invited_headers,
        )
        assert second_callback.status_code == 200

        with SessionLocal() as db:
            identity = db.execute(
                select(UserIdentity).where(UserIdentity.user_id == user_id)
            ).scalar_one()
            assert identity.team_id is not None


def test_bootstrap_flow_returns_410_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_db()
    monkeypatch.setenv("SPARKPILOT_BOOTSTRAP_FLOW", "disabled")
    get_settings.cache_clear()
    _oidc_verifier.cache_clear()
    _oidc_verifiers.cache_clear()

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

    monkeypatch.delenv("SPARKPILOT_BOOTSTRAP_FLOW", raising=False)
    monkeypatch.setenv("SPARKPILOT_ENVIRONMENT", "staging")
    get_settings.cache_clear()
    assert get_settings().bootstrap_flow_enabled is False
