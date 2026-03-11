# Choose Your Mode: BYOC-lite vs Full-BYOC

Use this page first before setup.

## BYOC-lite

- Uses an existing customer EKS cluster and namespace.
- Fastest path to first value and lowest setup time.
- In SparkPilot proof runs, this mode can reuse shared test cluster `sparkpilot-live-1`.

Choose BYOC-lite when:

- You already run EKS and want self-serve Spark now.
- You need low-cost validation and fast POC turnaround.
- You can provide a role ARN, EKS cluster ARN, and namespace.

## Full-BYOC

- Provisions customer-owned VPC/EKS/EMR dependencies per environment.
- Higher isolation and stronger infrastructure control.
- Must be validated on disposable stacks; do not reuse the BYOC-lite shared cluster topology.

Choose Full-BYOC when:

- Security/compliance requires per-environment isolation.
- You want full infra lifecycle managed through SparkPilot.
- You are ready for longer provisioning and stricter IaC controls.

## Decision Checklist

1. Need fastest production trial with minimal infra change: choose `BYOC-lite`.
2. Need full infra isolation and policy-controlled provisioning: choose `Full-BYOC`.
3. Need both: run BYOC-lite for immediate delivery, then promote to Full-BYOC.

## Validating Full-BYOC Terraform

Before running live provisioning, validate that the Full-BYOC Terraform modules are
syntactically correct and internally consistent.

### Validation scripts

Two equivalent scripts are provided:

- PowerShell (Windows / cross-platform pwsh): `scripts/terraform/validate_full_byoc.ps1`
- Bash (Linux / macOS / WSL): `scripts/terraform/validate_full_byoc.sh`

Run from the repository root:

```powershell
# PowerShell
pwsh scripts/terraform/validate_full_byoc.ps1
```

```bash
# Bash
bash scripts/terraform/validate_full_byoc.sh
```

Each script runs `terraform fmt -check`, then `terraform init -backend=false` and
`terraform validate` for each of the four roots:

- `infra/terraform/full-byoc`
- `infra/terraform/full-byoc/network`
- `infra/terraform/full-byoc/eks`
- `infra/terraform/full-byoc/emr`

Exit code `0` means all checks passed; exit code `1` means at least one check failed.

### Important: validate_full_byoc uses -backend=false

The validation scripts pass `-backend=false` to `terraform init`. This disables remote
state configuration, so **no AWS credentials are required** to run validation. The check
is purely a local HCL syntax and schema check.

### Required env vars for remote backend (live provisioning only)

When initializing Terraform for real provisioning (not validation), you must supply the
following environment variables so the SparkPilot orchestrator can configure the S3
backend:

| Variable | Description |
|---|---|
| `TF_BACKEND_BUCKET` | S3 bucket name for Terraform state |
| `TF_BACKEND_KEY` | State object key (path within the bucket) |
| `TF_BACKEND_REGION` | AWS region of the S3 bucket |
| `TF_BACKEND_DYNAMODB_TABLE` | DynamoDB table name for state locking (optional but recommended) |

### Manual remote-backend init

To initialize the Full-BYOC root with a remote backend outside of the SparkPilot
orchestrator:

```bash
terraform init \
  -backend-config="bucket=$TF_BACKEND_BUCKET" \
  -backend-config="key=$TF_BACKEND_KEY" \
  -backend-config="region=$TF_BACKEND_REGION" \
  -backend-config="dynamodb_table=$TF_BACKEND_DYNAMODB_TABLE"
```

Omit the `dynamodb_table` argument if you are not using state locking.
