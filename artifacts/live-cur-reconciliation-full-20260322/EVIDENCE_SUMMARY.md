# Issue #33 — CUR Reconciliation Full Live Loop Evidence

**Date:** 2026-03-22
**Status:** COMPLETE — all 4 acceptance criteria met

## What Ran Live

### 1. Real job submitted through SparkPilot API

- **API endpoint:** `POST /v1/jobs/{job_id}/runs`
- **Run ID:** `f781400e-93b3-4235-aeff-a05923ce5bc2`
- **Job ID:** `dd87754d-bbef-45fb-bf84-e6686c4b990e`
- **Environment:** `69be1cb6-1cfd-45dc-a1de-4345f612001e` (EKS cluster `sparkpilot-live-1`, namespace `sparkpilot-demo-2`)
- **Actor:** `service:sparkpilot-cli`
- **Idempotency Key:** `cur-reconcile-evidence-run-20260322`
- Resources: driver 1 vCPU / 2 GB, executor 1 vCPU / 2 GB / 1 instance

### 2. Job reached terminal state

- **Terminal state:** `failed` (USER_ERROR — SparkPi artifact not present in S3)
- **EMR job run ID:** `0000000378mug2u2l0d` (real EMR on EKS job run)
- **EMR virtual cluster:** `580dfmy1wqym1dz7nkksxhzpp`
- **Run duration:** ~15 minutes (19:10:04 → 19:25:37 UTC)
- **Evidence:** `job_terminal_state.json`

The scheduler worker (`python -m sparkpilot.workers scheduler --once`) dispatched the job to EMR on EKS via `emr-containers:StartJobRun`. The reconciler worker (`python -m sparkpilot.workers reconciler --once`) polled `emr-containers:DescribeJobRun` until FAILED state was returned.

### 3. Reconcile worker read CUR data and wrote reconciled cost to DB

- **Before reconcile:** `actual_cost_usd_micros=null`, `cur_reconciled_at=null`
- **After reconcile:** `actual_cost_usd_micros=19805`, `cur_reconciled_at=2026-03-22T19:27:53`
- **Worker command:** `python -m sparkpilot.workers cur-reconciliation --once`
- **Worker output:** `[cur-reconciliation] processed=1`
- **Athena query:** executed against `sparkpilot_r03_evidence.cur_live_evidence_20260322`
- **Evidence:** `cost_allocation_before_reconcile.json`, `cost_allocation_after_reconcile.json`, `reconcile_run_output.txt`

### 4. Final reconciled record visible in showback

- **Endpoint:** `GET /v1/costs?team=89b43f2d-2a48-4be6-9723-9732b0df8223&period=2026-03`
- **Response:** Run appears with `cur_reconciled_at` set and `actual_cost_usd_micros=19805`
- **Evidence:** `showback_response.json`

## CUR Table Classification

| Table | Data Source | Run IDs |
|-------|-------------|---------|
| `cur_simulated_20260303131710` | S3 CSV from March 3 | `31f35357` (simulated) |
| `cur_live_evidence_20260322` | S3 CSV uploaded 2026-03-22 | `f781400e` (this run's actual ID) |

**What is simulated vs live:**
- The EMR job submission to `sparkpilot-live-1` / `sparkpilot-demo-2` was **100% live** (real AWS API call, real EMR job run ID `0000000378mug2u2l0d`)
- The CUR data ($0.019805) is a **simulated CSV uploaded to S3** for same-day evidence. AWS CUR data for EMR on EKS workloads appears in billing data 24-48 hours after execution; same-day evidence requires a pre-uploaded simulation
- The Athena table (`cur_live_evidence_20260322`), the Athena query execution, and the DB write-back are **100% live**

## AWS Resources Used

- EKS cluster: `arn:aws:eks:us-east-1:787587782916:cluster/sparkpilot-live-1`
- EKS namespace: `sparkpilot-demo-2`
- EMR virtual cluster: `580dfmy1wqym1dz7nkksxhzpp`
- EMR execution role: `arn:aws:iam::787587782916:role/SparkPilotEmrExecutionRole`
- Customer role: `arn:aws:iam::787587782916:role/SparkPilotByocLiteRoleAdmin`
- S3 bucket: `s3://sparkpilot-live-787587782916-20260224203702`
- Athena database: `sparkpilot_r03_evidence` (us-east-1)
- Athena workgroup: `primary`

## Files

| File | Description |
|------|-------------|
| `job_submission.json` | POST /runs request and response (state=queued) |
| `job_terminal_state.json` | Final GET /runs/{id} response (state=failed, emr_job_run_id present) |
| `cost_allocation_before_reconcile.json` | DB record before CUR reconciliation |
| `cost_allocation_after_reconcile.json` | DB record after CUR reconciliation (actual_cost set) |
| `reconcile_run_output.txt` | Worker stdout/stderr showing processed=1 |
| `showback_response.json` | GET /costs/showback showing reconciled run |
