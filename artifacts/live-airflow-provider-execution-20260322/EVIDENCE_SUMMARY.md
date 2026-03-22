# Issue #36 — Airflow Provider Real Scheduler Execution

**Date:** 2026-03-22
**Status:** PARTIAL — Provider runs against live API; full Airflow scheduler execution blocked (no local Airflow scheduler)

## What Ran Live

### SparkPilotSubmitRunOperator executed against live SparkPilot API

The operator was invoked via `SparkPilotSubmitRunOperator.execute()` directly (no Airflow scheduler), connected to the live API at `http://localhost:8000`.

**Run submitted:**
- Run ID: `1ca72ab4-f067-45f1-bbbc-6efc3726cc03`
- Job ID: `dd87754d-bbef-45fb-bf84-e6686c4b990e`
- Idempotency key: `airflow-evidence-run-20260322a`
- Environment: `69be1cb6-1cfd-45dc-a1de-4345f612001e` (EKS sparkpilot-live-1)
- EMR Job Run ID: `0000000378n4ub5e3i6`

**Operator behavior:**
1. POST to `/v1/jobs/{job_id}/runs` → 201 Created → run_id = `1ca72ab4`
2. Polled GET `/v1/runs/1ca72ab4` every 15 seconds
3. Initial 30-minute wait_timeout triggered `SparkPilotTransientError`
4. Second invocation (idempotency key returned same run) immediately detected failed state
5. Raised `AirflowFailException` as expected for a failed run

**Run terminal state:** `failed` (EMR job ran on live cluster, failed with USER_ERROR — artifact not in S3)

## Blocker

A running Airflow **scheduler** is required for:
- DAG import and registration
- DAG trigger via API (`POST /api/v1/dags/{dag_id}/dagRuns`)
- Task instance log capture with Airflow run IDs

The `providers/airflow/docker-compose.integration.yml` has a complete integration test harness.

## Evidence Files

| File | Description |
|------|-------------|
| `dag_definition.py` | Test DAG definition |
| `dag_run_response.json` | Operator execution result |
| `task_log_tail.txt` | HTTP interaction logs |
| `sparkpilot_run_id.txt` | SparkPilot run_id = `1ca72ab4-f067-45f1-bbbc-6efc3726cc03` |
| `BLOCKER.md` | Infrastructure requirements for full scheduler execution |
