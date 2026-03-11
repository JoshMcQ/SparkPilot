from __future__ import annotations

from typing import Any

from airflow.providers.sparkpilot._compat import AirflowException, AirflowFailException, BaseOperator
from airflow.providers.sparkpilot.common import (
    TERMINAL_STATES,
    SparkPilotPermanentError,
    SparkPilotTransientError,
    build_run_metadata,
)
from airflow.providers.sparkpilot.hooks.sparkpilot import SparkPilotHook
from airflow.providers.sparkpilot.triggers.sparkpilot import SparkPilotRunTrigger


class SparkPilotSubmitRunOperator(BaseOperator):
    template_fields = ("job_id", "sparkpilot_conn_id", "golden_path", "idempotency_key")

    def __init__(
        self,
        *,
        job_id: str,
        sparkpilot_conn_id: str = "sparkpilot_default",
        base_url: str | None = None,
        oidc_issuer: str | None = None,
        oidc_audience: str | None = None,
        oidc_client_id: str | None = None,
        oidc_client_secret: str | None = None,
        oidc_token_endpoint: str | None = None,
        oidc_scope: str | None = None,
        golden_path: str | None = None,
        args: list[str] | None = None,
        spark_conf: dict[str, str] | None = None,
        requested_resources: dict[str, int] | None = None,
        timeout_seconds: int | None = None,
        run_timeout_seconds: int | None = None,
        wait_timeout_seconds: int | None = None,
        idempotency_key: str | None = None,
        poll_interval_seconds: int = 15,
        wait_for_completion: bool = True,
        deferrable: bool = False,
        hook: SparkPilotHook | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.job_id = job_id
        self.sparkpilot_conn_id = sparkpilot_conn_id
        self.base_url = base_url
        self.oidc_issuer = oidc_issuer
        self.oidc_audience = oidc_audience
        self.oidc_client_id = oidc_client_id
        self.oidc_client_secret = oidc_client_secret
        self.oidc_token_endpoint = oidc_token_endpoint
        self.oidc_scope = oidc_scope
        self.golden_path = golden_path
        self.args = args
        self.spark_conf = spark_conf
        self.requested_resources = requested_resources
        self.run_timeout_seconds = run_timeout_seconds
        # `timeout_seconds` is retained as a backwards-compatible alias for wait timeout.
        if wait_timeout_seconds is None and timeout_seconds is not None:
            wait_timeout_seconds = timeout_seconds
        if self.run_timeout_seconds is not None and self.run_timeout_seconds <= 0:
            raise ValueError("run_timeout_seconds must be greater than 0.")
        if wait_timeout_seconds is not None and wait_timeout_seconds <= 0:
            raise ValueError("wait_timeout_seconds must be greater than 0.")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than 0.")
        self.wait_timeout_seconds = wait_timeout_seconds or 3600
        self.idempotency_key = idempotency_key
        self.poll_interval_seconds = poll_interval_seconds
        self.wait_for_completion = wait_for_completion
        self.deferrable = deferrable
        self._hook = hook

    def get_hook(self) -> SparkPilotHook:
        if self._hook is not None:
            return self._hook
        return SparkPilotHook(
            sparkpilot_conn_id=self.sparkpilot_conn_id,
            base_url=self.base_url,
            oidc_issuer=self.oidc_issuer,
            oidc_audience=self.oidc_audience,
            oidc_client_id=self.oidc_client_id,
            oidc_client_secret=self.oidc_client_secret,
            oidc_token_endpoint=self.oidc_token_endpoint,
            oidc_scope=self.oidc_scope,
        )

    def _build_run_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.golden_path:
            payload["golden_path"] = self.golden_path
        if self.args is not None:
            payload["args"] = self.args
        if self.spark_conf is not None:
            payload["spark_conf"] = self.spark_conf
        if self.requested_resources is not None:
            payload["requested_resources"] = self.requested_resources
        if self.run_timeout_seconds is not None:
            payload["timeout_seconds"] = self.run_timeout_seconds
        return payload

    def execute(self, context: dict[str, Any]) -> dict[str, Any] | None:  # noqa: ARG002
        hook = self.get_hook()
        try:
            submitted = hook.submit_run(
                job_id=self.job_id,
                run_payload=self._build_run_payload(),
                idempotency_key=self.idempotency_key,
            )
        except SparkPilotTransientError as exc:
            raise AirflowException(str(exc)) from exc
        except SparkPilotPermanentError as exc:
            raise AirflowFailException(str(exc)) from exc

        run_id = str(submitted.get("id") or "").strip()
        if not run_id:
            raise AirflowFailException("SparkPilot submit response did not contain run id.")

        if self.deferrable:
            self.defer(
                trigger=SparkPilotRunTrigger(
                    run_id=run_id,
                    sparkpilot_conn_id=self.sparkpilot_conn_id,
                    base_url=self.base_url,
                    oidc_issuer=self.oidc_issuer,
                    oidc_audience=self.oidc_audience,
                    oidc_client_id=self.oidc_client_id,
                    oidc_client_secret=self.oidc_client_secret,
                    oidc_token_endpoint=self.oidc_token_endpoint,
                    oidc_scope=self.oidc_scope,
                    poll_interval_seconds=self.poll_interval_seconds,
                    timeout_seconds=self.wait_timeout_seconds,
                ),
                method_name="execute_complete",
            )
            return None

        if not self.wait_for_completion:
            return build_run_metadata(submitted)

        try:
            terminal = hook.wait_for_terminal_state(
                run_id=run_id,
                poll_interval_seconds=self.poll_interval_seconds,
                timeout_seconds=self.wait_timeout_seconds,
            )
        except SparkPilotTransientError as exc:
            raise AirflowException(str(exc)) from exc
        except SparkPilotPermanentError as exc:
            raise AirflowFailException(str(exc)) from exc
        return build_run_metadata(terminal)

    def execute_complete(self, context: dict[str, Any], event: dict[str, Any] | None = None) -> dict[str, Any]:
        # Trigger contract:
        # - status=success for successful terminal completion
        # - status in {failed,error} for non-success completion
        # - transient=True only for retryable/non-terminal transport conditions
        if event is None:
            raise AirflowException("SparkPilot deferrable trigger completed without event payload.")
        status = str(event.get("status") or "").lower()
        if status == "success":
            metadata = event.get("metadata")
            if isinstance(metadata, dict):
                return metadata
            run = event.get("run")
            if isinstance(run, dict):
                return build_run_metadata(run)
            raise AirflowException("SparkPilot trigger success event did not include run metadata.")
        message = str(event.get("message") or "SparkPilot trigger reported failure.")
        is_transient = bool(event.get("transient", False))
        if is_transient:
            raise AirflowException(message)
        raise AirflowFailException(message)


class SparkPilotCancelRunOperator(BaseOperator):
    """Cancel a SparkPilot run.

    If the run is already in a terminal state the operator succeeds silently.
    When ``wait_for_completion`` is True (default) the operator polls until
    the run reaches a terminal state after requesting cancellation.
    """

    template_fields = ("run_id", "sparkpilot_conn_id", "idempotency_key")

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
        idempotency_key: str | None = None,
        wait_for_completion: bool = True,
        poll_interval_seconds: int = 10,
        timeout_seconds: int = 600,
        hook: SparkPilotHook | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.run_id = run_id
        if not self.run_id.strip():
            raise ValueError("run_id is required.")
        self.sparkpilot_conn_id = sparkpilot_conn_id
        self.base_url = base_url
        self.oidc_issuer = oidc_issuer
        self.oidc_audience = oidc_audience
        self.oidc_client_id = oidc_client_id
        self.oidc_client_secret = oidc_client_secret
        self.oidc_token_endpoint = oidc_token_endpoint
        self.oidc_scope = oidc_scope
        self.idempotency_key = idempotency_key
        self.wait_for_completion = wait_for_completion
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than 0.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0.")
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds
        self._hook = hook

    def get_hook(self) -> SparkPilotHook:
        if self._hook is not None:
            return self._hook
        return SparkPilotHook(
            sparkpilot_conn_id=self.sparkpilot_conn_id,
            base_url=self.base_url,
            oidc_issuer=self.oidc_issuer,
            oidc_audience=self.oidc_audience,
            oidc_client_id=self.oidc_client_id,
            oidc_client_secret=self.oidc_client_secret,
            oidc_token_endpoint=self.oidc_token_endpoint,
            oidc_scope=self.oidc_scope,
        )

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        hook = self.get_hook()
        try:
            result = hook.cancel_run(
                run_id=self.run_id,
                idempotency_key=self.idempotency_key,
            )
        except SparkPilotTransientError as exc:
            raise AirflowException(str(exc)) from exc
        except SparkPilotPermanentError as exc:
            raise AirflowFailException(str(exc)) from exc

        state = str(result.get("state") or "").lower()
        if state in TERMINAL_STATES:
            return build_run_metadata(result)

        if not self.wait_for_completion:
            return build_run_metadata(result)

        try:
            terminal = hook.wait_for_terminal_state(
                run_id=self.run_id,
                poll_interval_seconds=self.poll_interval_seconds,
                timeout_seconds=self.timeout_seconds,
            )
        except SparkPilotTransientError as exc:
            raise AirflowException(str(exc)) from exc
        except SparkPilotPermanentError as exc:
            raise AirflowFailException(str(exc)) from exc
        return build_run_metadata(terminal)
