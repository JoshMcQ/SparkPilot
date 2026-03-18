from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import time
from typing import Any
from uuid import uuid4

import httpx

from dagster_sparkpilot.common import FAILURE_STATES, SUCCESS_STATES, TERMINAL_STATES, error_detail_from_json
from dagster_sparkpilot.errors import (
    SparkPilotPermanentError,
    SparkPilotRunFailedError,
    SparkPilotTransientError,
    is_transient_status_code,
)


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"SparkPilot client config field '{key}' must be a non-empty string.")
    return value.strip()


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"SparkPilot client config field '{key}' must be a string when provided.")
    candidate = value.strip()
    return candidate or None


def _optional_positive_int(payload: Mapping[str, Any], key: str, default_value: int) -> int:
    value = payload.get(key, default_value)
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"SparkPilot client config field '{key}' must be an integer >= 0.")
    return value


def _optional_positive_float(payload: Mapping[str, Any], key: str, default_value: float) -> float:
    value = payload.get(key, default_value)
    if not isinstance(value, int | float) or float(value) < 0:
        raise ValueError(f"SparkPilot client config field '{key}' must be a number >= 0.")
    return float(value)


@dataclass(frozen=True)
class SparkPilotClientConfig:
    base_url: str
    oidc_issuer: str
    oidc_audience: str
    oidc_client_id: str
    oidc_client_secret: str
    oidc_token_endpoint: str | None = None
    oidc_scope: str | None = None
    timeout_seconds: float = 30.0
    request_retries: int = 2
    request_backoff_seconds: float = 1.0

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SparkPilotClientConfig":
        if not isinstance(payload, Mapping):
            raise ValueError("SparkPilot client config must be a mapping.")
        base_url = _required_string(payload, "base_url").rstrip("/")
        if base_url.startswith("http://") is False and base_url.startswith("https://") is False:
            raise ValueError("SparkPilot client config field 'base_url' must start with http:// or https://.")
        timeout_seconds = _optional_positive_float(payload, "timeout_seconds", 30.0)
        if timeout_seconds <= 0:
            raise ValueError("SparkPilot client config field 'timeout_seconds' must be > 0.")
        request_retries = _optional_positive_int(payload, "request_retries", 2)
        request_backoff_seconds = _optional_positive_float(payload, "request_backoff_seconds", 1.0)
        return cls(
            base_url=base_url,
            oidc_issuer=_required_string(payload, "oidc_issuer"),
            oidc_audience=_required_string(payload, "oidc_audience"),
            oidc_client_id=_required_string(payload, "oidc_client_id"),
            oidc_client_secret=_required_string(payload, "oidc_client_secret"),
            oidc_token_endpoint=_optional_string(payload, "oidc_token_endpoint"),
            oidc_scope=_optional_string(payload, "oidc_scope"),
            timeout_seconds=timeout_seconds,
            request_retries=request_retries,
            request_backoff_seconds=request_backoff_seconds,
        )


class SparkPilotClient:
    def __init__(self, config: SparkPilotClientConfig) -> None:
        self.config = config
        self._cached_access_token: str | None = None
        self._cached_access_token_expiry: float = 0.0

    def _discover_token_endpoint(self) -> str:
        metadata_url = f"{self.config.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
        response = httpx.get(metadata_url, timeout=self.config.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise SparkPilotPermanentError("OIDC discovery response must be a JSON object.")
        token_endpoint = str(payload.get("token_endpoint") or "").strip()
        if not token_endpoint:
            raise SparkPilotPermanentError("OIDC discovery did not return token_endpoint.")
        return token_endpoint

    def _fetch_access_token(self, *, force_refresh: bool = False) -> str:
        now = time.time()
        if (
            not force_refresh
            and self._cached_access_token
            and self._cached_access_token_expiry > now + 30
        ):
            return self._cached_access_token

        token_endpoint = self.config.oidc_token_endpoint or self._discover_token_endpoint()
        body: dict[str, str] = {
            "grant_type": "client_credentials",
            "audience": self.config.oidc_audience,
        }
        if self.config.oidc_scope:
            body["scope"] = self.config.oidc_scope

        response = httpx.post(
            token_endpoint,
            data=body,
            auth=(self.config.oidc_client_id, self.config.oidc_client_secret),
            headers={"Accept": "application/json"},
            timeout=self.config.timeout_seconds,
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

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url}{path}"
        max_attempts = self.config.request_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                access_token = self._fetch_access_token(force_refresh=False)
                headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                }
                if extra_headers:
                    headers.update(extra_headers)
                response = httpx.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_body,
                    params=params,
                    timeout=self.config.timeout_seconds,
                )
            except httpx.RequestError as exc:
                if attempt >= max_attempts:
                    raise SparkPilotTransientError(
                        f"SparkPilot request transport failure for {method.upper()} {path}: {exc}"
                    ) from exc
                delay = max(1.0, self.config.request_backoff_seconds * attempt)
                time.sleep(delay)
                continue

            if response.status_code == 401 and attempt < max_attempts:
                self._fetch_access_token(force_refresh=True)
                delay = max(1.0, self.config.request_backoff_seconds * attempt)
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
                    f"SparkPilot API request failed: {method.upper()} {path} returned "
                    f"{response.status_code}. Detail: {detail}"
                )
                if is_transient_status_code(response.status_code):
                    if attempt >= max_attempts:
                        raise SparkPilotTransientError(message)
                    delay = max(1.0, self.config.request_backoff_seconds * attempt)
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
                    f"SparkPilot API returned unexpected JSON type for {method.upper()} "
                    f"{path}: {type(payload).__name__}"
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
        key = idempotency_key or f"dagster-{uuid4()}"
        return self._request_json(
            "POST",
            f"/v1/jobs/{job_id}/runs",
            json_body=body,
            extra_headers={"Idempotency-Key": key},
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/v1/runs/{run_id}")

    def cancel_run(
        self,
        *,
        run_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        key = idempotency_key or f"dagster-cancel-{uuid4()}"
        return self._request_json(
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
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be > 0.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0.")
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                run = self.get_run(run_id)
            except SparkPilotTransientError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(max(1, poll_interval_seconds))
                continue

            state = str(run.get("state") or "").lower()
            if state in SUCCESS_STATES:
                return run
            if state in FAILURE_STATES:
                message = run.get("error_message") or "Run failed."
                raise SparkPilotRunFailedError(
                    f"Run {run_id} reached terminal failure state '{state}': {message}"
                )
            if state in TERMINAL_STATES:
                raise SparkPilotPermanentError(
                    f"Run {run_id} reached unsupported terminal state '{state}'."
                )
            if time.monotonic() >= deadline:
                raise SparkPilotTransientError(
                    f"Timed out waiting for run {run_id} to reach terminal state."
                )
            time.sleep(max(1, poll_interval_seconds))

