"""Tests for Databricks dispatch client."""
import pytest
import httpx
from sparkpilot.databricks_client import DatabricksClient, DatabricksDispatchResult


def _mock_client(monkeypatch, responses: list[dict]) -> DatabricksClient:
    call_idx = {"n": 0}

    def _fake_send(self, request, **kwargs):
        idx = call_idx["n"]
        call_idx["n"] += 1
        resp_data = responses[idx % len(responses)]
        return httpx.Response(200, json=resp_data, request=request)

    monkeypatch.setattr("httpx.Client.send", _fake_send)
    return DatabricksClient("https://adb-12345.azuredatabricks.net", "dapi-fake-token")


def test_submit_run_returns_dispatch_result(monkeypatch):
    responses = [
        {"run_id": 42},
        {"run_page_url": "https://adb-12345.azuredatabricks.net/#job/42/run/42", "run_id": 42},
    ]
    client = _mock_client(monkeypatch, responses)
    result = client.submit_run(
        job_artifact_uri="s3://my-bucket/jobs/",
        entrypoint="s3://my-bucket/jobs/main.py",
        args=["--env", "prod"],
        spark_conf={"spark.executor.memory": "4g"},
        run_name="test-run",
    )
    assert isinstance(result, DatabricksDispatchResult)
    assert result.databricks_run_id == 42


def test_get_run_returns_lifecycle_state(monkeypatch):
    responses = [{"state": {"life_cycle_state": "RUNNING", "result_state": None}}]
    client = _mock_client(monkeypatch, responses)
    run = client.get_run(42)
    assert run["state"]["life_cycle_state"] == "RUNNING"


def test_cancel_run_posts_cancel(monkeypatch):
    responses = [{}]
    client = _mock_client(monkeypatch, responses)
    client.cancel_run(42)  # should not raise
