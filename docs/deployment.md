# Deployment Guide

Prerequisite for real AWS runs:

- `docs/setup/aws-auth-quickstart.md`
- `docs/security/tenant-isolation-boundaries.md`

## CI/CD Deployment Flow

`/.github/workflows/ci-cd.yml` runs this sequence:

1. `test`
2. `ui-build`
3. `terraform-validate`
4. `e2e-local-smoke`
5. `security-scan`
6. `deploy-dev`
7. `deploy-staging`
8. `deploy-prod`

Deploy jobs run only for `push` events on `main`, and use GitHub Environments (`dev`, `staging`, `prod`) for approval gates.

Each deploy job:

1. Assumes the environment-specific AWS deploy role.
2. Builds and pushes API and worker container images to environment-specific ECR repositories.
3. Runs `scripts/terraform/deploy_control_plane.sh`, which performs:
   - `terraform fmt -check -recursive`
   - `terraform init -reconfigure` with S3 backend + DynamoDB lock table (`-backend-config`)
   - `terraform validate`
   - `terraform plan`
   - `terraform apply`
4. Runs `scripts/smoke/control_plane_api.sh` against the Terraform output `api_base_url` to verify:
   - `/healthz` is healthy (`status=ok`, database check ok, AWS check not error)
   - unauthenticated API access is rejected (`GET /v1/environments` returns `401`)

In addition, CI runs `scripts/smoke/run_local_stack_smoke.sh` before deploy gates to verify the local docker-compose control plane can execute an end-to-end BYOC-Lite app flow in dry-run mode.

Manual local smoke run:

```bash
bash scripts/smoke/run_local_stack_smoke.sh
```

If your shell resolves to a Python interpreter without `httpx` installed, set an explicit interpreter:

```bash
SMOKE_PYTHON_BIN=/path/to/python bash scripts/smoke/run_local_stack_smoke.sh
```

## Remote Backend Prerequisites

For each environment (`dev`, `staging`, `prod`) provision:

1. An S3 bucket for Terraform state.
2. A DynamoDB table for state locking with a string partition key named `LockID`.

Recommended bucket settings:

- Versioning enabled.
- Server-side encryption enabled.
- Block public access on all four flags.
- Access limited to the deploy role for that environment.

Deploy-role minimum capabilities:

- ECR repository and image operations used in CI (`ecr:DescribeRepositories`, `ecr:CreateRepository`, `ecr:PutImageScanningConfiguration`, image push actions).
- S3 state bucket read/write for the environment state key.
- DynamoDB lock table read/write for Terraform state locking.
- Create/update/delete permissions for control-plane Terraform resources in `infra/terraform/control-plane`.

## Required GitHub Configuration

Use environment prefixes:

- `dev` -> `DEV_*`
- `staging` -> `STAGING_*`
- `prod` -> `PROD_*`

Required secrets per environment:

- `AWS_<ENV>_DEPLOY_ROLE_ARN`
- `<ENV>_TF_STATE_BUCKET`
- `<ENV>_TF_LOCK_TABLE`
- `<ENV>_VPC_ID`
- `<ENV>_PRIVATE_SUBNET_IDS_JSON` (JSON array, at least two subnets)
- `<ENV>_PUBLIC_SUBNET_IDS_JSON` (JSON array, optional; defaults to `[]`)
- `<ENV>_DB_PASSWORD` (minimum 16 characters)
- `<ENV>_OIDC_ISSUER`
- `<ENV>_OIDC_AUDIENCE`
- `<ENV>_OIDC_JWKS_URI`
- `<ENV>_BOOTSTRAP_SECRET` (minimum 16 characters)
- `<ENV>_EMR_EXECUTION_ROLE_ARN`

Optional security secret per environment:

- `<ENV>_ASSUME_ROLE_EXTERNAL_ID` (required when customer role trust policy enforces `sts:ExternalId`)

Required variables per environment:

- `<ENV>_DRY_RUN_MODE` (`true`/`false`)
- `<ENV>_ENABLE_FULL_BYOC_MODE` (`true`/`false`)

Optional break-glass variables per environment:

- `<ENV>_ALLOW_UNSAFE_RDS_CONFIGURATION` (`true`/`false`, default `false`)
- `<ENV>_RDS_DELETION_PROTECTION` (`true`/`false`, optional override)
- `<ENV>_RDS_SKIP_FINAL_SNAPSHOT` (`true`/`false`, optional override)
- `<ENV>_RDS_FINAL_SNAPSHOT_IDENTIFIER` (optional override)

Optional CUR/chargeback variables per environment:

- `<ENV>_CUR_ATHENA_DATABASE` (Athena database for CUR)
- `<ENV>_CUR_ATHENA_TABLE` (Athena table for CUR)
- `<ENV>_CUR_ATHENA_OUTPUT_LOCATION` (`s3://...` query result location)
- `<ENV>_CUR_ATHENA_WORKGROUP` (default `primary`)
- `<ENV>_CUR_RUN_ID_COLUMN` (default `resource_tags_user_sparkpilot_run_id`)
- `<ENV>_CUR_COST_COLUMN` (default `line_item_unblended_cost`)
- `<ENV>_COST_CENTER_POLICY_JSON` (optional JSON mapping policy with keys `by_namespace`, `by_virtual_cluster_id`, `by_team`, `default`)

## RDS Safety Defaults By Environment

Control-plane Terraform enforces environment-aware defaults:

