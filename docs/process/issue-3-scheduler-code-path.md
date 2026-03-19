# Issue #3 — Scheduler `StartJobRun` Code Path Map

Date: 2026-03-18

## Objective

Map the exact dispatch path used by scheduler workers and identify where AWS `StartJobRun` is actually invoked.

## Code Path (current)

1. **Batch loop entrypoint**
   - `src/sparkpilot/services/workers_scheduling.py:154`
   - Function: `process_scheduler_once(db, actor="worker:scheduler", limit=20)`
   - Claims queued runs (`_claim_runs`) and iterates each run.

2. **Preflight gate before dispatch**
   - `src/sparkpilot/services/workers_scheduling.py:173-205`
   - Calls `_build_preflight_cached(env, run_id=run.id, spark_conf=..., db=db)`.
   - If `preflight["ready"]` is false, run is failed and dispatch is skipped.

3. **Dispatch transition**
   - `src/sparkpilot/services/workers_scheduling.py:207-209`
   - Sets `run.state = "dispatching"` then calls `dispatch = _dispatch_run(env, job, run)`.

4. **Engine router**
   - `src/sparkpilot/services/workers_scheduling.py:91-125`
   - `_dispatch_run(...)` routes by `env.engine`:
     - `emr_on_eks` → `EmrEksClient().start_job_run(env, job, run)` (`line 98`)
     - `emr_serverless` → `EmrServerlessClient().start_job_run(...)` (`line 100`)
     - `emr_on_ec2` → `EmrEc2Client().start_job_run(...)` (`line 102`)
     - `databricks` → `DatabricksClient.submit_run(...)` (`lines 103-124`, not AWS StartJobRun)

5. **Actual EMR on EKS AWS API call (`StartJobRun`)**
   - `src/sparkpilot/aws_clients.py:1231` (`EmrEksClient.start_job_run`)
   - AWS call site: `src/sparkpilot/aws_clients.py:1280`
   - Statement: `client.start_job_run(...)`
   - Client type: `session.client("emr-containers", region_name=environment.region)`.

## Dispatch Result Writeback

- `src/sparkpilot/services/workers_scheduling.py:128-151`
- `_apply_dispatch_result(...)` maps backend result IDs onto `Run`:
  - EMR on EKS: `run.emr_job_run_id` + `run.backend_job_run_id` from dispatch result.

## Integration Point for Issue #3

The strongest gating point remains **inside `process_scheduler_once` before line 207** (before `_dispatch_run`), because that blocks all engines consistently and prevents `client.start_job_run(...)` from being called when IAM/IRSA preflight fails.
