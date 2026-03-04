# Enterprise Matrix Real-AWS Runbook

Run a broad scenario matrix against a live SparkPilot deployment with explicit spend controls and evidence artifacts.

## What This Covers

- Spot baseline submissions
- Golden path + Graviton profile checks
- Policy/budget preflight blocking
- CUR/showback capture
- Moderate load burst validation
- Manual evidence checkpoints for integrations that are not API-only

## Prerequisites

1. SparkPilot API and workers are running against a shared database.
2. `SPARKPILOT_DRY_RUN_MODE=false` in API + workers for real AWS dispatch.
3. Valid BYOC-Lite IAM/EKS/EMR wiring is complete.
4. A bearer token is configured for API auth.
5. You have reviewed the matrix estimate and set a strict cost cap.

## Step 1: Prepare Manifest

Use the example as a starting point:

- `docs/validation/enterprise-scenario-matrix.example.json`

Copy it and set real values:

- `customer_role_arn`
- `eks_cluster_arn`
- `eks_namespace`
- artifact details for your workload

Tip: keep resources small and timeout short for early validation cycles.

## Step 2: Execute Matrix With Cost Cap

```powershell
python scripts/e2e/run_enterprise_matrix.py `
  --manifest docs/validation/enterprise-scenario-matrix.example.json `
  --base-url http://127.0.0.1:8000 `
  --token <api-token> `
  --actor matrix-admin `
  --max-estimated-cost-usd 8 `
  --poll-seconds 20 `
  --wait-timeout-seconds 3600
```

If estimated spend exceeds the cap, the run is blocked by default.

## Step 3: Review Artifacts

The runner writes a timestamped directory:

- `artifacts/enterprise-matrix-<timestamp>/summary.json`
- `artifacts/enterprise-matrix-<timestamp>/resolved-manifest.json`
- `artifacts/enterprise-matrix-<timestamp>/<scenario>-<iteration>.json`

Use `summary.json` as issue evidence and attach scenario JSON files where needed.

## Cost Hygiene

- Start with the smallest scenario subset (set `repeat` low).
- Keep `timeout_seconds` tight.
- Use `max_estimated_cost_usd` for every run.
- Scale EKS nodegroups to zero when done.
- Delete temporary namespaces/resources after validation.

## Notes on “Every Scenario”

Some roadmap items are not purely API-call validations (for example Dagster, Lake Formation FGAC, interactive endpoints, YuniKorn).  
For these, keep scenario entries with `submit_run=false` and add concrete artifact links under `required_external_evidence`.
