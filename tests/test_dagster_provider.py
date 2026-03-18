from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import httpx
import pytest


PROVIDER_SRC = Path(__file__).resolve().parents[1] / "providers" / "dagster" / "src"
if str(PROVIDER_SRC) not in sys.path:
    sys.path.insert(0, str(PROVIDER_SRC))

from dagster_sparkpilot._compat import Failure, OpExecutionContext, RetryRequested  # noqa: E402
from dagster_sparkpilot.client import SparkPilotClient, SparkPilotClientConfig  # noqa: E402
from dagster_sparkpilot.common import normalize_op_config  # noqa: E402
from dagster_sparkpilot.errors import (  # noqa: E402
    SparkPilotPermanentError,
    SparkPilotRunFailedError,
    SparkPilotTransientError,
)
from dagster_sparkpilot.ops import (  # noqa: E402
    CancelRunOpConfig,
    SubmitRunOpConfig,
    WaitRunOpConfig,
    _looks_like_sparkpilot_client,
    cancel_run_with_client,
    sparkpilot_submit_run_op,
    sparkpilot_wait_for_run_op,
    submit_run_with_client,
    wait_for_run_with_client,
)
from dagster_sparkpilot.resource import sparkpilot_resource_from_config  # noqa: E402


def _client_config() -> SparkPilotClientConfig:
    return SparkPilotClientConfig.from_mapping(
        {
            "base_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
            "oidc_client_id": "dagster-client",
            "oidc_client_secret": "dagster-secret",
            "oidc_token_endpoint": "https://issuer.local/oauth/token",
            "request_retries": 1,
            "request_backoff_seconds": 0,
        }
    )


