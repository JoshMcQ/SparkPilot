from __future__ import annotations

import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from sparkpilot.oidc import OIDCTokenVerifier, OIDCValidationError, OIDCKeyRotationError


def _make_signing_key() -> tuple[rsa.RSAPrivateKey, dict[str, str]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    return private_key, public_jwk


def _issue_token(
    *,
    private_key: rsa.RSAPrivateKey,
    kid: str,
    issuer: str,
    audience: str,
    subject: str,
) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + 600,
    }
    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": kid, "typ": "JWT"},
    )


def test_oidc_verifier_refreshes_jwks_after_signature_mismatch(tmp_path) -> None:
    issuer = "https://issuer.test"
    audience = "sparkpilot-api"
    shared_kid = "rotating-key-kid"
    jwks_path = tmp_path / "jwks.json"
    jwks_uri = jwks_path.resolve().as_uri()

    key_one, jwk_one = _make_signing_key()
    jwk_one["kid"] = shared_kid
    jwks_path.write_text(json.dumps({"keys": [jwk_one]}), encoding="utf-8")

    verifier = OIDCTokenVerifier(
        issuer=issuer,
        audience=audience,
        jwks_uri=jwks_uri,
        jwks_cache_ttl_seconds=3600,
    )

    first_token = _issue_token(
        private_key=key_one,
        kid=shared_kid,
        issuer=issuer,
        audience=audience,
        subject="user:first",
    )
    first_identity = verifier.verify_access_token(first_token)
    assert first_identity.subject == "user:first"

    # Rotate to a new key with the same kid, which can happen with non-ideal issuers.
    key_two, jwk_two = _make_signing_key()
    jwk_two["kid"] = shared_kid
    jwks_path.write_text(json.dumps({"keys": [jwk_two]}), encoding="utf-8")

    rotated_token = _issue_token(
        private_key=key_two,
        kid=shared_kid,
        issuer=issuer,
        audience=audience,
        subject="user:rotated",
    )
    rotated_identity = verifier.verify_access_token(rotated_token)
    assert rotated_identity.subject == "user:rotated"


def test_jwks_forced_refresh_throttle_rejects_flood(tmp_path) -> None:
    """Repeated bad signatures must not trigger unbounded JWKS fetches (#60)."""
    issuer = "https://issuer.test"
    audience = "sparkpilot-api"
    jwks_path = tmp_path / "jwks.json"
    jwks_uri = jwks_path.resolve().as_uri()

    good_key, good_jwk = _make_signing_key()
    good_jwk["kid"] = "good-kid"
    jwks_path.write_text(json.dumps({"keys": [good_jwk]}), encoding="utf-8")

    verifier = OIDCTokenVerifier(
        issuer=issuer,
        audience=audience,
        jwks_uri=jwks_uri,
        jwks_cache_ttl_seconds=3600,
        jwks_min_refresh_interval_seconds=0.05,
        jwks_throttle_window_seconds=60,
        jwks_throttle_max_refreshes=3,
    )

    # Initial valid token to populate cache
    good_token = _issue_token(
        private_key=good_key, kid="good-kid",
        issuer=issuer, audience=audience, subject="user:good",
    )
    assert verifier.verify_access_token(good_token).subject == "user:good"

    # Generate tokens signed with a DIFFERENT key (attacker simulation)
    bad_key, _ = _make_signing_key()

    throttled_count = 0
    for i in range(10):
        bad_token = _issue_token(
            private_key=bad_key, kid="good-kid",
            issuer=issuer, audience=audience, subject=f"bad:{i}",
        )
        try:
            verifier.verify_access_token(bad_token)
        except OIDCValidationError as exc:
            if "throttled" in str(exc).lower():
                throttled_count += 1
        time.sleep(0.06)  # just above min interval

    # Throttle should have kicked in — we allowed max 3 forced refreshes
    assert throttled_count > 0, "Expected some requests to be throttled"
    assert verifier.jwks_refresh_throttled > 0
    stats = verifier.jwks_refresh_stats
    assert stats["throttled"] > 0
    assert stats["forced"] <= 3 + 2  # resolve_signing_key + verify_access_token path


