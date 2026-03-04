# Deployment Guide

Prerequisite for real AWS runs:

- `docs/setup/aws-auth-quickstart.md`

## 1. Control Plane Accounts

Create three AWS accounts:

- `sparkpilot-dev`
- `sparkpilot-staging`
- `sparkpilot-prod`

## 2. Terraform Bootstrap (Control Plane)

From `infra/terraform/control-plane`:

```bash
terraform init
terraform apply \
  -var="environment=dev" \
  -var="vpc_id=vpc-xxxxxxxx" \
  -var='private_subnet_ids=["subnet-a","subnet-b"]' \
  -var="db_password=<secure-password>"
```

## 3. Customer BYOC Bootstrap

Deploy `infra/cloudformation/customer-bootstrap.yaml` in customer account with:

- `SparkPilotControlPlaneAccountId`
- `ExternalId`
- optional `RoleName`

Register resulting `SparkPilotRoleArn` in SparkPilot via `POST /v1/environments`.

For full-BYOC architecture and implementation sequencing, see:

- `docs/design/full-byoc-design.md`
- `docs/design/full-byoc-implementation-backlog.md`

### BYOC-Lite Mode (recommended for fast security review)

In BYOC-Lite, customer provides existing EKS cluster ARN + namespace.

`POST /v1/environments` example fields:

- `provisioning_mode: byoc_lite`
- `eks_cluster_arn: arn:aws:eks:...:cluster/<name>`
- `eks_namespace: sparkpilot-team`

This mode skips VPC/EKS creation and only manages EMR virtual cluster + job lifecycle.

## 4. Runtime Services

- API container from `docker/api.Dockerfile`
- Worker container from `docker/worker.Dockerfile` with command override:
  - `python -m sparkpilot.workers provisioner`
  - `python -m sparkpilot.workers scheduler`
  - `python -m sparkpilot.workers reconciler`

## 5. UI

From `ui`:

```bash
npm install
SPARKPILOT_API=https://api.sparkpilot.example \
OIDC_ISSUER=https://auth.example \
OIDC_AUDIENCE=sparkpilot-api \
OIDC_CLIENT_ID=<ui-server-client-id> \
OIDC_CLIENT_SECRET=<ui-server-client-secret> \
npm run build
npm run start
```

## 6. Recommended Rollout

1. Internal dogfood tenant
2. Two design partners
3. General availability
