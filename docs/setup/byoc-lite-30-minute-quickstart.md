# BYOC-lite 30-Minute Quickstart

Get your first Spark run on SparkPilot using an existing EKS cluster.

## Prerequisites

1. Python environment with project dependencies installed.
2. Access to SparkPilot API endpoint.
3. OIDC client credentials for API token minting:
   - `OIDC_ISSUER`
   - `OIDC_AUDIENCE`
   - `OIDC_CLIENT_ID`
   - `OIDC_CLIENT_SECRET`
4. AWS assets:
   - customer role ARN trusted for SparkPilot
   - EKS cluster ARN
   - dedicated namespace

## Step 1: Verify AWS and API Access (5 min)

**macOS / Linux:**

```bash
aws sts get-caller-identity
python -m scripts.smoke.live_byoc_lite --help
```

**Windows (PowerShell):**

```powershell
python -m awscli sts get-caller-identity
python -m scripts.smoke.live_byoc_lite --help
```

## Step 2: Run Live BYOC-lite Smoke (10-15 min)

**macOS / Linux:**

```bash
python -m scripts.smoke.live_byoc_lite \
  --base-url http://127.0.0.1:8000 \
  --oidc-issuer "$OIDC_ISSUER" \
  --oidc-audience "$OIDC_AUDIENCE" \
  --oidc-client-id "$OIDC_CLIENT_ID" \
  --oidc-client-secret "$OIDC_CLIENT_SECRET" \
  --customer-role-arn arn:aws:iam::<account-id>:role/SparkPilotByocLiteRoleAdmin \
  --eks-cluster-arn arn:aws:eks:us-east-1:<account-id>:cluster/sparkpilot-live-1 \
  --eks-namespace sparkpilot-quickstart \
  --region us-east-1
```

**Windows (PowerShell):**

```powershell
python -m scripts.smoke.live_byoc_lite `
  --base-url http://127.0.0.1:8000 `
  --oidc-issuer $env:OIDC_ISSUER `
  --oidc-audience $env:OIDC_AUDIENCE `
  --oidc-client-id $env:OIDC_CLIENT_ID `
  --oidc-client-secret $env:OIDC_CLIENT_SECRET `
  --customer-role-arn arn:aws:iam::<account-id>:role/SparkPilotByocLiteRoleAdmin `
  --eks-cluster-arn arn:aws:eks:us-east-1:<account-id>:cluster/sparkpilot-live-1 `
  --eks-namespace sparkpilot-quickstart `
  --region us-east-1
```

## Step 3: Validate in the UI (5 min)

1. Open `/environments` and confirm environment status is `ready`.
2. Open `/runs`, run preflight, submit one run, and open logs.
3. Use [Job template + run fields (demo-safe)](./job-template-and-run-fields.md) for exact values.
4. Open `/costs` and load usage/showback for the tenant.

## Step 4: Review Results (5 min)

1. Confirm the run reached terminal `succeeded` state.
2. Verify preflight checks are visible in the API and UI.
3. Confirm run logs are retrievable from the logs viewer.
4. Verify cost/usage data appears for the tenant.
