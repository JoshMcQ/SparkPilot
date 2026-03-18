from __future__ import annotations

import json
import time

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from sparkpilot.oidc import OIDCTokenVerifier


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
