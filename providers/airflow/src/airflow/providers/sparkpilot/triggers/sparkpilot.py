from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from airflow.providers.sparkpilot._compat import BaseTrigger, TriggerEvent
from airflow.providers.sparkpilot.common import (
    FAILURE_STATES,
    SUCCESS_STATES,
    SparkPilotPermanentError,
    build_run_metadata,
    error_detail_from_json,
    is_transient_status_code,
)
from airflow.providers.sparkpilot.hooks.sparkpilot import SparkPilotHook


class SparkPilotTriggerTransientError(RuntimeError):
    """Transient trigger transport/status error."""


class SparkPilotRunTrigger(BaseTrigger):
    def __init__(
        self,
        *,
        run_id: str,
        sparkpilot_conn_id: str = "sparkpilot_default",
        base_url: str | None = None,
        oidc_issuer: str | None = None,
        oidc_audience: str | None = None,
        oidc_client_id: str | None = None,
        oidc_client_secret: str | None = None,
        oidc_token_endpoint: str | None = None,
        oidc_scope: str | None = None,
        poll_interval_seconds: int = 15,
        timeout_seconds: int = 3600,
        max_transient_failures: int = 20,
        max_backoff_seconds: int = 60,
    ) -> None:
        super().__init__()
        self.run_id = run_id
        self.sparkpilot_conn_id = sparkpilot_conn_id
        self.base_url = base_url
        self.oidc_issuer = oidc_issuer
        self.oidc_audience = oidc_audience
        self.oidc_client_id = oidc_client_id
        self.oidc_client_secret = oidc_client_secret
        self.oidc_token_endpoint = oidc_token_endpoint
        self.oidc_scope = oidc_scope
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than 0.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0.")
        if max_transient_failures < 0:
            raise ValueError("max_transient_failures must be >= 0.")
        if max_backoff_seconds <= 0:
            raise ValueError("max_backoff_seconds must be greater than 0.")
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.max_transient_failures = max_transient_failures
        self.max_backoff_seconds = max_backoff_seconds

    def serialize(self) -> tuple[str, dict[str, Any]]:
        return (
            "airflow.providers.sparkpilot.triggers.sparkpilot.SparkPilotRunTrigger",
            {
                "run_id": self.run_id,
                "sparkpilot_conn_id": self.sparkpilot_conn_id,
                "base_url": self.base_url,
                "oidc_issuer": self.oidc_issuer,
                "oidc_audience": self.oidc_audience,
                "oidc_client_id": self.oidc_client_id,
                "oidc_client_secret": self.oidc_client_secret,
                "oidc_token_endpoint": self.oidc_token_endpoint,
                "oidc_scope": self.oidc_scope,
                "poll_interval_seconds": self.poll_interval_seconds,
                "timeout_seconds": self.timeout_seconds,
                "max_transient_failures": self.max_transient_failures,
                "max_backoff_seconds": self.max_backoff_seconds,
            },
        )

    async def _fetch_run(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        response = await client.get(
            f"{base_url}/v1/runs/{self.run_id}",
            headers=headers,
        )
        if response.status_code >= 400:
            try:
                detail = error_detail_from_json(response.json())
            except ValueError:
                detail = response.text.strip() if response.text else "Unknown error"
            message = (
                f"SparkPilot API request failed: GET /v1/runs/{self.run_id} "
                f"returned {response.status_code}. Detail: {detail}"
            )
            if is_transient_status_code(response.status_code):
                raise SparkPilotTriggerTransientError(message)
            raise SparkPilotPermanentError(message)
        try:
            payload = response.json()
        except ValueError as exc:
            raise SparkPilotPermanentError(
                f"SparkPilot API returned invalid JSON while fetching run {self.run_id}."
            ) from exc
        if not isinstance(payload, dict):
            raise SparkPilotPermanentError(
                f"SparkPilot API returned unexpected JSON type while fetching run {self.run_id}: "
                f"{type(payload).__name__}"
            )
        return payload

    def _create_async_client(self, *, timeout_seconds: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout_seconds)

    async def run(self):  # noqa: ANN201
        hook = SparkPilotHook(
            sparkpilot_conn_id=self.sparkpilot_conn_id,
            base_url=self.base_url,
            oidc_issuer=self.oidc_issuer,
            oidc_audience=self.oidc_audience,
            oidc_client_id=self.oidc_client_id,
            oidc_client_secret=self.oidc_client_secret,
            oidc_token_endpoint=self.oidc_token_endpoint,
            oidc_scope=self.oidc_scope,
        )
        resolved = hook.resolve_connection()
        deadline = time.monotonic() + self.timeout_seconds
        consecutive_transient_failures = 0
        async with self._create_async_client(timeout_seconds=hook.timeout_seconds) as client:
            while True:
                try:
                    headers = hook.build_headers(hook.get_access_token(force_refresh=False))
                    run = await self._fetch_run(
                        client=client,
                        base_url=resolved.base_url,
                        headers=headers,
                    )
                    consecutive_transient_failures = 0
                except SparkPilotPermanentError as exc:
                    yield TriggerEvent(
                        {
                            "status": "failed",
                            "transient": False,
                            "message": str(exc),
                        }
                    )
                    return
                except (SparkPilotTriggerTransientError, httpx.RequestError) as exc:
                    consecutive_transient_failures += 1
                    if consecutive_transient_failures > self.max_transient_failures:
                        yield TriggerEvent(
                            {
                                "status": "error",
                                "transient": True,
                                "message": (
                                    f"Exceeded max transient failures ({self.max_transient_failures}) "
                                    f"while waiting for run {self.run_id}: {exc}"
                                ),
                            }
                        )
                        return
                    if time.monotonic() >= deadline:
                        yield TriggerEvent(
                            {
                                "status": "error",
                                "transient": True,
                                "message": f"Timed out waiting for run {self.run_id}: {exc}",
                            }
                        )
                        return
                    backoff_factor = 2 ** min(consecutive_transient_failures - 1, 4)
                    delay_seconds = min(
                        self.max_backoff_seconds,
                        max(1, self.poll_interval_seconds) * backoff_factor,
                    )
                    await asyncio.sleep(delay_seconds)
                    continue

                state = str(run.get("state") or "").lower()
                metadata = build_run_metadata(run)
                if state in SUCCESS_STATES:
                    yield TriggerEvent(
                        {
                            "status": "success",
                            "transient": False,
                            "run": run,
                            "metadata": metadata,
                        }
                    )
                    return
                if state in FAILURE_STATES:
                    yield TriggerEvent(
                        {
                            "status": "failed",
                            "transient": False,
                            "run": run,
                            "metadata": metadata,
                            "message": (
                                f"Run {self.run_id} reached terminal failure state '{state}'. "
                                f"{run.get('error_message') or ''}".strip()
                            ),
                        }
                    )
                    return
                if time.monotonic() >= deadline:
                    yield TriggerEvent(
                        {
                            "status": "error",
                            "transient": True,
                            "run": run,
                            "metadata": metadata,
                            "message": f"Timed out waiting for run {self.run_id} terminal state.",
                        }
                    )
                    return
                await asyncio.sleep(max(1, self.poll_interval_seconds))