def test_jwks_legitimate_rotation_still_recovers(tmp_path) -> None:
    """Legitimate key rotation must still recover correctly after throttle (#60)."""
    issuer = "https://issuer.test"
    audience = "sparkpilot-api"
    jwks_path = tmp_path / "jwks.json"
    jwks_uri = jwks_path.resolve().as_uri()

    key_one, jwk_one = _make_signing_key()
    jwk_one["kid"] = "kid-v1"
    jwks_path.write_text(json.dumps({"keys": [jwk_one]}), encoding="utf-8")

    verifier = OIDCTokenVerifier(
        issuer=issuer,
        audience=audience,
        jwks_uri=jwks_uri,
        jwks_cache_ttl_seconds=3600,
        jwks_min_refresh_interval_seconds=0.01,
        jwks_throttle_window_seconds=60,
        jwks_throttle_max_refreshes=10,
    )

    token_v1 = _issue_token(
        private_key=key_one, kid="kid-v1",
        issuer=issuer, audience=audience, subject="user:v1",
    )
    assert verifier.verify_access_token(token_v1).subject == "user:v1"

    # Rotate - new key, same kid
    key_two, jwk_two = _make_signing_key()
    jwk_two["kid"] = "kid-v1"
    jwks_path.write_text(json.dumps({"keys": [jwk_two]}), encoding="utf-8")
    time.sleep(0.02)

    token_v2 = _issue_token(
        private_key=key_two, kid="kid-v1",
        issuer=issuer, audience=audience, subject="user:v2",
    )
    identity = verifier.verify_access_token(token_v2)
    assert identity.subject == "user:v2"


def test_jwks_refresh_stats_telemetry(tmp_path) -> None:
    """Telemetry counters must track refresh attempts and throttle decisions (#60)."""
    issuer = "https://issuer.test"
    audience = "sparkpilot-api"
    jwks_path = tmp_path / "jwks.json"
    jwks_uri = jwks_path.resolve().as_uri()

    key, jwk = _make_signing_key()
    jwk["kid"] = "tel-kid"
    jwks_path.write_text(json.dumps({"keys": [jwk]}), encoding="utf-8")

    verifier = OIDCTokenVerifier(
        issuer=issuer,
        audience=audience,
        jwks_uri=jwks_uri,
        jwks_cache_ttl_seconds=3600,
    )

    token = _issue_token(
        private_key=key, kid="tel-kid",
        issuer=issuer, audience=audience, subject="user:tel",
    )
    verifier.verify_access_token(token)

    stats = verifier.jwks_refresh_stats
    assert "total" in stats
    assert "forced" in stats
    assert "throttled" in stats
    assert stats["total"] >= 1


