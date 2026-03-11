from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import httpx
import pytest


PROVIDER_SRC = Path(__file__).resolve().parents[1] / "providers" / "airflow" / "src"
if str(PROVIDER_SRC) not in sys.path:
    sys.path.insert(0, str(PROVIDER_SRC))

from airflow.providers.sparkpilot._compat import AirflowException, AirflowFailException  # noqa: E402
from airflow.providers.sparkpilot.common import SparkPilotPermanentError, SparkPilotTransientError  # noqa: E402
from airflow.providers.sparkpilot.hooks.sparkpilot import SparkPilotHook  # noqa: E402
from airflow.providers.sparkpilot.operators.sparkpilot import SparkPilotCancelRunOperator, SparkPilotSubmitRunOperator  # noqa: E402
from airflow.providers.sparkpilot.sensors.sparkpilot import SparkPilotRunSensor  # noqa: E402
from airflow.providers.sparkpilot.triggers.sparkpilot import SparkPilotRunTrigger  # noqa: E402


class _Conn:
    def __init__(
        self,
        *,
        host: str | None = None,
        schema: str | None = None,
        port: int | None = None,
        login: str | None = None,
        password: str | None = None,
        extra_dejson: dict[str, str] | None = None,
    ) -> None:
        self.host = host
        self.schema = schema
        self.port = port
        self.login = login
        self.password = password
        self.extra_dejson = extra_dejson or {}


def test_hook_submit_run_uses_oidc_bearer_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn(
        extra_dejson={
            "sparkpilot_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
        },
        login="airflow-client",
        password="airflow-secret",
    )
    monkeypatch.setattr(SparkPilotHook, "get_connection", classmethod(lambda _cls, _conn_id: conn))
    monkeypatch.setattr(SparkPilotHook, "_get_access_token", lambda _self, _resolved, force_refresh=False: "access-1")

    captured: dict[str, object] = {}

    def _fake_request(**kwargs):  # noqa: ANN001, ANN202
        captured.update(kwargs)
        request = httpx.Request("POST", "http://sparkpilot.local:8000/v1/jobs/job-1/runs")
        return httpx.Response(201, json={"id": "run-1", "state": "queued"}, request=request)

    monkeypatch.setattr("httpx.request", _fake_request)
    hook = SparkPilotHook(sparkpilot_conn_id="sparkpilot_default")
    payload = hook.submit_run(job_id="job-1", run_payload={"golden_path": "small"}, idempotency_key="idem-1")

    assert payload["id"] == "run-1"
    assert captured["url"] == "http://sparkpilot.local:8000/v1/jobs/job-1/runs"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer access-1"
    assert "X-Actor" not in headers
    assert headers["Idempotency-Key"] == "idem-1"


def test_hook_build_headers_contains_only_bearer_identity() -> None:
    headers = SparkPilotHook.build_headers("token-1")
    assert headers["Authorization"] == "Bearer token-1"
    assert headers["Accept"] == "application/json"
    assert "X-Actor" not in headers


def test_hook_resolves_connection_from_host_schema_port_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn(host="sparkpilot.local", schema="https", port=8443, login="conn-client", password="conn-secret")
    monkeypatch.setattr(SparkPilotHook, "get_connection", classmethod(lambda _cls, _conn_id: conn))
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.env")
    monkeypatch.setenv("OIDC_AUDIENCE", "sparkpilot-api")

    hook = SparkPilotHook(sparkpilot_conn_id="sparkpilot_default")
    resolved = hook.resolve_connection()
    assert resolved.base_url == "https://sparkpilot.local:8443"
    assert resolved.issuer == "https://issuer.env"
    assert resolved.audience == "sparkpilot-api"
    assert resolved.client_id == "conn-client"
    assert resolved.client_secret == "conn-secret"


def test_hook_raises_when_required_oidc_fields_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn(extra_dejson={"sparkpilot_url": "http://sparkpilot.local:8000"})
    monkeypatch.setattr(SparkPilotHook, "get_connection", classmethod(lambda _cls, _conn_id: conn))

    hook = SparkPilotHook()
    with pytest.raises(AirflowException, match="missing required OIDC fields"):
        hook.resolve_connection()


