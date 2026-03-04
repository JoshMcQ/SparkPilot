from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
import jwt


SUPPORTED_JWT_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}


class OIDCValidationError(ValueError):
    """Token is invalid for SparkPilot authentication."""


@dataclass(frozen=True)
class OIDCIdentity:
    subject: str
    claims: dict[str, Any]


@dataclass(frozen=True)
class OIDCClientToken:
    access_token: str
    expires_at_epoch_seconds: float


def _read_uri_json(uri: str, *, timeout_seconds: float) -> dict[str, Any]:
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        path_text = unquote(parsed.path or "")
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            path_text = f"//{parsed.netloc}{path_text}"
        # Windows file URIs encode local drive paths as /C:/...
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", path_text):
            path_text = path_text[1:]
        payload = json.loads(Path(path_text).read_text(encoding="utf-8"))
    else:
        response = httpx.get(uri, timeout=timeout_seconds)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise OIDCValidationError("OIDC metadata response must be a JSON object.")
    return payload


class OIDCTokenVerifier:
    """JWT verification backed by OIDC JWKS."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_uri: str,
        jwks_cache_ttl_seconds: int = 300,
        http_timeout_seconds: float = 5.0,
    ) -> None:
        self.issuer = issuer.strip()
        self.audience = audience.strip()
        self.jwks_uri = jwks_uri.strip()
        self.jwks_cache_ttl_seconds = max(10, jwks_cache_ttl_seconds)
        self.http_timeout_seconds = max(1.0, http_timeout_seconds)
        self._cached_jwks: dict[str, jwt.PyJWK] = {}
        self._cached_at_monotonic: float = 0.0

    def _jwks_stale(self) -> bool:
        if not self._cached_jwks:
            return True
        return (time.monotonic() - self._cached_at_monotonic) >= self.jwks_cache_ttl_seconds

    def _refresh_jwks(self) -> None:
        payload = _read_uri_json(self.jwks_uri, timeout_seconds=self.http_timeout_seconds)
        keys = payload.get("keys")
        if not isinstance(keys, list) or not keys:
            raise OIDCValidationError("OIDC_JWKS_URI did not return a non-empty 'keys' array.")

        parsed: dict[str, jwt.PyJWK] = {}
        fallback_index = 0
        for item in keys:
            if not isinstance(item, dict):
                continue
            kid = str(item.get("kid") or "")
            if not kid:
                kid = f"__anon_{fallback_index}"
                fallback_index += 1
            parsed[kid] = jwt.PyJWK.from_dict(item)
        if not parsed:
            raise OIDCValidationError("OIDC_JWKS_URI did not include usable JWK keys.")
        self._cached_jwks = parsed
        self._cached_at_monotonic = time.monotonic()

    def _resolve_signing_key(self, token: str) -> tuple[str, jwt.PyJWK]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise OIDCValidationError(f"OIDC JWT validation failed: {exc}") from exc
        algorithm = str(header.get("alg") or "")
        if algorithm not in SUPPORTED_JWT_ALGORITHMS:
            raise OIDCValidationError(f"Unsupported JWT signing algorithm '{algorithm}'.")

        if self._jwks_stale():
            self._refresh_jwks()

        kid = str(header.get("kid") or "")
        if kid and kid in self._cached_jwks:
            return algorithm, self._cached_jwks[kid]

        # Refresh once in case key rotation happened between cache updates.
        self._refresh_jwks()
        if kid and kid in self._cached_jwks:
            return algorithm, self._cached_jwks[kid]

        if not kid and len(self._cached_jwks) == 1:
            only_key = next(iter(self._cached_jwks.values()))
            return algorithm, only_key

        raise OIDCValidationError("JWT kid was not found in configured JWKS.")

    def verify_access_token(self, token: str) -> OIDCIdentity:
        algorithm, signing_key = self._resolve_signing_key(token)
        try:
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["sub", "iss", "aud", "exp"]},
            )
        except jwt.PyJWTError as exc:
            raise OIDCValidationError(f"OIDC JWT validation failed: {exc}") from exc
        if not isinstance(claims, dict):
            raise OIDCValidationError("OIDC JWT claims payload must be an object.")
        subject = str(claims.get("sub") or "").strip()
        if not subject:
            raise OIDCValidationError("OIDC JWT is missing required subject claim.")
        return OIDCIdentity(subject=subject, claims=claims)


def discover_token_endpoint(*, issuer: str, timeout_seconds: float = 10.0) -> str:
    issuer_text = issuer.rstrip("/")
    metadata_url = f"{issuer_text}/.well-known/openid-configuration"
    payload = _read_uri_json(metadata_url, timeout_seconds=timeout_seconds)
    token_endpoint = str(payload.get("token_endpoint") or "").strip()
    if not token_endpoint:
        raise OIDCValidationError(
            "OIDC discovery did not provide token_endpoint. Configure a standards-compliant issuer."
        )
    return token_endpoint


def fetch_client_credentials_token(
    *,
    issuer: str,
    audience: str,
    client_id: str,
    client_secret: str,
    token_endpoint: str | None = None,
    scope: str | None = None,
    timeout_seconds: float = 10.0,
) -> OIDCClientToken:
    endpoint = (token_endpoint or "").strip() or discover_token_endpoint(
        issuer=issuer,
        timeout_seconds=timeout_seconds,
    )
    data: dict[str, str] = {
        "grant_type": "client_credentials",
        "audience": audience,
    }
    if scope:
        data["scope"] = scope
    response = httpx.post(
        endpoint,
        data=data,
        auth=(client_id, client_secret),
        headers={"Accept": "application/json"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise OIDCValidationError("OIDC token response must be a JSON object.")
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise OIDCValidationError("OIDC token response is missing access_token.")
    expires_in = int(payload.get("expires_in") or 300)
    expires_at = time.time() + max(30, expires_in)
    return OIDCClientToken(access_token=access_token, expires_at_epoch_seconds=expires_at)
