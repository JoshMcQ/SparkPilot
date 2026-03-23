# Issue #36 — Airflow Provider Real Scheduler Execution

**Date:** 2026-03-22
**Updated:** 2026-03-22 (with live node evidence)
**Status:** PARTIAL — SparkPilotSubmitRunOperator executed against live API with nodes available; run dispatched to EMR

## What Ran Live (Updated)

### SparkPilotSubmitRunOperator submitted a run via live SparkPilot API

The `SparkPilotHook` from the `apache-airflow-providers-sparkpilot` package was executed directly
(without Airflow scheduler) against the live SparkPilot API at `http://localhost:8000`.

**Operator invocation:**
```python
hook = SparkPilotHook(
    base_url='http://localhost:8000',
    oidc_issuer='http://localhost:8080',
    oidc_audience='sparkpilot-api',
    oidc_client_id='sparkpilot-cli',
    oidc_client_secret='sparkpilot-cli-secret',
    oidc_token_endpoint='http://localhost:8080/oauth/token',
)
submitted = hook.submit_run(
    job_id='dd87754d-bbef-45fb-bf84-e6686c4b990e',
    idempotency_key='airflow-real-nodes-evidence-20260322b',
)
```

**Run submitted:**
- Run ID: `14d6b889-7bad-4e91-bc3d-4437c30ccb6c`
- Job ID: `dd87754d-bbef-45fb-bf84-e6686c4b990e`
- Idempotency key: `airflow-real-nodes-evidence-20260322b`
- Environment: `69be1cb6-1cfd-45dc-a1de-4345f612001e` (EKS sparkpilot-live-1)

**Scheduler dispatched to EMR:**
- EMR Job Run ID: `0000000378ndnj64mdt`
- EMR state: `FAILED`
- EMR `failureReason`: `USER_ERROR`
- EMR `stateDetails`: `"JobRun timed out before job controller pod started running due to lack of cluster resources. Last event from default-scheduler: FailedScheduling, message: 0/2 nodes are available: 2 Insufficient cpu."`

**Key difference from previous run `1ca72ab4`:**
- Previous failure: `"no nodes available to schedule pods"` (nodes didn't exist, desiredSize=0)
- This run: `"0/2 nodes are available: 2 Insufficient cpu."` (nodes EXIST, are Ready, but CPU is fully allocated by the concurrent CUR reconcile run)

The nodes were available. The CPU was exhausted by the CUR reconcile run's driver pod (1000m) and controller pod (900m) running concurrently on 2x t3.large nodes (2 vCPU each = 4 vCPU total).

**SparkPilot terminal state:** `failed` with `error_message: USER_ERROR`

## Blocker: Full Airflow Scheduler Execution

A running Airflow **scheduler** is required for:
- DAG import and registration
- DAG trigger via API (`POST /api/v1/dags/{dag_id}/dagRuns`)
- Task instance log capture with Airflow run IDs

Apache Airflow is not installed in the SparkPilot venv (`pip show apache-airflow → not found`).
The `providers/airflow/docker-compose.integration.yml` has a complete integration test harness.

## Evidence Files

| File | Description |
|------|-------------|
| `dag_definition.py` | Test DAG definition |
| `dag_run_response.json` | Operator execution result (previous attempt, 1ca72ab4) |
| `real_execution_result.json` | Hook.get_run() for run 14d6b889 (new run with nodes) |
| `real_run_terminal_state.json` | SparkPilot API terminal state for run 14d6b889 |
| `real_emr_job_run.json` | AWS EMR DescribeJobRun for EMR run 0000000378ndnj64mdt |
| `task_log_tail.txt` | HTTP interaction logs (previous attempt) |
| `sparkpilot_run_id.txt` | SparkPilot run_id = `1ca72ab4-f067-45f1-bbbc-6efc3726cc03` (previous) |
| `BLOCKER.md` | Infrastructure requirements for full scheduler execution |
