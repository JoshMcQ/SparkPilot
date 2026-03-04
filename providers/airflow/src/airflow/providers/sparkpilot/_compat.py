from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

try:
    from airflow.exceptions import AirflowException, AirflowFailException
    from airflow.hooks.base import BaseHook
    from airflow.models.baseoperator import BaseOperator
    from airflow.sensors.base import BaseSensorOperator, PokeReturnValue
    from airflow.triggers.base import BaseTrigger, TriggerEvent
except Exception:  # noqa: BLE001

    class AirflowException(Exception):
        """Fallback AirflowException for local unit tests without Airflow."""

    class AirflowFailException(AirflowException):
        """Fallback AirflowFailException for local unit tests without Airflow."""

    @dataclass
    class _FallbackConnection:
        host: str | None = None
        schema: str | None = None
        port: int | None = None
        password: str | None = None
        extra_dejson: dict[str, Any] = field(default_factory=dict)

    class BaseHook:
        conn_name_attr = "sparkpilot_conn_id"
        default_conn_name = "sparkpilot_default"
        conn_type = "sparkpilot"
        hook_name = "SparkPilot"
        log = logging.getLogger("sparkpilot.airflow.hook")

        @classmethod
        def get_connection(cls, _conn_id: str) -> _FallbackConnection:
            raise AirflowException(
                "Apache Airflow is not installed and no fallback connection is configured."
            )

    class BaseOperator:
        template_fields: tuple[str, ...] = ()

        def __init__(self, **kwargs: Any) -> None:
            self.task_id = kwargs.get("task_id")
            self.log = logging.getLogger("sparkpilot.airflow.operator")

        def defer(
            self,
            *,
            timeout: int | None = None,
            trigger: Any = None,
            method_name: str = "execute_complete",
        ) -> None:
            raise AirflowException(
                "Deferrable execution requires Apache Airflow runtime."
            )

    class BaseSensorOperator(BaseOperator):
        def __init__(self, *, poke_interval: int = 60, timeout: int = 3600, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.poke_interval = poke_interval
            self.timeout = timeout

    @dataclass(frozen=True)
    class PokeReturnValue:
        is_done: bool
        xcom_value: Any = None

    class BaseTrigger:
        def serialize(self) -> tuple[str, dict[str, Any]]:
            raise NotImplementedError

        async def run(self):  # noqa: ANN201
            raise NotImplementedError

    @dataclass(frozen=True)
    class TriggerEvent:
        payload: dict[str, Any]

