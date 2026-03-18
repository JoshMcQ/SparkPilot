"""Databricks Jobs API dispatch client for SparkPilot."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import time
from typing import Any

import httpx

from sparkpilot.config import get_settings
from sparkpilot.models import Environment, Job, Run

logger = logging.getLogger(__name__)

DATABRICKS_TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}

DATABRICKS_TERMINAL_LIFECYCLE_STATES = {
    "TERMINATED", "SKIPPED", "INTERNAL_ERROR"
}
DATABRICKS_SUCCESS_RESULT_STATES = {"SUCCESS"}
DATABRICKS_FAILURE_RESULT_STATES = {"FAILED", "TIMEDOUT", "CANCELED", "MAXIMUM_CONCURRENT_RUNS_REACHED"}


@dataclass(slots=True)
class DatabricksDispatchResult:
    databricks_run_id: int
    run_page_url: str
    aws_request_id: str | None = None


class DatabricksClient:
    """Thin Databricks Jobs API client for SparkPilot dispatch."""

    def __init__(self, workspace_url: str, token: str) -> None:
        self.workspace_url = workspace_url.rstrip("/")
        self._token = token
        self._http = httpx.Client(
            base_url=self.workspace_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    def _post(self, path: str, payload: dict) -> dict:
        response = self._http.post(path, json=payload)
        response.raise_for_status()
        return response.json()

    def _get(self, path: str, params: dict | None = None) -> dict:
        response = self._http.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def preflight_check(self) -> dict[str, Any]:
        """Verify workspace connectivity, cluster policy, instance pool."""
        checks = []
        try:
            self._get("/api/2.0/clusters/list-node-types")
            checks.append({"name": "workspace_connectivity", "status": "pass"})
        except httpx.HTTPStatusError as e:
            checks.append({"name": "workspace_connectivity", "status": "fail", "detail": str(e)})
        return {"ready": all(c["status"] == "pass" for c in checks), "checks": checks}

    def submit_run(
        self,
        *,
        job_artifact_uri: str,
        entrypoint: str,
        args: list[str],
        spark_conf: dict[str, str],
        cluster_policy_id: str | None = None,
        instance_pool_id: str | None = None,
        run_name: str = "sparkpilot-run",
        idempotency_token: str | None = None,
    ) -> DatabricksDispatchResult:
        """Submit a one-time run via Databricks Jobs API runs/submit."""
        new_cluster: dict[str, Any] = {
            "spark_version": "13.3.x-scala2.12",
            "num_workers": 2,
        }
        if cluster_policy_id:
            new_cluster["policy_id"] = cluster_policy_id
        if instance_pool_id:
            new_cluster["instance_pool_id"] = instance_pool_id
        else:
            new_cluster["node_type_id"] = "i3.xlarge"

        spark_python_task: dict[str, Any] = {
            "python_file": f"{job_artifact_uri}/{entrypoint}" if not entrypoint.startswith("s3://") else entrypoint,
            "parameters": args,
            "source": "GIT" if "github" in job_artifact_uri.lower() else "S3",
        }

        payload: dict[str, Any] = {
            "run_name": run_name,
            "new_cluster": new_cluster,
            "spark_python_task": spark_python_task,
            "spark_conf": spark_conf,
        }
        if idempotency_token:
            payload["idempotency_token"] = idempotency_token

        response = self._post("/api/2.1/jobs/runs/submit", payload)
        run_id = int(response["run_id"])
        run_details = self._get("/api/2.1/jobs/runs/get", {"run_id": run_id})
        run_page_url = run_details.get("run_page_url", f"{self.workspace_url}/#job/{run_id}/run/{run_id}")
        return DatabricksDispatchResult(databricks_run_id=run_id, run_page_url=run_page_url)

    def get_run(self, run_id: int) -> dict[str, Any]:
        return self._get("/api/2.1/jobs/runs/get", {"run_id": run_id})

    def cancel_run(self, run_id: int) -> None:
        self._post("/api/2.1/jobs/runs/cancel", {"run_id": run_id})

    def get_run_output(self, run_id: int) -> dict[str, Any]:
        return self._get("/api/2.1/jobs/runs/get-output", {"run_id": run_id})
