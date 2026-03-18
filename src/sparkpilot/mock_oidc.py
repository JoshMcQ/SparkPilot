from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Final
from urllib.parse import parse_qs

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
import jwt
import uvicorn


def _parse_clients(raw: str) -> dict[str, str]:
    clients: dict[str, str] = {}
    for token in raw.split(","):
        pair = token.strip()
        if not pair:
            continue
        client_id, sep, client_secret = pair.partition(":")
        if not sep or not client_id.strip() or not client_secret.strip():
            continue
        clients[client_id.strip()] = client_secret.strip()
    return clients


MOCK_ISSUER: Final[str] = os.getenv("MOCK_OIDC_ISSUER", "http://sparkpilot-oidc:8080").rstrip("/")
MOCK_AUDIENCE: Final[str] = os.getenv("MOCK_OIDC_AUDIENCE", "sparkpilot-api")
MOCK_CLIENTS: Final[dict[str, str]] = _parse_clients(
    os.getenv("MOCK_OIDC_CLIENTS", "sparkpilot-ui:sparkpilot-ui-secret,sparkpilot-cli:sparkpilot-cli-secret")
)
MOCK_TOKEN_TTL_SECONDS: Final[int] = max(60, int(os.getenv("MOCK_OIDC_TOKEN_TTL_SECONDS", "3600")))
MOCK_KID: Final[str] = os.getenv("MOCK_OIDC_KID", "sparkpilot-local-dev-kid")
MOCK_ALLOW_SUBJECT_OVERRIDE: Final[bool] = (
    os.getenv("MOCK_OIDC_ALLOW_SUBJECT_OVERRIDE", "true").strip().lower() == "true"
)
MOCK_STABLE_KEY_PATH: Final[str] = os.getenv("MOCK_OIDC_STABLE_KEY_PATH", "").strip()


def _load_or_generate_key() -> rsa.RSAPrivateKey:
    """Load a stable PEM key from file, or generate an ephemeral key.

    When MOCK_OIDC_STABLE_KEY_PATH is set, the key is loaded from (or written
    to) that path on first startup so it survives container restarts (#84).
    """
    if not MOCK_STABLE_KEY_PATH:
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)

    key_path = Path(MOCK_STABLE_KEY_PATH)
    if key_path.exists():
        pem_data = key_path.read_bytes()
        loaded = serialization.load_pem_private_key(pem_data, password=None)
        if not isinstance(loaded, rsa.RSAPrivateKey):
            raise TypeError(f"Expected RSA key at {key_path}, got {type(loaded).__name__}")
        return loaded

    # Generate and persist
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return private_key


_PRIVATE_KEY = _load_or_generate_key()
_PUBLIC_JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_PRIVATE_KEY.public_key()))
_PUBLIC_JWK["kid"] = MOCK_KID
_PUBLIC_JWK["use"] = "sig"
_PUBLIC_JWK["alg"] = "RS256"

app = FastAPI(title="SparkPilot Mock OIDC")


def _parse_basic_auth(authorization: str | None) -> tuple[str | None, str | None]:
    auth_text = (authorization or "").strip()
    if not auth_text:
        return None, None
    scheme, _, encoded = auth_text.partition(" ")
    if scheme.lower() != "basic" or not encoded.strip():
        return None, None
    try:
        decoded = base64.b64decode(encoded.strip()).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - malformed auth headers should return 401.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed Basic authorization header.",
        ) from exc
    client_id, sep, client_secret = decoded.partition(":")
    if not sep:
        return None, None
    return client_id.strip(), client_secret.strip()


def _issue_token(*, subject: str, audience: str) -> str:
    now = int(time.time())
    claims = {
        "sub": subject,
        "iss": MOCK_ISSUER,
        "aud": audience,
        "iat": now,
        "exp": now + MOCK_TOKEN_TTL_SECONDS,
    }
    return jwt.encode(
        claims,
        _PRIVATE_KEY,
        algorithm="RS256",
        headers={"kid": MOCK_KID, "typ": "JWT"},
    )


@app.get("/.well-known/openid-configuration")
def openid_configuration() -> JSONResponse:
    return JSONResponse(
        {
            "issuer": MOCK_ISSUER,
            "jwks_uri": f"{MOCK_ISSUER}/.well-known/jwks.json",
            "token_endpoint": f"{MOCK_ISSUER}/oauth/token",
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
            "grant_types_supported": ["client_credentials"],
            "response_types_supported": [],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
        }
    )


@app.get("/.well-known/jwks.json")
def jwks() -> JSONResponse:
    return JSONResponse({"keys": [_PUBLIC_JWK]})


@app.post("/oauth/token")
async def token(request: Request, authorization: str | None = Header(default=None)) -> JSONResponse:
    body = (await request.body()).decode("utf-8")
    form = parse_qs(body, keep_blank_values=True)
    grant_type = (form.get("grant_type", [""])[0] or "").strip()
    audience = (form.get("audience", [""])[0] or "").strip()
    requested_subject = (form.get("subject", [""])[0] or "").strip()
    client_id_form = (form.get("client_id", [""])[0] or "").strip()
    client_secret_form = (form.get("client_secret", [""])[0] or "").strip()

    if grant_type != "client_credentials":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported grant_type; expected client_credentials.",
        )

    client_id, client_secret = _parse_basic_auth(authorization)
    if not client_id:
        client_id = client_id_form or None
        client_secret = client_secret_form or None

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing client credentials.",
        )

    expected_secret = MOCK_CLIENTS.get(client_id)
    if not expected_secret or expected_secret != client_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials.",
        )
    if requested_subject and not MOCK_ALLOW_SUBJECT_OVERRIDE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="subject override is disabled for this mock OIDC deployment.",
        )

    token_audience = audience or MOCK_AUDIENCE
    token_subject = requested_subject or f"service:{client_id}"
    access_token = _issue_token(subject=token_subject, audience=token_audience)
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": MOCK_TOKEN_TTL_SECONDS,
        }
    )


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def main() -> None:
    host = os.getenv("MOCK_OIDC_HOST", "0.0.0.0")
    port = int(os.getenv("MOCK_OIDC_PORT", "8080"))
    uvicorn.run("sparkpilot.mock_oidc:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
