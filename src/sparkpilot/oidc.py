from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
import jwt

logger = logging.getLogger(__name__)

SUPPORTED_JWT_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}


class OIDCValidationError(ValueError):
    """Token is invalid for SparkPilot authentication."""


class OIDCKeyRotationError(OIDCValidationError):
    """Signature verification failed after JWKS refresh — indicates key rotation.

    The UI should detect this and prompt the user to re-authenticate rather than
    showing a confusing generic "signature verification failed" error.
    """


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

# ---------------------------------------------------------------------------
# JWKS refresh throttle defaults
# ---------------------------------------------------------------------------
_DEFAULT_JWKS_MIN_REFRESH_INTERVAL_SECONDS = 10  # min seconds between forced refreshes
_DEFAULT_JWKS_THROTTLE_WINDOW_SECONDS = 60  # sliding window for counting forced refreshes
_DEFAULT_JWKS_THROTTLE_MAX_REFRESHES = 5  # max forced refreshes per sliding window


class OIDCTokenVerifier:
    """JWT verification backed by OIDC JWKS with throttled refresh."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_uri: str,
        jwks_cache_ttl_seconds: int = 300,
        http_timeout_seconds: float = 5.0,
        jwks_min_refresh_interval_seconds: float = _DEFAULT_JWKS_MIN_REFRESH_INTERVAL_SECONDS,
        jwks_throttle_window_seconds: float = _DEFAULT_JWKS_THROTTLE_WINDOW_SECONDS,
        jwks_throttle_max_refreshes: int = _DEFAULT_JWKS_THROTTLE_MAX_REFRESHES,
    ) -> None:
        self.issuer = issuer.strip()
        self.audience = audience.strip()
        self.jwks_uri = jwks_uri.strip()
        self.jwks_cache_ttl_seconds = max(10, jwks_cache_ttl_seconds)
        self.http_timeout_seconds = max(1.0, http_timeout_seconds)
        self._cached_jwks: dict[str, jwt.PyJWK] = {}
        self._cached_at_monotonic: float = 0.0

        # Throttle state for forced JWKS refreshes
        self._jwks_min_refresh_interval = max(1.0, jwks_min_refresh_interval_seconds)
        self._jwks_throttle_window = max(10.0, jwks_throttle_window_seconds)
        self._jwks_throttle_max = max(1, jwks_throttle_max_refreshes)
        self._last_forced_refresh_monotonic: float = 0.0
        self._forced_refresh_timestamps: list[float] = []
        self._refresh_lock = threading.Lock()

        # Telemetry counters
        self.jwks_refresh_total: int = 0
        self.jwks_refresh_forced: int = 0
        self.jwks_refresh_throttled: int = 0

    def _jwks_stale(self) -> bool:
        if not self._cached_jwks:
            return True
        return (time.monotonic() - self._cached_at_monotonic) >= self.jwks_cache_ttl_seconds

    def _is_forced_refresh_allowed(self) -> bool:
        """Check whether a forced JWKS refresh is allowed by throttle policy.

        Returns True if the minimum interval has elapsed since the last forced
        refresh AND the sliding-window limit has not been reached.
        """
        now = time.monotonic()
        # Minimum interval check
        if (now - self._last_forced_refresh_monotonic) < self._jwks_min_refresh_interval:
            return False
        # Sliding window check — prune old timestamps first
        cutoff = now - self._jwks_throttle_window
        self._forced_refresh_timestamps = [
            ts for ts in self._forced_refresh_timestamps if ts > cutoff
        ]
        if len(self._forced_refresh_timestamps) >= self._jwks_throttle_max:
            return False
        return True

    def _record_forced_refresh(self) -> None:
        now = time.monotonic()
        self._last_forced_refresh_monotonic = now
        self._forced_refresh_timestamps.append(now)
        self.jwks_refresh_forced += 1

    def _refresh_jwks(self, *, forced: bool = False) -> bool:
        """Refresh cached JWKS keys.

        When ``forced`` is True the throttle policy is checked first.
        Returns True if a refresh was actually performed, False if throttled.
        """
        with self._refresh_lock:
            if forced:
                if not self._is_forced_refresh_allowed():
                    self.jwks_refresh_throttled += 1
                    logger.warning(
                        "JWKS forced refresh throttled (interval=%.1fs, window=%ds, max=%d, "
                        "recent=%d)",
                        self._jwks_min_refresh_interval,
                        int(self._jwks_throttle_window),
                        self._jwks_throttle_max,
                        len(self._forced_refresh_timestamps),
                    )
                    return False
                self._record_forced_refresh()

            try:
                payload = _read_uri_json(self.jwks_uri, timeout_seconds=self.http_timeout_seconds)
            except (httpx.HTTPError, OSError, ValueError) as exc:
                raise OIDCValidationError(f"OIDC JWKS retrieval failed: {exc}") from exc
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
            self.jwks_refresh_total += 1
            logger.info(
                "JWKS refreshed (forced=%s, total=%d, forced_count=%d, throttled=%d)",
                forced,
                self.jwks_refresh_total,
                self.jwks_refresh_forced,
                self.jwks_refresh_throttled,
            )
            return True

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
        # This is a forced refresh subject to throttle policy.
        refreshed = self._refresh_jwks(forced=True)
        if refreshed and kid and kid in self._cached_jwks:
            return algorithm, self._cached_jwks[kid]

        if not kid and len(self._cached_jwks) == 1:
            only_key = next(iter(self._cached_jwks.values()))
            return algorithm, only_key

        raise OIDCValidationError("JWT kid was not found in configured JWKS.")

    def _claims_match_audience(self, claims: dict[str, Any]) -> bool:
        """Support both standard `aud` and Cognito access-token `client_id`."""
        aud_claim = claims.get("aud")
        aud_values: list[str] = []
        if isinstance(aud_claim, str):
            text = aud_claim.strip()
            if text:
                aud_values.append(text)
        elif isinstance(aud_claim, list):
            for item in aud_claim:
                text = str(item).strip()
                if text:
                    aud_values.append(text)

        if aud_values:
            return self.audience in aud_values

        client_id = str(claims.get("client_id") or "").strip()
        if client_id:
            return client_id == self.audience
        return False

    def verify_access_token(self, token: str) -> OIDCIdentity:
        algorithm, signing_key = self._resolve_signing_key(token)
        try:
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                issuer=self.issuer,
                options={
                    "require": ["sub", "iss", "exp"],
                    "verify_aud": False,
                },
            )
        except jwt.InvalidSignatureError:
            # Support key rotation where an issuer reuses the same kid for a new key.
            # Forced refresh is subject to throttle policy to prevent refresh storms.
            refreshed = self._refresh_jwks(forced=True)
            if refreshed:
                try:
                    algorithm, signing_key = self._resolve_signing_key(token)
                    claims = jwt.decode(
                        token,
                        signing_key.key,
                        algorithms=[algorithm],
                        audience=self.audience,
                        issuer=self.issuer,
                        options={"require": ["sub", "iss", "aud", "exp"]},
                    )
                except jwt.InvalidSignatureError as exc:
                    # Key rotation confirmed: new JWKS loaded but token still fails
                    raise OIDCKeyRotationError(
                        "Signing keys have changed. Please sign in again to get a new token."
                    ) from exc
                except jwt.PyJWTError as exc:
                    raise OIDCValidationError(f"OIDC JWT validation failed: {exc}") from exc
            else:
                raise OIDCKeyRotationError(
                    "OIDC JWT signature verification failed. "
                    "JWKS refresh was throttled — please sign in again."
                )
        except jwt.PyJWTError as exc:
            raise OIDCValidationError(f"OIDC JWT validation failed: {exc}") from exc
        if not isinstance(claims, dict):
            raise OIDCValidationError("OIDC JWT claims payload must be an object.")
        if not self._claims_match_audience(claims):
            raise OIDCValidationError(
                "OIDC JWT validation failed: token audience/client_id does not match expected audience."
            )
        subject = str(claims.get("sub") or "").strip()
        if not subject:
            raise OIDCValidationError("OIDC JWT is missing required subject claim.")
        return OIDCIdentity(subject=subject, claims=claims)

    @property
    def jwks_refresh_stats(self) -> dict[str, int]:
        """Return telemetry counters for JWKS refresh activity."""
        return {
            "total": self.jwks_refresh_total,
            "forced": self.jwks_refresh_forced,
            "throttled": self.jwks_refresh_throttled,
        }


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
