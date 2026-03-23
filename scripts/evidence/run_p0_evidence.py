#!/usr/bin/env python
"""P0 Evidence Gap Closure — Issue #33 #36 #46

This script:
1. Starts mock OIDC + SparkPilot API (with evidence2.db)
2. Submits a minimal-resource SparkPi job (fits in 2×t3.large)
3. Scales EKS nodegroup to 2 nodes
4. Waits for EMR COMPLETED state (max 20 min)
5. Runs CUR reconciliation
6. Captures Airflow DAG run (if docker-compose.airflow.yml is up)
7. Scales nodegroup back to 0
8. Writes evidence artifacts

Usage:
    python scripts/evidence/run_p0_evidence.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
DB_PATH = REPO_ROOT / "sparkpilot_evidence2.db"
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"

# SparkPilot API
API_BASE_URL = "http://127.0.0.1:8000"
OIDC_ISSUER = "http://127.0.0.1:8080"
OIDC_AUDIENCE = "sparkpilot-api"
OIDC_CLIENT_ID = "sparkpilot-cli"
OIDC_CLIENT_SECRET = "sparkpilot-cli-secret"
BOOTSTRAP_SECRET = "sparkpilot-local-bootstrap-secret"

# AWS / EMR
AWS_REGION = "us-east-1"
VIRTUAL_CLUSTER_ID = "580dfmy1wqym1dz7nkksxhzpp"
EKS_CLUSTER_NAME = "sparkpilot-live-1"
NODEGROUP_NAME = "sparkpilot-ng"
EMR_EXECUTION_ROLE_ARN = "arn:aws:iam::787587782916:role/SparkPilotEmrExecutionRole"
S3_BUCKET = "sparkpilot-live-787587782916-20260224203702"

# CUR Athena
CUR_ATHENA_DATABASE = "sparkpilot_r03_evidence"
CUR_ATHENA_TABLE = "cur_live_evidence_20260322"
CUR_ATHENA_WORKGROUP = "primary"
CUR_ATHENA_OUTPUT_LOCATION = f"s3://{S3_BUCKET}/athena-results/"

# Job to run
SPARKPI_JOB_ID = "dd87754d-bbef-45fb-bf84-e6686c4b990e"

# Minimal Spark conf — fits in 2×t3.large (4 vCPU, ~14 GB usable)
# Driver: 1 core + 1g overhead = ~1 vCPU, 1.5 GB
# Executor: 1 core + 1g = ~1 vCPU, 2.5 GB
# Total: ~2 vCPU, ~4 GB — well within 4 vCPU / 14 GB
MINIMAL_SPARK_CONF = {
    "spark.driver.cores": "1",
    "spark.driver.memory": "1g",
    "spark.executor.instances": "1",
    "spark.executor.cores": "1",
    "spark.executor.memory": "2g",
}

MINIMAL_RESOURCES = {
    "driver_vcpu": 1,
    "driver_memory_gb": 1,
    "executor_vcpu": 1,
    "executor_memory_gb": 2,
    "executor_instances": 1,
}

TERMINAL_STATES = {"succeeded", "failed", "cancelled", "timed_out"}
EMR_TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_cmd(args: list[str], *, env: dict[str, str] | None = None, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    merged_env = {**os.environ, **(env or {})}
    log.info("CMD: %s", " ".join(str(a) for a in args))
    return subprocess.run(
        args,
        env=merged_env,
        capture_output=capture,
        text=True,
        check=check,
    )


def _base_env() -> dict[str, str]:
    return {
        "SPARKPILOT_DATABASE_URL": f"sqlite:///{DB_PATH}",
        "SPARKPILOT_ENVIRONMENT": "dev",
        "SPARKPILOT_DRY_RUN_MODE": "false",
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN": EMR_EXECUTION_ROLE_ARN,
        "SPARKPILOT_AUTH_MODE": "oidc",
        "SPARKPILOT_OIDC_ISSUER": OIDC_ISSUER,
        "SPARKPILOT_OIDC_AUDIENCE": OIDC_AUDIENCE,
        "SPARKPILOT_OIDC_JWKS_URI": f"{OIDC_ISSUER}/.well-known/jwks.json",
        "SPARKPILOT_BOOTSTRAP_SECRET": BOOTSTRAP_SECRET,
        "SPARKPILOT_CORS_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
        "SPARKPILOT_CUR_ATHENA_DATABASE": CUR_ATHENA_DATABASE,
        "SPARKPILOT_CUR_ATHENA_TABLE": CUR_ATHENA_TABLE,
        "SPARKPILOT_CUR_ATHENA_WORKGROUP": CUR_ATHENA_WORKGROUP,
        "SPARKPILOT_CUR_ATHENA_OUTPUT_LOCATION": CUR_ATHENA_OUTPUT_LOCATION,
        "SPARKPILOT_CUR_RUN_ID_COLUMN": "resource_tags_user_sparkpilot_run_id",
        "SPARKPILOT_CUR_COST_COLUMN": "line_item_unblended_cost",
        "AWS_PAGER": "",
        "AWS_DEFAULT_REGION": AWS_REGION,
    }


def _get_token() -> str:
    """Fetch OIDC token from mock OIDC server."""
    resp = httpx.post(
        f"{OIDC_ISSUER}/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": OIDC_CLIENT_ID,
            "client_secret": OIDC_CLIENT_SECRET,
            "audience": OIDC_AUDIENCE,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _api_request(method: str, path: str, *, token: str, json_body: Any = None, params: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.request(
        method,
        f"{API_BASE_URL}{path}",
        headers=headers,
        json=json_body,
        params=params,
        timeout=30,
    )
    if not resp.is_success:
        log.error("API %s %s → %s: %s", method, path, resp.status_code, resp.text[:500])
    resp.raise_for_status()
    return resp.json()


def _aws_cmd(args: list[str]) -> dict:
    result = _run_cmd(
        ["aws"] + args + ["--output", "json", "--region", AWS_REGION],
        capture=True,
    )
    return json.loads(result.stdout)


def _scale_nodegroup(desired: int) -> None:
    log.info("Scaling nodegroup %s to desiredSize=%d", NODEGROUP_NAME, desired)
    _run_cmd([
        "aws", "eks", "update-nodegroup-config",
        "--cluster-name", EKS_CLUSTER_NAME,
        "--nodegroup-name", NODEGROUP_NAME,
        "--scaling-config", f"minSize=0,maxSize=4,desiredSize={desired}",
        "--region", AWS_REGION,
        "--output", "json",
    ])


def _wait_nodes_ready(count: int, max_wait_seconds: int = 600) -> bool:
    log.info("Waiting for %d nodes to be Ready...", count)
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        try:
            result = _run_cmd(
                ["kubectl", "get", "nodes", "--no-headers", "-o", "custom-columns=STATUS:.status.conditions[-1].type"],
                capture=True,
                check=False,
            )
            ready_count = result.stdout.strip().count("Ready")
            log.info("Nodes ready: %d / %d", ready_count, count)
            if ready_count >= count:
                return True
        except Exception as exc:
            log.warning("kubectl check failed (will retry): %s", exc)
        time.sleep(30)
    return False


def _wait_emr_terminal(emr_run_id: str, max_wait_seconds: int = 1200) -> dict:
    log.info("Waiting for EMR job run %s to reach terminal state...", emr_run_id)
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        result = _aws_cmd([
            "emr-containers", "describe-job-run",
            "--virtual-cluster-id", VIRTUAL_CLUSTER_ID,
            "--id", emr_run_id,
        ])
        job_run = result.get("jobRun", {})
        state = job_run.get("state", "UNKNOWN")
        state_details = job_run.get("stateDetails", "")
        log.info("EMR state: %s | details: %s", state, state_details[:100] if state_details else "")
        if state in EMR_TERMINAL_STATES:
            return job_run
        time.sleep(30)
    log.warning("Timed out waiting for EMR terminal state")
    return {}


def _wait_run_terminal(run_id: str, token: str, max_wait_seconds: int = 1200) -> dict:
    log.info("Waiting for SparkPilot run %s to reach terminal state...", run_id)
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        run = _api_request("GET", f"/v1/runs/{run_id}", token=token)
        state = run.get("state", "unknown")
        log.info("SparkPilot run state: %s", state)
        if state in TERMINAL_STATES:
            return run
        time.sleep(30)
    log.warning("Timed out waiting for SparkPilot terminal state")
    return {}


def _run_cur_reconciliation(run_ids: list[str]) -> str:
    """Run CUR reconciliation and return output."""
    log.info("Running CUR reconciliation for run IDs: %s", run_ids)
    env = _base_env()
    result = _run_cmd(
        [str(VENV_PYTHON), "-m", "sparkpilot.workers", "cur-reconciliation", "--once"],
        env=env,
        capture=True,
        check=False,
    )
    output = result.stdout + result.stderr
    log.info("CUR reconciliation output:\n%s", output)
    return output


def _write_artifact(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data, indent=2, default=str))
    else:
        path.write_text(str(data))
    log.info("Wrote artifact: %s", path)


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------

def main(dry_run: bool = False) -> int:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    evidence_dir = REPO_ROOT / "artifacts" / f"p0-evidence-{ts}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log.info("Evidence directory: %s", evidence_dir)

    idempotency_key = f"p0-minimal-run-{ts}"

    # -----------------------------------------------------------------------
    # Step 1: Start mock OIDC (if not already running)
    # -----------------------------------------------------------------------
    log.info("=== Step 1: Checking mock OIDC ===")
    oidc_proc = None
    try:
        resp = httpx.get(f"{OIDC_ISSUER}/healthz", timeout=3)
        if resp.is_success:
            log.info("Mock OIDC already running at %s", OIDC_ISSUER)
    except Exception:
        log.info("Starting mock OIDC server...")
        env = _base_env()
        env.update({
            "MOCK_OIDC_ISSUER": OIDC_ISSUER,
            "MOCK_OIDC_AUDIENCE": OIDC_AUDIENCE,
            "MOCK_OIDC_PORT": "8080",
        })
        oidc_proc = subprocess.Popen(
            [str(VENV_PYTHON), "-m", "sparkpilot.mock_oidc"],
            env={**os.environ, **env},
            cwd=str(REPO_ROOT),
        )
        time.sleep(3)

    # -----------------------------------------------------------------------
    # Step 2: Start SparkPilot API (if not already running)
    # -----------------------------------------------------------------------
    log.info("=== Step 2: Checking SparkPilot API ===")
    api_proc = None
    try:
        resp = httpx.get(f"{API_BASE_URL}/healthz", timeout=3)
        if resp.is_success:
            log.info("SparkPilot API already running at %s", API_BASE_URL)
    except Exception:
        log.info("Starting SparkPilot API...")
        env = _base_env()
        api_proc = subprocess.Popen(
            [str(VENV_PYTHON), "-m", "uvicorn", "sparkpilot.api:app",
             "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
            env={**os.environ, **env},
            cwd=str(REPO_ROOT),
        )
        # Wait for API to be ready
        for attempt in range(20):
            time.sleep(2)
            try:
                resp = httpx.get(f"{API_BASE_URL}/healthz", timeout=3)
                if resp.is_success:
                    log.info("API ready after %d attempts", attempt + 1)
                    break
            except Exception:
                pass
        else:
            log.error("API failed to start")
            return 1

    # -----------------------------------------------------------------------
    # Step 3: Start workers (scheduler + reconciler)
    # -----------------------------------------------------------------------
    log.info("=== Step 3: Starting workers ===")
    env = _base_env()
    scheduler_proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "sparkpilot.workers", "scheduler"],
        env={**os.environ, **env},
        cwd=str(REPO_ROOT),
    )
    reconciler_proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "sparkpilot.workers", "reconciler"],
        env={**os.environ, **env},
        cwd=str(REPO_ROOT),
    )
    time.sleep(2)

    try:
        # -----------------------------------------------------------------------
        # Step 4: Get auth token
        # -----------------------------------------------------------------------
        log.info("=== Step 4: Getting auth token ===")
        token = _get_token()
        log.info("Got OIDC token (sub=service:%s)", OIDC_CLIENT_ID)

        # -----------------------------------------------------------------------
        # Step 5: Submit minimal-resource job
        # -----------------------------------------------------------------------
        log.info("=== Step 5: Submitting minimal-resource SparkPi job ===")
        run_payload = {
            "spark_conf": MINIMAL_SPARK_CONF,
            "requested_resources": MINIMAL_RESOURCES,
            "timeout_seconds": 900,  # 15 min — enough for SparkPi, not too long
        }
        log.info("Run payload: %s", json.dumps(run_payload, indent=2))

        run_resp = _api_request(
            "POST",
            f"/v1/jobs/{SPARKPI_JOB_ID}/runs",
            token=token,
            json_body=run_payload,
            params=None,
        )
        run_id = run_resp["id"]
        log.info("Submitted run: %s (state=%s)", run_id, run_resp.get("state"))
        _write_artifact(evidence_dir / "run_submission.json", run_resp)

        # -----------------------------------------------------------------------
        # Step 6: Scale up nodes
        # -----------------------------------------------------------------------
        log.info("=== Step 6: Scaling EKS nodegroup to 2 nodes ===")
        if not dry_run:
            _scale_nodegroup(2)
            nodes_ready = _wait_nodes_ready(2, max_wait_seconds=600)
            if not nodes_ready:
                log.warning("Nodes may not be fully ready, continuing anyway...")
        else:
            log.info("[DRY RUN] Would scale nodegroup to 2")

        # -----------------------------------------------------------------------
        # Step 7: Wait for SparkPilot run to reach terminal state
        # -----------------------------------------------------------------------
        log.info("=== Step 7: Waiting for run terminal state ===")
        terminal_run = _wait_run_terminal(run_id, token, max_wait_seconds=1200)
        if not terminal_run:
            # Get current state
            terminal_run = _api_request("GET", f"/v1/runs/{run_id}", token=token)

        log.info("Terminal run state: %s", terminal_run.get("state"))
        log.info("EMR job run ID: %s", terminal_run.get("emr_job_run_id"))
        _write_artifact(evidence_dir / "run_terminal_state.json", terminal_run)

        # -----------------------------------------------------------------------
        # Step 8: Check real EMR state
        # -----------------------------------------------------------------------
        emr_run_id = terminal_run.get("emr_job_run_id")
        emr_state_data = {}
        if emr_run_id:
            log.info("=== Step 8: Checking real EMR state for %s ===", emr_run_id)
            try:
                emr_state_data = _aws_cmd([
                    "emr-containers", "describe-job-run",
                    "--virtual-cluster-id", VIRTUAL_CLUSTER_ID,
                    "--id", emr_run_id,
                ])
                job_run = emr_state_data.get("jobRun", {})
                log.info("EMR state: %s", job_run.get("state"))
                log.info("EMR stateDetails: %s", job_run.get("stateDetails", "")[:200])
                _write_artifact(evidence_dir / "emr_job_run.json", emr_state_data)
            except Exception as exc:
                log.warning("Could not fetch EMR state: %s", exc)

        # -----------------------------------------------------------------------
        # Step 9: CUR reconciliation
        # -----------------------------------------------------------------------
        log.info("=== Step 9: CUR reconciliation ===")
        cur_output = _run_cur_reconciliation([run_id])
        _write_artifact(evidence_dir / "cur_reconcile_output.txt", cur_output)

        # Get updated cost allocation
        try:
            import sqlite3
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cost_rows = conn.execute(
                "SELECT * FROM cost_allocations WHERE run_id = ?", (run_id,)
            ).fetchall()
            cost_data = [dict(r) for r in cost_rows]
            _write_artifact(evidence_dir / "cost_allocation_after_reconcile.json", cost_data)
            log.info("Cost allocation: %s", cost_data)
        except Exception as exc:
            log.warning("Could not read cost allocation: %s", exc)

        # Showback response
        try:
            tenant_id = "89b43f2d-2a48-4be6-9723-9732b0df8223"
            showback = _api_request(
                "GET",
                f"/v1/costs/showback",
                token=token,
                params={"team": tenant_id, "period": "2026-03"},
            )
            _write_artifact(evidence_dir / "showback_response.json", showback)
        except Exception as exc:
            log.warning("Could not fetch showback: %s", exc)

        # -----------------------------------------------------------------------
        # Step 10: Write evidence summary
        # -----------------------------------------------------------------------
        final_state = terminal_run.get("state", "unknown")
        emr_final_state = emr_state_data.get("jobRun", {}).get("state", "unknown") if emr_state_data else "unknown"
        emr_state_details = emr_state_data.get("jobRun", {}).get("stateDetails", "") if emr_state_data else ""

        summary = {
            "timestamp": ts,
            "run_id": run_id,
            "job_id": SPARKPI_JOB_ID,
            "emr_job_run_id": emr_run_id,
            "emr_virtual_cluster_id": VIRTUAL_CLUSTER_ID,
            "sparkpilot_final_state": final_state,
            "emr_final_state": emr_final_state,
            "emr_state_details": emr_state_details,
            "spark_conf_overrides": MINIMAL_SPARK_CONF,
            "requested_resources": MINIMAL_RESOURCES,
            "cur_reconcile_executed": True,
            "evidence_dir": str(evidence_dir),
        }
        _write_artifact(evidence_dir / "summary.json", summary)

        log.info("=== SUMMARY ===")
        log.info("SparkPilot final state: %s", final_state)
        log.info("EMR final state: %s", emr_final_state)
        log.info("EMR stateDetails: %s", emr_state_details[:200] if emr_state_details else "none")
        log.info("Evidence dir: %s", evidence_dir)

    finally:
        # -----------------------------------------------------------------------
        # Step 11: Scale nodes back to 0
        # -----------------------------------------------------------------------
        log.info("=== Step 11: Scaling nodes back to 0 ===")
        if not dry_run:
            try:
                _scale_nodegroup(0)
                log.info("Nodegroup scaled to 0")
            except Exception as exc:
                log.error("Failed to scale down nodegroup: %s", exc)

        # Terminate background processes
        for proc_name, proc in [("scheduler", scheduler_proc), ("reconciler", reconciler_proc)]:
            if proc and proc.poll() is None:
                log.info("Terminating %s worker", proc_name)
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

        if api_proc and api_proc.poll() is None:
            log.info("Terminating API")
            api_proc.terminate()

        if oidc_proc and oidc_proc.poll() is None:
            log.info("Terminating mock OIDC")
            oidc_proc.terminate()

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Skip AWS node scaling")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