def test_client_submit_run_retries_transient_status(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SparkPilotClient(_client_config())
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    def _fake_token(*_args, **_kwargs):  # noqa: ANN001, ANN202
        request = httpx.Request("POST", "https://issuer.local/oauth/token")
        return httpx.Response(200, json={"access_token": "token-1", "expires_in": 300}, request=request)

    attempts = {"count": 0}

    def _fake_request(**kwargs):  # noqa: ANN001, ANN202
        attempts["count"] += 1
        request = httpx.Request(kwargs["method"], kwargs["url"])
        if attempts["count"] == 1:
            return httpx.Response(503, json={"detail": "temporary outage"}, request=request)
        return httpx.Response(201, json={"id": "run-1", "state": "queued"}, request=request)

    monkeypatch.setattr("httpx.post", _fake_token)
    monkeypatch.setattr("httpx.request", _fake_request)

    submitted = client.submit_run(
        job_id="job-1",
        run_payload={"golden_path": "small"},
        idempotency_key="idem-1",
    )

    assert attempts["count"] == 2
    assert submitted["id"] == "run-1"
    assert submitted["state"] == "queued"


def test_client_wait_for_terminal_state_raises_terminal_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SparkPilotClient(_client_config())

    def _fake_get_run(_run_id: str) -> dict[str, object]:
        return {"id": "run-fail", "state": "failed", "error_message": "driver pod OOM"}

    monkeypatch.setattr(client, "get_run", _fake_get_run)
    with pytest.raises(SparkPilotRunFailedError, match="terminal failure state 'failed'"):
        client.wait_for_terminal_state(run_id="run-fail", poll_interval_seconds=1, timeout_seconds=5)


def test_submit_and_wait_helpers_happy_path() -> None:
    class _FakeClient:
        def submit_run(  # noqa: ANN201
            self, *, job_id: str, run_payload: dict[str, object], idempotency_key: str | None = None
        ):
            assert job_id == "job-1"
            assert run_payload == {"golden_path": "small"}
            assert idempotency_key == "idem-submit"
            return {"id": "run-ok", "state": "queued"}

        def wait_for_terminal_state(  # noqa: ANN201
            self, *, run_id: str, poll_interval_seconds: int, timeout_seconds: int
        ):
            assert run_id == "run-ok"
            assert poll_interval_seconds == 2
            assert timeout_seconds == 120
            return {
                "id": "run-ok",
                "state": "succeeded",
                "started_at": "2026-03-11T10:00:00+00:00",
                "ended_at": "2026-03-11T10:00:30+00:00",
                "spark_ui_uri": "https://sparkhistory.local/run-ok",
            }

    submitted = submit_run_with_client(
        _FakeClient(),  # type: ignore[arg-type]
        SubmitRunOpConfig(job_id="job-1", golden_path="small", idempotency_key="idem-submit"),
    )
    terminal = wait_for_run_with_client(
        _FakeClient(),  # type: ignore[arg-type]
        WaitRunOpConfig(poll_interval_seconds=2, timeout_seconds=120),
        run_metadata=submitted,
    )
    assert submitted["id"] == "run-ok"
    assert submitted["status"] == "queued"
    assert terminal["status"] == "succeeded"
    assert terminal["duration_seconds"] == 30


def test_cancel_helper_waits_until_terminal() -> None:
    class _FakeClient:
        def __init__(self) -> None:
            self.wait_called = False

        def cancel_run(self, *, run_id: str, idempotency_key: str | None = None):  # noqa: ANN201
            assert run_id == "run-cancel"
            assert idempotency_key == "idem-cancel"
            return {"id": "run-cancel", "state": "running", "cancellation_requested": True}

        def wait_for_terminal_state(  # noqa: ANN201
            self, *, run_id: str, poll_interval_seconds: int, timeout_seconds: int
        ):
            self.wait_called = True
            assert run_id == "run-cancel"
            assert poll_interval_seconds == 3
            assert timeout_seconds == 60
            return {"id": "run-cancel", "state": "cancelled"}

    fake_client = _FakeClient()
    result = cancel_run_with_client(
        fake_client,  # type: ignore[arg-type]
        CancelRunOpConfig(
            run_id=None,
            idempotency_key="idem-cancel",
            wait_for_completion=True,
            poll_interval_seconds=3,
            timeout_seconds=60,
        ),
        run_metadata={"id": "run-cancel"},
    )
    assert fake_client.wait_called is True
    assert result["status"] == "cancelled"


def test_submit_op_maps_transient_error_to_retry_requested() -> None:
    class _FailingClient:
        def submit_run(self, **_kwargs: object) -> dict[str, object]:
            raise SparkPilotTransientError("temporary outage")

        def get_run(self, _run_id: str) -> dict[str, object]:
            return {}

        def cancel_run(self, **_kwargs: object) -> dict[str, object]:
            return {}

        def wait_for_terminal_state(self, **_kwargs: object) -> dict[str, object]:
            return {}

    context = OpExecutionContext(
        op_config={"job_id": "job-1"},
        resources=SimpleNamespace(sparkpilot=_FailingClient()),
    )
    with pytest.raises(RetryRequested):
        sparkpilot_submit_run_op(context)


def test_wait_op_maps_terminal_failure_to_failure() -> None:
    class _FailingClient:
        def submit_run(self, **_kwargs: object) -> dict[str, object]:
            return {}

        def get_run(self, _run_id: str) -> dict[str, object]:
            return {}

        def cancel_run(self, **_kwargs: object) -> dict[str, object]:
            return {}

        def wait_for_terminal_state(self, **_kwargs: object) -> dict[str, object]:
            raise SparkPilotRunFailedError("terminal state failed")

    context = OpExecutionContext(
        op_config={"poll_interval_seconds": 1, "timeout_seconds": 5},
        resources=SimpleNamespace(sparkpilot=_FailingClient()),
    )
    with pytest.raises(Failure, match="terminal state failed"):
        sparkpilot_wait_for_run_op(context, {"id": "run-1"})


def test_resource_factory_validates_required_fields() -> None:
    with pytest.raises(ValueError, match="oidc_client_secret"):
        sparkpilot_resource_from_config(
            {
                "base_url": "http://sparkpilot.local:8000",
                "oidc_issuer": "https://issuer.local",
                "oidc_audience": "sparkpilot-api",
                "oidc_client_id": "dagster-client",
            }
        )


# ---------------------------------------------------------------------------
# #61 – _compat catches only ImportError/ModuleNotFoundError
# ---------------------------------------------------------------------------


def test_compat_import_error_caught() -> None:
    """Importing from _compat must work even when dagster is absent."""
    # The module was already imported, so this just verifies the stubs resolved.
    from dagster_sparkpilot._compat import Failure as F, RetryRequested as RR  # noqa: F401

    assert issubclass(F, Exception)
    assert issubclass(RR, Exception)


def test_compat_runtime_exception_not_swallowed() -> None:
    """A RuntimeError raised during import should propagate, not be silenced."""
    import importlib
    import types

    # Simulate a broken dagster module that raises RuntimeError on import
    broken = types.ModuleType("dagster")
    broken.__spec__ = None  # type: ignore[attr-defined]

    def _raiser(*_a: object, **_k: object) -> None:
        raise RuntimeError("unexpected runtime failure")

    # We cannot easily re-trigger the except-block without reloading the module,
    # but we can verify the guard is ImportError/ModuleNotFoundError only by
    # inspecting the source of the try/except.
    import inspect
    import dagster_sparkpilot._compat as compat_mod

    src = inspect.getsource(compat_mod)
    assert "except (ImportError, ModuleNotFoundError):" in src, (
        "_compat.py must catch only ImportError/ModuleNotFoundError, not broad Exception"
    )


# ---------------------------------------------------------------------------
# #62 – Token/discovery HTTP failures map to SparkPilot domain errors
# ---------------------------------------------------------------------------


def test_discovery_401_raises_permanent_error(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SparkPilotClientConfig.from_mapping(
        {
            "base_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
            "oidc_client_id": "c",
            "oidc_client_secret": "s",
        }
    )
    client = SparkPilotClient(config)

    def _bad_get(url: str, **_kw: object) -> httpx.Response:
        req = httpx.Request("GET", url)
        return httpx.Response(401, request=req)

    monkeypatch.setattr("httpx.get", _bad_get)
    with pytest.raises(SparkPilotPermanentError, match="HTTP 401"):
        client._discover_token_endpoint()


def test_discovery_503_raises_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SparkPilotClientConfig.from_mapping(
        {
            "base_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
            "oidc_client_id": "c",
            "oidc_client_secret": "s",
        }
    )
    client = SparkPilotClient(config)

    def _bad_get(url: str, **_kw: object) -> httpx.Response:
        req = httpx.Request("GET", url)
        return httpx.Response(503, request=req)

    monkeypatch.setattr("httpx.get", _bad_get)
    with pytest.raises(SparkPilotTransientError, match="HTTP 503"):
        client._discover_token_endpoint()


def test_token_401_raises_permanent_error(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SparkPilotClientConfig.from_mapping(
        {
            "base_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
            "oidc_client_id": "c",
            "oidc_client_secret": "s",
            "oidc_token_endpoint": "https://issuer.local/oauth/token",
        }
    )
    client = SparkPilotClient(config)

    def _bad_post(url: str, **_kw: object) -> httpx.Response:
        req = httpx.Request("POST", url)
        return httpx.Response(401, request=req)

    monkeypatch.setattr("httpx.post", _bad_post)
    with pytest.raises(SparkPilotPermanentError, match="HTTP 401"):
        client._fetch_access_token()


def test_token_429_raises_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SparkPilotClientConfig.from_mapping(
        {
            "base_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
            "oidc_client_id": "c",
            "oidc_client_secret": "s",
            "oidc_token_endpoint": "https://issuer.local/oauth/token",
        }
    )
    client = SparkPilotClient(config)

    def _bad_post(url: str, **_kw: object) -> httpx.Response:
        req = httpx.Request("POST", url)
        return httpx.Response(429, request=req)

    monkeypatch.setattr("httpx.post", _bad_post)
    with pytest.raises(SparkPilotTransientError, match="HTTP 429"):
        client._fetch_access_token()


def test_discovery_transport_failure_raises_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SparkPilotClientConfig.from_mapping(
        {
            "base_url": "http://sparkpilot.local:8000",
            "oidc_issuer": "https://issuer.local",
            "oidc_audience": "sparkpilot-api",
            "oidc_client_id": "c",
            "oidc_client_secret": "s",
        }
    )
    client = SparkPilotClient(config)

    def _network_fail(url: str, **_kw: object) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("httpx.get", _network_fail)
    with pytest.raises(SparkPilotTransientError, match="transport"):
        client._discover_token_endpoint()


# ---------------------------------------------------------------------------
# #63 – _looks_like_sparkpilot_client requires ALL methods; normalization shared
# ---------------------------------------------------------------------------


def test_looks_like_sparkpilot_client_requires_all_methods() -> None:
    class PartialClient:
        def submit_run(self, **_kw: object) -> dict[str, object]:
            return {}

    with pytest.raises(ValueError, match="missing required methods"):
        _looks_like_sparkpilot_client(PartialClient())


def test_looks_like_sparkpilot_client_accepts_full_implementation() -> None:
    class FullClient:
        def submit_run(self, **_kw: object) -> dict[str, object]:
            return {}

        def get_run(self, _run_id: str) -> dict[str, object]:
            return {}

        def cancel_run(self, **_kw: object) -> dict[str, object]:
            return {}

        def wait_for_terminal_state(self, **_kw: object) -> dict[str, object]:
            return {}

    assert _looks_like_sparkpilot_client(FullClient()) is True


def test_normalize_op_config_strips_sentinels() -> None:
    raw = {
        "job_id": "job-1",
        "golden_path": "",
        "idempotency_key": "",
        "run_id": "",
        "run_timeout_seconds": 0,
        "args": [],
        "spark_conf": {},
        "requested_resources": {},
    }
    result = normalize_op_config(raw)
    assert result == {"job_id": "job-1"}


def test_normalize_op_config_preserves_non_sentinel_values() -> None:
    raw = {
        "job_id": "job-2",
        "golden_path": "small",
        "run_timeout_seconds": 120,
        "args": ["--mode", "batch"],
    }
    result = normalize_op_config(raw)
    assert result["golden_path"] == "small"
    assert result["run_timeout_seconds"] == 120
    assert result["args"] == ["--mode", "batch"]


def test_normalize_op_config_ops_and_assets_share_implementation() -> None:
    """Ops and assets must delegate to the same normalize_op_config function."""
    from dagster_sparkpilot.ops import _normalized_op_config as ops_normalizer  # noqa: F401
    from dagster_sparkpilot.assets import _normalized_asset_config as asset_normalizer  # noqa: F401
    import inspect

    ops_src = inspect.getsource(ops_normalizer)
    asset_src = inspect.getsource(asset_normalizer)
    assert "normalize_op_config" in ops_src, "ops normalizer must call shared normalize_op_config"
    assert "normalize_op_config" in asset_src, "asset normalizer must call shared normalize_op_config"

