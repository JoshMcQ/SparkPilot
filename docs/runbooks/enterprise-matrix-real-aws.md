# Enterprise Matrix Real-AWS Runbook

Run a broad scenario matrix against a live SparkPilot deployment with explicit spend controls and evidence artifacts.

## What This Covers

- Spot baseline submissions
- Golden path and Graviton profile checks
- Policy and budget preflight blocking
- CUR showback capture
- Moderate load burst validation
- Manual evidence checkpoints for integrations that are not API-only

## Prerequisites

1. SparkPilot API and workers are running against a shared database.
2. `SPARKPILOT_DRY_RUN_MODE=false` in API and workers for real AWS dispatch.
3. Valid BYOC-lite IAM/EKS/EMR wiring is complete.
4. OIDC client-credentials auth is configured for the matrix runner.
5. You reviewed estimated spend and set strict caps.

## Step 1: Prepare Manifest

Use the example as a starting point:

- `docs/validation/enterprise-scenario-matrix.example.json`

Copy it and set real values:

- `customer_role_arn`
- `eks_cluster_arn`
- `eks_namespace`
- artifact details for workload under test

Tip: keep resources small and timeouts short for early validation slices.

## Step 2: Execute Matrix With Cost Caps

```powershell
python scripts/e2e/run_enterprise_matrix.py `
  --manifest docs/validation/enterprise-scenario-matrix.example.json `
  --base-url http://127.0.0.1:8000 `
  --oidc-issuer $env:OIDC_ISSUER `
  --oidc-audience $env:OIDC_AUDIENCE `
  --oidc-client-id $env:OIDC_CLIENT_ID `
  --oidc-client-secret $env:OIDC_CLIENT_SECRET `
  --oidc-token-endpoint $env:OIDC_TOKEN_ENDPOINT `
  --actor matrix-admin `
  --max-estimated-cost-usd 8 `
  --max-scenario-cost-usd 3 `
  --poll-seconds 20 `
  --wait-timeout-seconds 3600
```

Behavior:

- If total estimated spend exceeds `--max-estimated-cost-usd`, execution fails fast.
- If any single scenario estimate exceeds `--max-scenario-cost-usd`, execution fails fast.
- Use `--allow-over-budget` only for intentionally approved overspend runs.

## Step 3: Review Artifacts

The runner writes a timestamped directory:

- `artifacts/enterprise-matrix-<timestamp>/summary.json`
- `artifacts/enterprise-matrix-<timestamp>/resolved-manifest.json`
- `artifacts/enterprise-matrix-<timestamp>/<scenario>-<iteration>.json`

Use `summary.json` as issue evidence and attach scenario JSON files where needed.

## Artifact Schema Notes (v2)

`summary.json` now includes:

- `unexpected_failures`
- `expected_block_events`
- `coverage_gaps`

These fields are designed to separate true regressions from expected guardrail behavior and missing non-API evidence.

## Cost Hygiene

- Start with the smallest scenario subset (set `repeat` low).
- Keep `timeout_seconds` tight.
- Use both global and per-scenario cost caps on every run.
- Scale EKS nodegroups down when done.
- Delete temporary namespaces/resources after validation.

## Notes on "Every Scenario"

Some roadmap items are not purely API-call validations (for example Dagster, Lake Formation FGAC, interactive endpoints, YuniKorn).
For these, keep scenario entries with `submit_run=false` and provide concrete links under `required_external_evidence`.
