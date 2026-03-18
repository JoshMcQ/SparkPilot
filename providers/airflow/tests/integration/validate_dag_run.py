"""Validate an Airflow DAG run completed successfully via the Airflow REST API.

Usage:
    python validate_dag_run.py --dag-id sparkpilot_integration_submit_wait --run-id manual__2026-03-17

Exit codes:
    0 - DAG run succeeded and all task instances succeeded, XCom values present
    1 - Validation failed

Environment variables:
    AIRFLOW_API_BASE_URL     Airflow REST API base URL (e.g. http://localhost:8080)
    AIRFLOW_API_USERNAME     Airflow basic-auth username (default: admin)
    AIRFLOW_API_PASSWORD     Airflow basic-auth password
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import httpx


def _airflow_client() -> httpx.Client:
    base_url = os.getenv("AIRFLOW_API_BASE_URL", "http://localhost:8080").rstrip("/")
    username = os.getenv("AIRFLOW_API_USERNAME", "admin")
    password = os.getenv("AIRFLOW_API_PASSWORD", "")
    return httpx.Client(
        base_url=base_url,
        auth=(username, password),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=30.0,
    )


def _get_dag_run(client: httpx.Client, *, dag_id: str, run_id: str) -> dict:
    response = client.get(f"/api/v1/dags/{dag_id}/dagRuns/{run_id}")
    response.raise_for_status()
    return response.json()


def _get_task_instances(client: httpx.Client, *, dag_id: str, run_id: str) -> list[dict]:
    response = client.get(f"/api/v1/dags/{dag_id}/dagRuns/{run_id}/taskInstances")
    response.raise_for_status()
    data = response.json()
    return data.get("task_instances", [])


def _get_xcom_value(
    client: httpx.Client,
    *,
    dag_id: str,
    run_id: str,
    task_id: str,
    xcom_key: str = "return_value",
) -> object:
    response = client.get(
        f"/api/v1/dags/{dag_id}/dagRuns/{run_id}/taskInstances/{task_id}/xcomEntries/{xcom_key}"
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json().get("value")


def _wait_for_dag_run_completion(
    client: httpx.Client,
    *,
    dag_id: str,
    run_id: str,
    timeout_seconds: int = 600,
    poll_interval_seconds: int = 10,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    terminal_states = {"success", "failed"}
    while True:
        dag_run = _get_dag_run(client, dag_id=dag_id, run_id=run_id)
        state = dag_run.get("state", "")
        if state in terminal_states:
            return dag_run
        if time.monotonic() >= deadline:
            print(f"ERROR: Timed out waiting for DAG run {run_id} (state={state}).")
            sys.exit(1)
        print(f"  DAG run state: {state} — polling again in {poll_interval_seconds}s...")
        time.sleep(poll_interval_seconds)


def _validate(*, dag_id: str, run_id: str, timeout_seconds: int) -> int:
    print(f"Validating DAG run: dag_id={dag_id!r}, run_id={run_id!r}")

    with _airflow_client() as client:
        # Wait for completion
        dag_run = _wait_for_dag_run_completion(
            client,
            dag_id=dag_id,
            run_id=run_id,
            timeout_seconds=timeout_seconds,
        )

        dag_state = dag_run.get("state", "")
        print(f"DAG run terminal state: {dag_state}")
        if dag_state != "success":
            print(f"ERROR: DAG run did not succeed — state={dag_state!r}")
            return 1

        # Verify all task instances succeeded
        task_instances = _get_task_instances(client, dag_id=dag_id, run_id=run_id)
        if not task_instances:
            print("ERROR: No task instances found.")
            return 1

        failed_tasks = [
            ti for ti in task_instances if ti.get("state") != "success"
        ]
        if failed_tasks:
            for ti in failed_tasks:
                print(f"  FAILED task: {ti.get('task_id')} state={ti.get('state')}")
            return 1

        print(f"  All {len(task_instances)} task instance(s) succeeded.")

        # Check XCom on any submit task
        xcom_failures: list[str] = []
        for ti in task_instances:
            task_id = ti.get("task_id", "")
            if "submit" not in task_id:
                continue
            xcom = _get_xcom_value(client, dag_id=dag_id, run_id=run_id, task_id=task_id)
            if xcom is None:
                xcom_failures.append(f"{task_id}: no XCom return_value")
                continue
            if not isinstance(xcom, dict):
                xcom_failures.append(f"{task_id}: XCom is not a dict — {type(xcom).__name__}")
                continue
            run_xcom_id = xcom.get("id")
            if not run_xcom_id:
                xcom_failures.append(f"{task_id}: XCom missing 'id' key")
                continue
            run_xcom_state = xcom.get("status") or xcom.get("state")
            if not run_xcom_state:
                xcom_failures.append(f"{task_id}: XCom missing 'status'/'state' key")
                continue
            print(f"  XCom for {task_id!r}: run_id={run_xcom_id!r}, state={run_xcom_state!r}")

        if xcom_failures:
            print("XCom validation failures:")
            for msg in xcom_failures:
                print(f"  - {msg}")
            return 1

    print("Validation PASSED.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a SparkPilot Airflow integration DAG run.")
    parser.add_argument("--dag-id", required=True, help="Airflow DAG id to validate.")
    parser.add_argument("--run-id", required=True, help="Airflow DAG run id.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Seconds to wait for DAG run completion before failing (default: 600).",
    )
    args = parser.parse_args()
    return _validate(dag_id=args.dag_id, run_id=args.run_id, timeout_seconds=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
