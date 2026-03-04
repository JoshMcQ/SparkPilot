from __future__ import annotations

from typing import Any

from airflow.providers.sparkpilot._compat import (
    AirflowException,
    AirflowFailException,
    BaseSensorOperator,
    PokeReturnValue,
)
from airflow.providers.sparkpilot.common import (
    FAILURE_STATES,
    SUCCESS_STATES,
    SparkPilotPermanentError,
    SparkPilotTransientError,
    build_run_metadata,
)
from airflow.providers.sparkpilot.hooks.sparkpilot import SparkPilotHook


class SparkPilotRunSensor(BaseSensorOperator):
    template_fields = ("run_id", "sparkpilot_conn_id")

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
        hook: SparkPilotHook | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.run_id = run_id
        self.sparkpilot_conn_id = sparkpilot_conn_id
        self.base_url = base_url
        self.oidc_issuer = oidc_issuer
        self.oidc_audience = oidc_audience
        self.oidc_client_id = oidc_client_id
        self.oidc_client_secret = oidc_client_secret
        self.oidc_token_endpoint = oidc_token_endpoint
        self.oidc_scope = oidc_scope
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

    def poke(self, context: dict[str, Any]) -> bool | PokeReturnValue:  # noqa: ARG002
        hook = self.get_hook()
        try:
            run = hook.get_run(self.run_id)
        except SparkPilotTransientError as exc:
            raise AirflowException(str(exc)) from exc
        except SparkPilotPermanentError as exc:
            raise AirflowFailException(str(exc)) from exc

        state = str(run.get("state") or "").lower()
        if state in SUCCESS_STATES:
            return PokeReturnValue(is_done=True, xcom_value=build_run_metadata(run))
        if state in FAILURE_STATES:
            raise AirflowFailException(
                f"Run {self.run_id} reached terminal failure state '{state}'. "
                f"{run.get('error_message') or ''}".strip()
            )
        return False
