from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import httpx
import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "smoke" / "live_byoc_lite.py"
    spec = spec_from_file_location("sparkpilot_smoke_live_byoc_lite", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke = _load_module()


def test_classify_exception_for_smoke_failure() -> None:
    exc = smoke.SmokeFailure(classification="api_auth", stage="oidc_token", message="auth failed")
    classification, stage = smoke._classify_exception(exc)
    assert classification == "api_auth"
    assert stage == "oidc_token"


def test_classify_exception_for_unexpected() -> None:
    classification, stage = smoke._classify_exception(RuntimeError("boom"))
    assert classification == "unexpected"
    assert stage == "unknown"


def test_write_summary_writes_json(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    payload = {"status": "ok", "classification": "success"}
    smoke._write_summary(str(summary_path), payload)
    loaded = json.loads(summary_path.read_text(encoding="utf-8"))
    assert loaded == payload


def test_request_json_classifies_auth_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    transport = httpx.MockTransport(handler)
    with httpx.Client(base_url="http://example.test", transport=transport) as client:
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._request_json(
                client,
                method="GET",
                path="/v1/fail-auth",
                stage="fetch",
                access_token="token",
            )
    assert exc_info.value.classification == "api_auth"
    assert exc_info.value.stage == "fetch"


def test_request_json_classifies_non_auth_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    transport = httpx.MockTransport(handler)
    with httpx.Client(base_url="http://example.test", transport=transport) as client:
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._request_json(
                client,
                method="GET",
                path="/v1/fail-server",
                stage="fetch",
                access_token="token",
            )
    assert exc_info.value.classification == "api_request"
    assert exc_info.value.stage == "fetch"


def test_classify_terminal_run_state_maps_timed_out_to_timeout() -> None:
    classification, stage = smoke._classify_terminal_run_state("timed_out")
    assert classification == "run_state_timeout"
    assert stage == "wait_run"


def test_classify_terminal_run_state_maps_failed_to_api_request() -> None:
    classification, stage = smoke._classify_terminal_run_state("failed")
    assert classification == "api_request"
    assert stage == "run_terminal_state"
