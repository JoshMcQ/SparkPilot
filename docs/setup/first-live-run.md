# First Live Run (BYOC-Lite)

Use this after credentials are configured to run SparkPilot against real AWS APIs.

## 0. Prerequisite Gate

Must pass before continuing:

```powershell
python -m awscli sts get-caller-identity
```

## 1. Start SparkPilot in Live Mode

Open terminal A:

```powershell
$env:SPARKPILOT_DATABASE_URL="sqlite:///./sparkpilot_live.db"
$env:SPARKPILOT_DRY_RUN_MODE="false"
$env:SPARKPILOT_EMR_EXECUTION_ROLE_ARN="arn:aws:iam::<account-id>:role/SparkPilotEmrExecutionRole"
uvicorn sparkpilot.api:app --host 127.0.0.1 --port 8000
```

Open terminal B:

```powershell
$env:SPARKPILOT_DATABASE_URL="sqlite:///./sparkpilot_live.db"
$env:SPARKPILOT_DRY_RUN_MODE="false"
$env:SPARKPILOT_EMR_EXECUTION_ROLE_ARN="arn:aws:iam::<account-id>:role/SparkPilotEmrExecutionRole"
python -m sparkpilot.workers provisioner
```

Open terminal C:

```powershell
$env:SPARKPILOT_DATABASE_URL="sqlite:///./sparkpilot_live.db"
$env:SPARKPILOT_DRY_RUN_MODE="false"
$env:SPARKPILOT_EMR_EXECUTION_ROLE_ARN="arn:aws:iam::<account-id>:role/SparkPilotEmrExecutionRole"
python -m sparkpilot.workers scheduler
```

Open terminal D:

```powershell
$env:SPARKPILOT_DATABASE_URL="sqlite:///./sparkpilot_live.db"
$env:SPARKPILOT_DRY_RUN_MODE="false"
$env:SPARKPILOT_EMR_EXECUTION_ROLE_ARN="arn:aws:iam::<account-id>:role/SparkPilotEmrExecutionRole"
python -m sparkpilot.workers reconciler
```

## 2. Create Tenant

Open terminal E:

```powershell
sparkpilot tenant-create --name "Live Test Tenant"
```

Save `tenant_id` from output.

## 3. Create BYOC-Lite Environment

Use your real customer role ARN and existing EKS cluster namespace:

```powershell
sparkpilot env-create `
  --tenant-id <tenant_id> `
  --customer-role-arn arn:aws:iam::<account-id>:role/<sparkpilot-role> `
  --provisioning-mode byoc_lite `
  --eks-cluster-arn arn:aws:eks:us-east-1:<account-id>:cluster/<cluster-name> `
  --eks-namespace sparkpilot-team `
  --region us-east-1
```

Save:

- `environment_id`
- provisioning operation `id`

## 4. Verify Environment Ready

```powershell
sparkpilot env-get --environment-id <environment_id>
sparkpilot op-get --operation-id <operation_id>
```

Checkpoint:

- environment `status` is `ready`
- operation `state` is `ready`

## 5. Create Job Template

```powershell
sparkpilot job-create `
  --environment-id <environment_id> `
  --name daily-aggregation `
  --artifact-uri s3://<bucket>/jobs/daily.jar `
  --artifact-digest sha256:abc123 `
  --entrypoint com.acme.jobs.Daily `
  --arg --date `
  --arg 2026-02-17 `
  --conf spark.dynamicAllocation.enabled=true `
  --retry-max-attempts 2 `
  --timeout-seconds 1800
```

Save `job_id`.

## 6. Submit Run and Observe

```powershell
sparkpilot run-submit --job-id <job_id>
sparkpilot run-list
sparkpilot run-get --run-id <run_id>
```

When run is terminal:

```powershell
sparkpilot run-logs --run-id <run_id>
sparkpilot usage-get --tenant-id <tenant_id>
```

## Success Checkpoints

1. Environment reaches `ready`.
2. Run reaches `succeeded`.
3. `run-logs` returns lines.
4. `usage-get` returns at least one item.

## First-Live-Run Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Run fails with `Unable to locate credentials` | Workers/API started without valid AWS auth | Re-run AWS auth quickstart and restart processes |
| Run fails `AccessDenied` on `StartJobRun` and execution role in request is wrong account | `SPARKPILOT_EMR_EXECUTION_ROLE_ARN` not set; code default is placeholder `arn:aws:iam::111111111111:role/SparkPilotEmrExecutionRole` | Export `SPARKPILOT_EMR_EXECUTION_ROLE_ARN` and restart API/workers |
| `422 eks_cluster_arn is required for byoc_lite` | Missing BYOC-Lite flag/value | Add `--eks-cluster-arn` to `env-create` |
| `422 eks_namespace is required for byoc_lite` | Missing namespace | Add `--eks-namespace` to `env-create` |
| `AccessDenied` on EMR create/start | Role policy/trust incomplete | Verify bootstrap role policy, `ExternalId`, and role ARN |
| Run stuck not progressing | Worker not running | Ensure provisioner/scheduler/reconciler terminals are running |
