# SparkPilot

SparkPilot is an AWS-first BYOC managed Spark control plane for Kubernetes-native teams.

This repository contains:

- `src/sparkpilot`: FastAPI control-plane API, workers, and shared services
- `providers/airflow`: `apache-airflow-providers-sparkpilot` package (hook/operator/sensor/trigger)
- `ui`: Next.js thin operator UI
- `infra/terraform/control-plane`: Terraform baseline for SparkPilot control plane
- `infra/cloudformation`: Customer bootstrap templates
- `tests`: API and workflow tests
- `scripts/smoke`: Cross-platform app-level smoke automation for BYOC-Lite

## Quick Start

1. Create a Python environment and install dependencies:

```powershell
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -e ".[dev]"
```

2. Start the full local stack in one command (API + OIDC + Postgres + workers + UI):

```powershell
docker compose up --build
```

3. Mint a local user token for RBAC testing (mock OIDC), then paste it into the UI header auth panel:

```powershell
$basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("sparkpilot-cli:sparkpilot-cli-secret"))
$token = Invoke-RestMethod -Method Post -Uri http://localhost:8080/oauth/token -Headers @{ Authorization = "Basic $basic" } -Body @{
  grant_type = "client_credentials"
  audience = "sparkpilot-api"
  subject = "user:demo-admin"
}
$token.access_token
```

4. Run tests:

```powershell
pytest
```

5. Run CLI against local API:

```powershell
sparkpilot --help
```

6. Stop local stack:

```powershell
docker compose down
```

## Database Migrations

SparkPilot now uses Alembic for schema migrations.

For staging/production databases, run:

```powershell
alembic upgrade head
```

In non-dev environments, API startup rejects databases that are not at the Alembic head revision.

## Pricing Estimation

Usage estimates now support live AWS pricing ingestion.

- `SPARKPILOT_PRICING_SOURCE=auto` (default): try AWS Pricing API in live mode, fallback to static env rates.
- `SPARKPILOT_PRICING_SOURCE=aws_pricing_api`: require live AWS pricing lookup (fail if unavailable).
- `SPARKPILOT_PRICING_SOURCE=static`: use configured static pricing env vars only.
- Matrix cost guard calculations use the same runtime pricing snapshot as usage-cost recording and include the pricing source in cost guard messages.

`SPARKPILOT_PRICING_CACHE_SECONDS` controls in-process cache TTL for AWS pricing lookups.

## First Real AWS Run

- Set up AWS credentials: `docs/setup/aws-auth-quickstart.md`
- Run your first live job: `docs/setup/first-live-run.md`
- Run enterprise scenario matrix with cost caps: `docs/runbooks/enterprise-matrix-real-aws.md`

## One-Command Live UI (Real AWS)

Start API + workers + OIDC + UI in Docker with live AWS dispatch enabled:

```powershell
pwsh scripts/dev/start-live-ui.ps1 `
  -EmrExecutionRoleArn arn:aws:iam::<account-id>:role/SparkPilotEmrExecutionRole `
  -AwsProfile default `
  -AwsRegion us-east-1
```

The script:

- switches `SPARKPILOT_DRY_RUN_MODE=false`
- starts the full stack
- mints a bearer token
- bootstraps admin identity for that token subject
- copies token to clipboard and opens `http://localhost:3000`

## Current Scope

Implemented MVP control-plane behaviors include:

- Idempotent mutating APIs (`Idempotency-Key`)
- Environment provisioning operations and state machine
- Spark job template + run submission with per-run overrides
- Queue-style worker loops (provisioner, scheduler, reconciler)
- Deterministic log pointers and run log proxy
- Audit events and quota checks
- Starter AWS infra templates (Terraform + CloudFormation)
- BYOC-Lite mode (`provisioning_mode=byoc_lite`) for existing EKS cluster + namespace onboarding

## Execution Tracking

- Master tracker: `docs/execution-tracker.md`
- GitHub issue backlog: `https://github.com/JoshMcQ/SparkPilot/issues`
- POC criteria template: `docs/poc-success-criteria-template.md`
- Security one-pager template: `docs/security-one-pager-template.md`
- Weekly GTM scorecard: `docs/gtm-weekly-scorecard.md`
