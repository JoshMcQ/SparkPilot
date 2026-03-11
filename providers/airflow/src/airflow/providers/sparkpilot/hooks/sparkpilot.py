from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from airflow.providers.sparkpilot._compat import AirflowException, BaseHook
from airflow.providers.sparkpilot.common import (
    FAILURE_STATES,
    SUCCESS_STATES,
    TERMINAL_STATES,
    SparkPilotPermanentError,
    SparkPilotTransientError,
    error_detail_from_json,
    is_transient_status_code,
)


@dataclass(frozen=True)
class _ResolvedOIDCConnection:
    base_url: str
    issuer: str
    audience: str
    client_id: str
    client_secret: str
    token_endpoint: str | None
    scope: str | None


class SparkPilotHook(BaseHook):
    conn_name_attr = "sparkpilot_conn_id"
    default_conn_name = "sparkpilot_default"
    conn_type = "sparkpilot"
    hook_name = "SparkPilot"

    def __init__(
        self,
        *,
        sparkpilot_conn_id: str = "sparkpilot_default",
        base_url: str | None = None,
        oidc_issuer: str | None = None,
        oidc_audience: str | None = None,
        oidc_client_id: str | None = None,
        oidc_client_secret: str | None = None,
        oidc_token_endpoint: str | None = None,
        oidc_scope: str | None = None,
        timeout_seconds: float = 30.0,
        request_retries: int = 2,
        request_backoff_seconds: float = 1.0,
    ) -> None:
        super().__init__()
        self.sparkpilot_conn_id = sparkpilot_conn_id
        self.base_url = base_url
        self.oidc_issuer = oidc_issuer
        self.oidc_audience = oidc_audience
        self.oidc_client_id = oidc_client_id
        self.oidc_client_secret = oidc_client_secret
        self.oidc_token_endpoint = oidc_token_endpoint
        self.oidc_scope = oidc_scope
        self.timeout_seconds = timeout_seconds
        self.request_retries = max(0, request_retries)
        self.request_backoff_seconds = max(0.0, request_backoff_seconds)
        self._cached_access_token: str | None = None
        self._cached_access_token_expiry: float = 0.0

    @staticmethod
    def _env(*names: str) -> str | None:
        for name in names:
            value = os.getenv(name)
            if value:
                return value
        return None

    def resolve_connection(self) -> _ResolvedOIDCConnection:
        conn = self.get_connection(self.sparkpilot_conn_id)
        extras = dict(getattr(conn, "extra_dejson", {}) or {})

        base_url = self.base_url or (
            extras.get("sparkpilot_url")
            or extras.get("base_url")
            or extras.get("url")
        )
        if not base_url:
            host = getattr(conn, "host", None)
            if host:
                scheme = getattr(conn, "schema", None) or extras.get("scheme") or "http"
                port = getattr(conn, "port", None)
                base_url = f"{scheme}://{host}{f':{port}' if port else ''}"
        if not base_url:
            raise AirflowException(
                "SparkPilot connection is missing base URL. "
                "Set extras.sparkpilot_url or host/schema/port."
            )

        issuer = (
            self.oidc_issuer
            or extras.get("oidc_issuer")
            or self._env("OIDC_ISSUER", "SPARKPILOT_OIDC_ISSUER")
            or ""
        )
        audience = (
            self.oidc_audience
            or extras.get("oidc_audience")
            or self._env("OIDC_AUDIENCE", "SPARKPILOT_OIDC_AUDIENCE")
            or ""
        )
        client_id = (
            self.oidc_client_id
            or getattr(conn, "login", None)
            or extras.get("oidc_client_id")
            or self._env("OIDC_CLIENT_ID", "SPARKPILOT_OIDC_CLIENT_ID")
            or ""
        )
        client_secret = (
            self.oidc_client_secret
            or getattr(conn, "password", None)
            or extras.get("oidc_client_secret")
            or self._env("OIDC_CLIENT_SECRET", "SPARKPILOT_OIDC_CLIENT_SECRET")
            or ""
        )
        token_endpoint = (
            self.oidc_token_endpoint
            or extras.get("oidc_token_endpoint")
            or self._env("OIDC_TOKEN_ENDPOINT", "SPARKPILOT_OIDC_TOKEN_ENDPOINT")
            or ""
        )
        scope = (
            self.oidc_scope
            or extras.get("oidc_scope")
            or self._env("OIDC_SCOPE", "SPARKPILOT_OIDC_SCOPE")
            or ""
        )

        missing: list[str] = []
        if not issuer:
            missing.append("oidc_issuer")
        if not audience:
            missing.append("oidc_audience")
        if not client_id:
            missing.append("oidc_client_id")
        if not client_secret:
            missing.append("oidc_client_secret")
        if missing:
            raise AirflowException(
                "SparkPilot connection is missing required OIDC fields: " + ", ".join(missing)
            )

        return _ResolvedOIDCConnection(
            base_url=str(base_url).rstrip("/"),
            issuer=str(issuer).strip(),
            audience=str(audience).strip(),
            client_id=str(client_id).strip(),
            client_secret=str(client_secret).strip(),
            token_endpoint=str(token_endpoint).strip() or None,
            scope=str(scope).strip() or None,
        )

    @staticmethod
    def build_headers(access_token: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        }

    # Backward-compatible private aliases retained for callers that imported internals.
    def _resolve_connection(self) -> _ResolvedOIDCConnection:
        return self.resolve_connection()

    @staticmethod
    def _default_headers(access_token: str) -> dict[str, str]:
        return SparkPilotHook.build_headers(access_token)

    def _discover_token_endpoint(self, issuer: str) -> str:
        metadata_url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
        response = httpx.get(metadata_url, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise SparkPilotPermanentError("OIDC discovery response must be a JSON object.")
        token_endpoint = str(payload.get("token_endpoint") or "").strip()
        if not token_endpoint:
            raise SparkPilotPermanentError("OIDC discovery did not return token_endpoint.")
        return token_endpoint

    def _get_access_token(self, resolved: _ResolvedOIDCConnection, *, force_refresh: bool = False) -> str:
        now = time.time()
        if (
            not force_refresh
            and self._cached_access_token
            and self._cached_access_token_expiry > now + 30
        ):
            return self._cached_access_token

        token_endpoint = resolved.token_endpoint or self._discover_token_endpoint(resolved.issuer)
        body: dict[str, str] = {
            "grant_type": "client_credentials",
            "audience": resolved.audience,
        }
        if resolved.scope:
            body["scope"] = resolved.scope
        response = httpx.post(
            token_endpoint,
            data=body,
            auth=(resolved.client_id, resolved.client_secret),
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise SparkPilotPermanentError("OIDC token response must be a JSON object.")
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise SparkPilotPermanentError("OIDC token response missing access_token.")
        expires_in = int(payload.get("expires_in") or 300)
        self._cached_access_token = token
        self._cached_access_token_expiry = now + max(30, expires_in)
        return token

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        resolved = self.resolve_connection()
        return self._get_access_token(resolved, force_refresh=force_refresh)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        resolved = self.resolve_connection()
        url = f"{resolved.base_url}{path}"
        max_attempts = self.request_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                access_token = self._get_access_token(resolved, force_refresh=False)
                headers = self.build_headers(access_token)
                if extra_headers:
                    headers.update(extra_headers)
                response = httpx.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_body,
                    params=params,
                    timeout=self.timeout_seconds,
                )
            except httpx.RequestError as exc:
                if attempt >= max_attempts:
                    raise SparkPilotTransientError(f"SparkPilot request transport failure: {exc}") from exc
                delay = max(1.0, self.request_backoff_seconds * attempt)
                self.log.warning(
                    "Transient SparkPilot transport error for %s %s (attempt %s/%s); retrying in %.1fs: %s",
                    method.upper(),
                    path,
                    attempt,
                    max_attempts,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue

            if response.status_code == 401 and attempt < max_attempts:
                # Access token may be expired/revoked; refresh once and retry.
                try:
                    self._get_access_token(resolved, force_refresh=True)
                except httpx.HTTPError:
                    pass
                delay = max(1.0, self.request_backoff_seconds * attempt)
                time.sleep(delay)
                continue

            if response.status_code >= 400:
                detail = "Unknown error"
                try:
                    detail = error_detail_from_json(response.json())
                except ValueError:
                    if response.text:
                        detail = response.text.strip()
                message = (
                    f"SparkPilot API request failed: {method.upper()} {path} "
                    f"returned {response.status_code}. Detail: {detail}"
                )
                if is_transient_status_code(response.status_code):
                    if attempt >= max_attempts:
                        raise SparkPilotTransientError(message)
                    delay = max(1.0, self.request_backoff_seconds * attempt)
                    self.log.warning(
                        "Transient SparkPilot status for %s %s (attempt %s/%s); retrying in %.1fs: %s",
                        method.upper(),
                        path,
                        attempt,
                        max_attempts,
                        delay,
                        message,
                    )
                    time.sleep(delay)
                    continue
                raise SparkPilotPermanentError(message)

            if not response.content:
                return {}
            try:
                payload = response.json()
            except ValueError:
                return {}
            if not isinstance(payload, dict):
                raise SparkPilotPermanentError(
                    f"SparkPilot API returned unexpected JSON type for {method.upper()} {path}: "
                    f"{type(payload).__name__}"
                )
            return payload

        raise SparkPilotTransientError(
            f"SparkPilot API request exhausted retries for {method.upper()} {path}."
        )

    def submit_run(
        self,
        *,
        job_id: str,
        run_payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body = run_payload or {}
        key = idempotency_key or f"airflow-{uuid4()}"
        return self._request(
            "POST",
            f"/v1/jobs/{job_id}/runs",
            json_body=body,
            extra_headers={"Idempotency-Key": key},
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/runs/{run_id}")

    def cancel_run(
        self,
        *,
        run_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Request cancellation of a SparkPilot run.

        Returns the updated run payload with ``cancellation_requested=True``
        (or already in a terminal state).
        """
        key = idempotency_key or f"airflow-cancel-{uuid4()}"
        return self._request(
            "POST",
            f"/v1/runs/{run_id}/cancel",
            extra_headers={"Idempotency-Key": key},
        )

    def wait_for_terminal_state(
        self,
        *,
        run_id: str,
        poll_interval_seconds: int = 15,
        timeout_seconds: int = 3600,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                run = self.get_run(run_id)
            except SparkPilotTransientError as exc:
                if time.monotonic() >= deadline:
                    raise
                self.log.warning(
                    "Transient SparkPilot error while polling run '%s'; retrying in %ss: %s",
                    run_id,
                    max(1, poll_interval_seconds),
                    exc,
                )
                time.sleep(max(1, poll_interval_seconds))
                continue

            state = str(run.get("state") or "").lower()
            if state in SUCCESS_STATES:
                return run
            if state in FAILURE_STATES:
                message = run.get("error_message") or "Run failed."
                raise SparkPilotPermanentError(
                    f"Run {run_id} reached terminal failure state '{state}': {message}"
                )
            if state in TERMINAL_STATES and state not in SUCCESS_STATES:
                raise SparkPilotPermanentError(
                    f"Run {run_id} reached unsupported terminal state '{state}'."
                )
            if time.monotonic() >= deadline:
                raise SparkPilotTransientError(
                    f"Timed out waiting for run {run_id} to reach terminal state."
                )
            time.sleep(max(1, poll_interval_seconds))
