# Issue #46 — Dagster Real Orchestrator Run

**Date:** 2026-03-22
**Updated:** 2026-03-22 (with live node evidence)
**Status:** PARTIAL — SparkPilotClient called live API with nodes available; run dispatched to EMR

## What Ran Live (Updated)

The `SparkPilotClient` from `dagster-sparkpilot 0.1.0` was executed directly against the live SparkPilot API.

**Client invocation:**
```python
config = SparkPilotClientConfig(
    base_url='http://localhost:8000',
    oidc_issuer='http://localhost:8080',
    oidc_audience='sparkpilot-api',
    oidc_client_id='sparkpilot-cli',
    oidc_client_secret='sparkpilot-cli-secret',
    oidc_token_endpoint='http://localhost:8080/oauth/token',
)
client = SparkPilotClient(config)
submitted = client.submit_run(
    job_id='dd87754d-bbef-45fb-bf84-e6686c4b990e',
    idempotency_key='dagster-real-nodes-evidence-20260322a',
)
```

**Run submitted:**
- Run ID: `3a808369-f338-4d2e-9342-fb667a851992`
- Job ID: `dd87754d-bbef-45fb-bf84-e6686c4b990e`
- Idempotency key: `dagster-real-nodes-evidence-20260322a`
- Environment: `69be1cb6-1cfd-45dc-a1de-4345f612001e` (EKS sparkpilot-live-1)
- Submitted via: `SparkPilotClient.submit_run()` against `http://localhost:8000`

**Scheduler dispatched to EMR:**
- EMR Job Run ID: `0000000378ndnln0oek`
- EMR state: `FAILED`
- EMR `failureReason`: `USER_ERROR`
- EMR `stateDetails`: `"JobRun timed out before job controller pod started running due to lack of cluster resources. Last event from default-scheduler: FailedScheduling, message: 0/2 nodes are available: 2 Insufficient cpu."`

**Key difference from previous run `10f788e5`:**
- Previous failure: `"no nodes available to schedule pods"` (nodes didn't exist, desiredSize=0)
- This run: `"0/2 nodes are available: 2 Insufficient cpu."` (nodes EXIST, are Ready, but CPU is fully allocated)

The nodes were available. The CPU was exhausted by the concurrent CUR reconcile run's driver (1000m) and controller (900m) pods running on 2x t3.large nodes (4 vCPU total).

**SparkPilot terminal state:** `failed` with `error_message: USER_ERROR`

## Blocker: Full Dagster Orchestrator Execution

Dagster is not installed in the SparkPilot venv (`pip show dagster → not found`).
The `dagster_sparkpilot` package's client and resource layers work without Dagster,
but the `@op`, `@asset`, and `@resource` decorators require Dagster installed.

Full orchestrator run requires `pip install dagster>=1.8.0` and `dagster dev`.

## Files

| File | Description |
|------|-------------|
| `BLOCKER.md` | Infrastructure requirements for full Dagster execution |
| `real_execution_result.json` | SparkPilotClient.get_run() result for run 3a808369 |
| `real_run_terminal_state.json` | SparkPilot API terminal state for run 3a808369 |
| `real_emr_job_run.json` | AWS EMR DescribeJobRun for EMR run 0000000378ndnln0oek |
| `EVIDENCE_SUMMARY.md` | This file |