- `dev`: `deletion_protection=false`, `skip_final_snapshot=true`
- `staging` and `prod`: `deletion_protection=true`, `skip_final_snapshot=false`

For `staging`/`prod`, unsafe combinations are blocked by default. To allow an unsafe non-dev override, both conditions are required:

1. Set explicit unsafe override values (`RDS_DELETION_PROTECTION=false` and/or `RDS_SKIP_FINAL_SNAPSHOT=true`).
2. Set `ALLOW_UNSAFE_RDS_CONFIGURATION=true` for that environment.

## Manual Deploy (Outside GitHub Actions)

From repo root:

```bash
export SPARKPILOT_ENVIRONMENT=dev
export AWS_REGION=us-east-1
export TERRAFORM_DIR=infra/terraform/control-plane
export TF_STATE_BUCKET=<state-bucket>
export TF_STATE_KEY=sparkpilot/control-plane/dev.tfstate
export TF_LOCK_TABLE=<dynamodb-lock-table>
export VPC_ID=<vpc-id>
export PRIVATE_SUBNET_IDS_JSON='["subnet-aaa","subnet-bbb"]'
export PUBLIC_SUBNET_IDS_JSON='[]'
export DB_PASSWORD=<db-password>
export API_IMAGE_URI=<account>.dkr.ecr.<region>.amazonaws.com/sparkpilot-api-dev:<sha>
export WORKER_IMAGE_URI=<account>.dkr.ecr.<region>.amazonaws.com/sparkpilot-worker-dev:<sha>
export OIDC_ISSUER=<issuer-url>
export OIDC_AUDIENCE=<audience>
export OIDC_JWKS_URI=<jwks-uri>
export BOOTSTRAP_SECRET=<bootstrap-secret>
export ASSUME_ROLE_EXTERNAL_ID=<external-id-used-in-customer-role-trust-policy>
export DRY_RUN_MODE=false
export ENABLE_FULL_BYOC_MODE=false
export EMR_EXECUTION_ROLE_ARN=<iam-role-arn>
bash scripts/terraform/deploy_control_plane.sh
```

## Customer BYOC Bootstrap

Deploy `infra/cloudformation/customer-bootstrap.yaml` in each customer account with:

- `SparkPilotControlPlaneAccountId`
- `ExternalId`
- optional `RoleName`

Register the resulting `SparkPilotRoleArn` in SparkPilot via `POST /v1/environments`.

Runtime note: set `SPARKPILOT_ASSUME_ROLE_EXTERNAL_ID` (or `ASSUME_ROLE_EXTERNAL_ID`)
to the same value used in the customer trust policy so SparkPilot runtime
`AssumeRole` calls include `ExternalId`.

For full-BYOC architecture and sequencing:

- `docs/design/full-byoc-design.md`
- `docs/design/full-byoc-implementation-backlog.md`

### BYOC-Lite Mode

In BYOC-Lite, customer provides an existing EKS cluster ARN + namespace.

`POST /v1/environments` example fields:

- `provisioning_mode: byoc_lite`
- `eks_cluster_arn: arn:aws:eks:...:cluster/<name>`
- `eks_namespace: sparkpilot-team`

This mode skips VPC/EKS creation and only manages EMR virtual cluster + job lifecycle.

## Runtime Services

- API container from `docker/api.Dockerfile`
- Worker container from `docker/worker.Dockerfile` with command override:
  - `python -m sparkpilot.workers provisioner`
  - `python -m sparkpilot.workers scheduler`
  - `python -m sparkpilot.workers reconciler`

## UI

From `ui`:

```bash
npm install
SPARKPILOT_API=https://api.sparkpilot.cloud \
SPARKPILOT_UI_ENFORCE_AUTH=true \
NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE=false \
NEXT_PUBLIC_OIDC_ISSUER=https://auth.sparkpilot.cloud \
NEXT_PUBLIC_OIDC_AUDIENCE=sparkpilot-api \
NEXT_PUBLIC_OIDC_CLIENT_ID=<ui-public-client-id> \
NEXT_PUBLIC_OIDC_REDIRECT_URI=https://app.sparkpilot.cloud/auth/callback \
npm run build
npm run start
```

The UI uses Authorization Code + PKCE. Do not set a browser client secret.
`SPARKPILOT_UI_ENFORCE_AUTH` defaults to `true` when omitted.
`NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE` is for non-production development only.

Production-style local run (PowerShell):

```powershell
Set-Location ui
Copy-Item .env.production.example .env.production.local
# edit values for your API + OIDC settings
npm ci
npm run verify:prod-env
npm run build
npm run start -- --hostname 0.0.0.0 --port 3000
```

Or use the helper script:

```powershell
pwsh ./scripts/run-prod-local.ps1 `
  -ApiBase "https://api.sparkpilot.cloud" `
  -OidcIssuer "https://auth.sparkpilot.cloud" `
  -OidcClientId "sparkpilot-ui" `
  -OidcRedirectUri "https://app.sparkpilot.cloud/auth/callback" `
  -OidcAudience "sparkpilot-api" `
  -Port 3000
```

Route intent:

- Public pre-access routes: `/`, `/about`, `/contact`, `/pricing`, `/why-not-diy`, `/why-not-serverless`, `/login`, `/auth/callback`, `/getting-started`
- Authenticated product routes: `/dashboard`, `/onboarding/*`, `/environments/*`, `/runs`, `/integrations`, `/costs`, `/policies`, `/access`, `/settings`

## Recommended Rollout

1. Internal dogfood tenant.
2. Two design partners.
3. General availability.