def test_stale_token_after_oidc_restart_raises_key_rotation_error(tmp_path) -> None:
    """Stale token from before OIDC restart (key rotation) should raise
    OIDCKeyRotationError, not a generic validation error (#84).

    Simulates: user gets a token signed with key_one, then the mock OIDC
    container restarts and generates key_two with the same kid.  The user's
    old token now fails signature verification with the new key.
    """
    issuer = "https://issuer.test"
    audience = "sparkpilot-api"
    shared_kid = "mock-dev-kid"
    jwks_path = tmp_path / "jwks.json"
    jwks_uri = jwks_path.resolve().as_uri()

    # Phase 1: original OIDC instance with key_one
    key_one, jwk_one = _make_signing_key()
    jwk_one["kid"] = shared_kid
    jwks_path.write_text(json.dumps({"keys": [jwk_one]}), encoding="utf-8")

    verifier = OIDCTokenVerifier(
        issuer=issuer,
        audience=audience,
        jwks_uri=jwks_uri,
        jwks_cache_ttl_seconds=3600,
        jwks_min_refresh_interval_seconds=0.01,
        jwks_throttle_window_seconds=60,
        jwks_throttle_max_refreshes=10,
    )

    # User obtains a token from the original instance
    stale_token = _issue_token(
        private_key=key_one,
        kid=shared_kid,
        issuer=issuer,
        audience=audience,
        subject="user:before-restart",
    )
    identity = verifier.verify_access_token(stale_token)
    assert identity.subject == "user:before-restart"

    # Phase 2: OIDC container restarts — new key, same kid
    key_two, jwk_two = _make_signing_key()
    jwk_two["kid"] = shared_kid
    jwks_path.write_text(json.dumps({"keys": [jwk_two]}), encoding="utf-8")
    time.sleep(0.02)  # ensure throttle interval is satisfied

    # Simulate cache expiry (in production this happens after jwks_cache_ttl_seconds)
    verifier._cached_at_monotonic = time.monotonic() - verifier.jwks_cache_ttl_seconds - 1

    # The stale token should now raise OIDCKeyRotationError
    with pytest.raises(OIDCKeyRotationError, match="[Ss]igning keys have changed"):
        verifier.verify_access_token(stale_token)

    # A NEW token signed with key_two should succeed
    fresh_token = _issue_token(
        private_key=key_two,
        kid=shared_kid,
        issuer=issuer,
        audience=audience,
        subject="user:after-restart",
    )
    identity = verifier.verify_access_token(fresh_token)
    assert identity.subject == "user:after-restart"


def test_key_rotation_error_is_oidc_validation_error_subclass() -> None:
    """OIDCKeyRotationError must be a subclass of OIDCValidationError so
    existing except blocks still catch it (#84)."""
    err = OIDCKeyRotationError("test")
    assert isinstance(err, OIDCValidationError)
    assert isinstance(err, ValueError)


def test_cognito_style_access_token_with_client_id_claim_is_accepted(tmp_path) -> None:
    issuer = "https://issuer.test"
    audience = "sparkpilot-api"
    kid = "cognito-kid"
    jwks_path = tmp_path / "jwks.json"
    jwks_uri = jwks_path.resolve().as_uri()

    key, jwk = _make_signing_key()
    jwk["kid"] = kid
    jwks_path.write_text(json.dumps({"keys": [jwk]}), encoding="utf-8")

    verifier = OIDCTokenVerifier(
        issuer=issuer,
        audience=audience,
        jwks_uri=jwks_uri,
        jwks_cache_ttl_seconds=3600,
    )

    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "user:cognito",
            "iss": issuer,
            "client_id": audience,
            "iat": now,
            "exp": now + 600,
        },
        key,
        algorithm="RS256",
        headers={"kid": kid, "typ": "JWT"},
    )

    identity = verifier.verify_access_token(token)
    assert identity.subject == "user:cognito"


def test_missing_aud_and_client_id_is_rejected(tmp_path) -> None:
    issuer = "https://issuer.test"
    audience = "sparkpilot-api"
    kid = "missing-aud-kid"
    jwks_path = tmp_path / "jwks.json"
    jwks_uri = jwks_path.resolve().as_uri()

    key, jwk = _make_signing_key()
    jwk["kid"] = kid
    jwks_path.write_text(json.dumps({"keys": [jwk]}), encoding="utf-8")

    verifier = OIDCTokenVerifier(
        issuer=issuer,
        audience=audience,
        jwks_uri=jwks_uri,
        jwks_cache_ttl_seconds=3600,
    )

    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "user:no-audience",
            "iss": issuer,
            "iat": now,
            "exp": now + 600,
        },
        key,
        algorithm="RS256",
        headers={"kid": kid, "typ": "JWT"},
    )

    with pytest.raises(OIDCValidationError, match="audience/client_id"):
        verifier.verify_access_token(token)