def test_hook_raises_transient_error_for_retryable_status(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn(
        extra_dejson={
            "sparkpilot_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
        },
        login="airflow-client",
        password="airflow-secret",
    )
    monkeypatch.setattr(SparkPilotHook, "get_connection", classmethod(lambda _cls, _conn_id: conn))
    monkeypatch.setattr(SparkPilotHook, "_get_access_token", lambda _self, _resolved, force_refresh=False: "access-1")

    def _fake_request(**_kwargs):  # noqa: ANN001, ANN202
        request = httpx.Request("GET", "http://sparkpilot.local:8000/v1/runs/run-1")
        return httpx.Response(503, json={"detail": "temporary outage"}, request=request)

    monkeypatch.setattr("httpx.request", _fake_request)
    hook = SparkPilotHook()
    with pytest.raises(SparkPilotTransientError):
        hook.get_run("run-1")


def test_hook_raises_permanent_error_for_non_retryable_status(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn(
        extra_dejson={
            "sparkpilot_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
        },
        login="airflow-client",
        password="airflow-secret",
    )
    monkeypatch.setattr(SparkPilotHook, "get_connection", classmethod(lambda _cls, _conn_id: conn))
    monkeypatch.setattr(SparkPilotHook, "_get_access_token", lambda _self, _resolved, force_refresh=False: "access-1")

    def _fake_request(**_kwargs):  # noqa: ANN001, ANN202
        request = httpx.Request("GET", "http://sparkpilot.local:8000/v1/runs/run-1")
        return httpx.Response(403, json={"detail": "forbidden"}, request=request)

    monkeypatch.setattr("httpx.request", _fake_request)
    hook = SparkPilotHook()
    with pytest.raises(SparkPilotPermanentError):
        hook.get_run("run-1")


def test_hook_wait_for_terminal_state_retries_transient_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn(
        extra_dejson={
            "sparkpilot_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
        },
        login="airflow-client",
        password="airflow-secret",
    )
    monkeypatch.setattr(SparkPilotHook, "get_connection", classmethod(lambda _cls, _conn_id: conn))

    calls = {"count": 0}

    def _fake_get_run(_self, _run_id: str) -> dict[str, object]:
        calls["count"] += 1
        if calls["count"] == 1:
            raise SparkPilotTransientError("temporary outage")
        return {"id": "run-1", "state": "succeeded"}

    monkeypatch.setattr(SparkPilotHook, "get_run", _fake_get_run)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    hook = SparkPilotHook()
    run = hook.wait_for_terminal_state(run_id="run-1", poll_interval_seconds=1, timeout_seconds=10)
    assert run["state"] == "succeeded"
    assert calls["count"] == 2


def test_operator_supports_golden_path_and_xcom_metadata() -> None:
    class _FakeHook:
        def __init__(self) -> None:
            self.submitted_payload: dict[str, object] | None = None

        def submit_run(self, *, job_id: str, run_payload: dict[str, object], idempotency_key: str | None):  # noqa: ANN201
            assert job_id == "job-1"
            assert idempotency_key == "idem-operator"
            self.submitted_payload = run_payload
            return {"id": "run-1", "state": "queued"}

        def wait_for_terminal_state(self, *, run_id: str, poll_interval_seconds: int, timeout_seconds: int):  # noqa: ANN201
            assert run_id == "run-1"
            assert poll_interval_seconds == 2
            assert timeout_seconds == 120
            return {
                "id": "run-1",
                "state": "succeeded",
                "started_at": "2026-03-03T10:00:00+00:00",
                "ended_at": "2026-03-03T10:00:30+00:00",
                "driver_log_uri": "cloudwatch://logs/group/stream",
            }

    fake_hook = _FakeHook()
    op = SparkPilotSubmitRunOperator(
        task_id="submit",
        job_id="job-1",
        golden_path="small",
        wait_for_completion=True,
        poll_interval_seconds=2,
        timeout_seconds=120,
        idempotency_key="idem-operator",
        hook=fake_hook,  # type: ignore[arg-type]
    )

    metadata = op.execute(context={})
    assert fake_hook.submitted_payload == {"golden_path": "small"}
    assert metadata is not None
    assert metadata["id"] == "run-1"
    assert metadata["status"] == "succeeded"
    assert metadata["duration_seconds"] == 30
    assert metadata["log_url"] == "cloudwatch://logs/group/stream"


def test_operator_supports_raw_config_mode_without_wait() -> None:
    class _FakeHook:
        def __init__(self) -> None:
            self.payload: dict[str, object] | None = None

        def submit_run(self, *, job_id: str, run_payload: dict[str, object], idempotency_key: str | None):  # noqa: ANN201
            assert job_id == "job-raw"
            self.payload = run_payload
            return {"id": "run-2", "state": "queued"}

    fake_hook = _FakeHook()
    op = SparkPilotSubmitRunOperator(
        task_id="submit_raw",
        job_id="job-raw",
        args=["--date", "2026-03-03"],
        spark_conf={"spark.sql.shuffle.partitions": "8"},
        requested_resources={
            "driver_vcpu": 1,
            "driver_memory_gb": 4,
            "executor_vcpu": 2,
            "executor_memory_gb": 8,
            "executor_instances": 2,
        },
        run_timeout_seconds=600,
        timeout_seconds=30,
        wait_for_completion=False,
        hook=fake_hook,  # type: ignore[arg-type]
    )
    metadata = op.execute(context={})
    assert fake_hook.payload == {
        "args": ["--date", "2026-03-03"],
        "spark_conf": {"spark.sql.shuffle.partitions": "8"},
        "requested_resources": {
            "driver_vcpu": 1,
            "driver_memory_gb": 4,
            "executor_vcpu": 2,
            "executor_memory_gb": 8,
            "executor_instances": 2,
        },
        "timeout_seconds": 600,
    }
    assert metadata is not None
    assert metadata["id"] == "run-2"
    assert metadata["status"] == "queued"


def test_operator_deferrable_path_defers_with_trigger() -> None:
    class _FakeHook:
        def submit_run(self, *, job_id: str, run_payload: dict[str, object], idempotency_key: str | None):  # noqa: ANN201
            assert job_id == "job-def"
            return {"id": "run-def", "state": "queued"}

    class _CaptureDeferOperator(SparkPilotSubmitRunOperator):
        def __init__(self, **kwargs):  # noqa: ANN003, ANN204
            super().__init__(**kwargs)
            self.trigger = None
            self.method_name = None

        def defer(self, *, timeout=None, trigger=None, method_name="execute_complete"):  # noqa: ANN001, ANN202
            self.trigger = trigger
            self.method_name = method_name

    op = _CaptureDeferOperator(
        task_id="submit_def",
        job_id="job-def",
        deferrable=True,
        poll_interval_seconds=3,
        timeout_seconds=90,
        hook=_FakeHook(),  # type: ignore[arg-type]
    )
    result = op.execute(context={})
    assert result is None
    assert isinstance(op.trigger, SparkPilotRunTrigger)
    assert op.method_name == "execute_complete"
    serialized = op.trigger.serialize()
    assert serialized[1]["run_id"] == "run-def"


def test_operator_execute_complete_handles_trigger_contract() -> None:
    op = SparkPilotSubmitRunOperator(task_id="complete_contract", job_id="job-complete", wait_for_completion=False)

    success = op.execute_complete(context={}, event={"status": "success", "metadata": {"id": "run-1", "status": "succeeded"}})
    assert success["id"] == "run-1"

    with pytest.raises(AirflowFailException):
        op.execute_complete(context={}, event={"status": "failed", "transient": False, "message": "permanent failure"})

    with pytest.raises(AirflowException):
        op.execute_complete(context={}, event={"status": "error", "transient": True, "message": "retryable error"})


def test_sensor_raises_on_failure_terminal_state() -> None:
    class _FakeHook:
        def get_run(self, _run_id: str) -> dict[str, object]:
            return {"id": "run-fail", "state": "failed", "error_message": "boom"}

    sensor = SparkPilotRunSensor(
        task_id="wait_run",
        run_id="run-fail",
        hook=_FakeHook(),  # type: ignore[arg-type]
    )
    with pytest.raises(AirflowFailException):
        sensor.poke(context={})


def test_sensor_returns_xcom_value_on_success() -> None:
    class _FakeHook:
        def get_run(self, _run_id: str) -> dict[str, object]:
            return {
                "id": "run-ok",
                "state": "succeeded",
                "started_at": "2026-03-03T10:00:00+00:00",
                "ended_at": "2026-03-03T10:01:00+00:00",
                "spark_ui_uri": "https://sparkhistory.local/run-ok",
            }

    sensor = SparkPilotRunSensor(
        task_id="wait_ok",
        run_id="run-ok",
        hook=_FakeHook(),  # type: ignore[arg-type]
    )
    result = sensor.poke(context={})
    assert getattr(result, "is_done") is True
    xcom = getattr(result, "xcom_value")
    assert isinstance(xcom, dict)
    assert xcom["id"] == "run-ok"
    assert xcom["status"] == "succeeded"
    assert xcom["duration_seconds"] == 60
    assert xcom["log_url"] == "https://sparkhistory.local/run-ok"


def test_trigger_async_run_yields_success_event(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn(
        extra_dejson={
            "sparkpilot_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
        },
        login="airflow-client",
        password="airflow-secret",
    )
    monkeypatch.setattr(SparkPilotHook, "get_connection", classmethod(lambda _cls, _conn_id: conn))
    monkeypatch.setattr(SparkPilotHook, "get_access_token", lambda _self, force_refresh=False: "access-async")

    class _FakeAsyncClient:
        def __init__(self, **_kwargs) -> None:  # noqa: ANN003
            pass

        async def __aenter__(self):  # noqa: ANN204
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN204
            return None

        async def get(self, _url: str, headers: dict[str, str]):  # noqa: ANN001, ANN202
            assert headers["Authorization"] == "Bearer access-async"
            request = httpx.Request("GET", "http://sparkpilot.local:8000/v1/runs/run-async")
            return httpx.Response(
                200,
                json={"id": "run-async", "state": "succeeded"},
                request=request,
            )

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    trigger = SparkPilotRunTrigger(run_id="run-async", poll_interval_seconds=1, timeout_seconds=5)

    async def _collect_event() -> dict[str, object]:
        async for event in trigger.run():
            return dict(event.payload)
        raise AssertionError("Trigger yielded no events.")

    event = asyncio.run(_collect_event())
    assert event["status"] == "success"
    assert event["metadata"]["id"] == "run-async"


# ---------- Hook cancel_run ----------


def test_hook_cancel_run_sends_idempotency_key(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn(
        extra_dejson={
            "sparkpilot_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
        },
        login="airflow-client",
        password="airflow-secret",
    )
    monkeypatch.setattr(SparkPilotHook, "get_connection", classmethod(lambda _cls, _conn_id: conn))
    monkeypatch.setattr(SparkPilotHook, "_get_access_token", lambda _self, _resolved, force_refresh=False: "access-1")

    captured: dict[str, object] = {}

    def _fake_request(**kwargs):  # noqa: ANN001, ANN202
        captured.update(kwargs)
        request = httpx.Request("POST", "http://sparkpilot.local:8000/v1/runs/run-cancel/cancel")
        return httpx.Response(200, json={"id": "run-cancel", "state": "cancelled"}, request=request)

    monkeypatch.setattr("httpx.request", _fake_request)
    hook = SparkPilotHook()
    result = hook.cancel_run(run_id="run-cancel", idempotency_key="idem-cancel-1")

    assert result["id"] == "run-cancel"
    assert result["state"] == "cancelled"
    assert captured["url"] == "http://sparkpilot.local:8000/v1/runs/run-cancel/cancel"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Idempotency-Key"] == "idem-cancel-1"
    assert headers["Authorization"] == "Bearer access-1"


def test_hook_cancel_run_generates_idempotency_key_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn(
        extra_dejson={
            "sparkpilot_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
        },
        login="airflow-client",
        password="airflow-secret",
    )
    monkeypatch.setattr(SparkPilotHook, "get_connection", classmethod(lambda _cls, _conn_id: conn))
    monkeypatch.setattr(SparkPilotHook, "_get_access_token", lambda _self, _resolved, force_refresh=False: "access-1")

    captured: dict[str, object] = {}

    def _fake_request(**kwargs):  # noqa: ANN001, ANN202
        captured.update(kwargs)
        request = httpx.Request("POST", "http://sparkpilot.local:8000/v1/runs/run-cancel/cancel")
        return httpx.Response(200, json={"id": "run-cancel", "state": "cancelled"}, request=request)

    monkeypatch.setattr("httpx.request", _fake_request)
    hook = SparkPilotHook()
    hook.cancel_run(run_id="run-cancel")

    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Idempotency-Key"].startswith("airflow-cancel-")


# ---------- CancelRunOperator ----------


def test_cancel_operator_requests_cancellation_and_waits() -> None:
    class _FakeHook:
        def __init__(self) -> None:
            self.cancelled_run_id: str | None = None
            self.cancelled_key: str | None = None

        def cancel_run(self, *, run_id: str, idempotency_key: str | None = None) -> dict[str, object]:
            self.cancelled_run_id = run_id
            self.cancelled_key = idempotency_key
            return {"id": run_id, "state": "running", "cancellation_requested": True}

        def wait_for_terminal_state(self, *, run_id: str, poll_interval_seconds: int, timeout_seconds: int) -> dict[str, object]:
            assert run_id == "run-cancel-1"
            assert poll_interval_seconds == 5
            assert timeout_seconds == 60
            return {
                "id": "run-cancel-1",
                "state": "cancelled",
                "started_at": "2026-03-03T10:00:00+00:00",
                "ended_at": "2026-03-03T10:00:20+00:00",
            }

    fake_hook = _FakeHook()
    op = SparkPilotCancelRunOperator(
        task_id="cancel",
        run_id="run-cancel-1",
        idempotency_key="idem-cancel-op",
        wait_for_completion=True,
        poll_interval_seconds=5,
        timeout_seconds=60,
        hook=fake_hook,  # type: ignore[arg-type]
    )
    metadata = op.execute(context={})
    assert fake_hook.cancelled_run_id == "run-cancel-1"
    assert fake_hook.cancelled_key == "idem-cancel-op"
    assert metadata["id"] == "run-cancel-1"
    assert metadata["status"] == "cancelled"
    assert metadata["duration_seconds"] == 20


def test_cancel_operator_returns_immediately_when_already_terminal() -> None:
    class _FakeHook:
        def cancel_run(self, *, run_id: str, idempotency_key: str | None = None) -> dict[str, object]:
            return {"id": run_id, "state": "succeeded", "started_at": "2026-03-03T10:00:00+00:00", "ended_at": "2026-03-03T10:00:10+00:00"}

        def wait_for_terminal_state(self, **_kwargs: object) -> dict[str, object]:
            raise AssertionError("Should not poll when already terminal")

    op = SparkPilotCancelRunOperator(
        task_id="cancel_already_done",
        run_id="run-done",
        wait_for_completion=True,
        hook=_FakeHook(),  # type: ignore[arg-type]
    )
    metadata = op.execute(context={})
    assert metadata["status"] == "succeeded"


def test_cancel_operator_no_wait_mode() -> None:
    class _FakeHook:
        def cancel_run(self, *, run_id: str, idempotency_key: str | None = None) -> dict[str, object]:
            return {"id": run_id, "state": "running", "cancellation_requested": True}

        def wait_for_terminal_state(self, **_kwargs: object) -> dict[str, object]:
            raise AssertionError("Should not poll when wait_for_completion=False")

    op = SparkPilotCancelRunOperator(
        task_id="cancel_nowait",
        run_id="run-nowait",
        wait_for_completion=False,
        hook=_FakeHook(),  # type: ignore[arg-type]
    )
    metadata = op.execute(context={})
    assert metadata["id"] == "run-nowait"
    assert metadata["status"] == "running"


def test_cancel_operator_raises_on_permanent_error() -> None:
    class _FakeHook:
        def cancel_run(self, *, run_id: str, idempotency_key: str | None = None) -> dict[str, object]:
            raise SparkPilotPermanentError("forbidden: not allowed")

    op = SparkPilotCancelRunOperator(
        task_id="cancel_perm_err",
        run_id="run-perm",
        hook=_FakeHook(),  # type: ignore[arg-type]
    )
    with pytest.raises(AirflowFailException, match="forbidden"):
        op.execute(context={})


def test_cancel_operator_raises_on_transient_error() -> None:
    class _FakeHook:
        def cancel_run(self, *, run_id: str, idempotency_key: str | None = None) -> dict[str, object]:
            raise SparkPilotTransientError("service unavailable")

    op = SparkPilotCancelRunOperator(
        task_id="cancel_trans_err",
        run_id="run-trans",
        hook=_FakeHook(),  # type: ignore[arg-type]
    )
    with pytest.raises(AirflowException, match="service unavailable"):
        op.execute(context={})


def test_cancel_operator_requires_non_empty_run_id() -> None:
    with pytest.raises(ValueError, match="run_id is required"):
        SparkPilotCancelRunOperator(
            task_id="cancel_invalid",
            run_id="  ",
        )
