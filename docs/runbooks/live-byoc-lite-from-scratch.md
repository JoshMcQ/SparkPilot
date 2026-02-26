# Live BYOC-Lite From Scratch

Reproduce a full BYOC-Lite Spark job on real AWS from a clean starting point.
Written from the Feb 24 2026 live run on account `787587782916`.

---

## Prerequisites

| Tool | Install |
|---|---|
| AWS CLI | `pip install awscli` or standalone installer |
| eksctl | <https://eksctl.io/installation/> |
| kubectl | via eksctl or standalone |
| Python 3.12+ | system install |
| SparkPilot | `pip install -e .` from repo root |

Verify AWS identity before proceeding:

```powershell
python -m awscli sts get-caller-identity
```

---

## Phase 1 — EKS Cluster (one-time)

### 1.1 Create Cluster

```bash
eksctl create cluster \
  --name sparkpilot-live-1 \
  --region us-east-1 \
  --node-type t3.large \
  --nodes 2
```

### 1.2 Associate OIDC Provider

**This is mandatory for IRSA (IAM Roles for Service Accounts).
EMR execution role pods will fail with `InvalidIdentityToken` without it.**

```bash
eksctl utils associate-iam-oidc-provider \
  --cluster sparkpilot-live-1 \
  --region us-east-1 \
  --approve
```

---

## Phase 2 — IAM Roles (one-time)

### 2.1 BYOC Role (control-plane assume-role target)

Create a role trusted by your SparkPilot IAM user/role. Minimum permissions:

- `emr-containers:*`
- `iam:PassRole`
- `s3:*`
- `logs:*`
- `eks:DescribeCluster`

In the live run this was `SparkPilotByocLiteRoleAdmin` with `AdministratorAccess`
(overly broad — scope down for production).

### 2.2 EMR Execution Role (data-plane pod identity)

Create a role with:

- `AmazonS3FullAccess`
- `CloudWatchLogsFullAccess`

Trust policy is set automatically in step 3.2 via `update-role-trust-policy`.
You do **not** need to hand-craft the OIDC service-account wildcard yourself.

In the live run this was `SparkPilotEmrExecutionRole`.

---

## Phase 3 — EMR-on-EKS Namespace Wiring (one-time per namespace)

### 3.1 Create Namespace

> **⚠ Namespace collision:** If the target namespace already has an EMR virtual
> cluster mapped to it, `CreateVirtualCluster` will fail with a validation error.
> Always use a fresh namespace or delete the existing virtual cluster first.

```bash
kubectl create namespace sparkpilot-team-234100
```

### 3.2 Grant EMR Service Access (aws-auth mapRoles)

EMR on EKS requires the `AWSServiceRoleForAmazonEMRContainers` service-linked role
to be mapped into the cluster's `aws-auth` ConfigMap. This is the mapping that gives
EMR permission to schedule job pods in the namespace.

```bash
eksctl create iamidentitymapping \
  --cluster sparkpilot-live-1 \
  --region us-east-1 \
  --arn "arn:aws:iam::<account-id>:role/AWSServiceRoleForAmazonEMRContainers" \
  --username emr-containers
```

> **Note:** In the Feb 24 live run, this was applied by editing the `aws-auth`
> ConfigMap directly (`kubectl edit -n kube-system configmap/aws-auth`) to add
> the `mapRoles` entry for `AWSServiceRoleForAmazonEMRContainers`. The eksctl
> command above achieves the same result.

### 3.3 Update Execution Role Trust Policy

This scopes the execution role's OIDC trust to the target namespace. Use the
EMR CLI helper — it writes the correct service-account condition automatically:

```bash
aws emr-containers update-role-trust-policy \
  --cluster-name sparkpilot-live-1 \
  --namespace sparkpilot-team-234100 \
  --role-name SparkPilotEmrExecutionRole \
  --region us-east-1
```

---

## Phase 4 — SparkPilot Session Env Vars (every session)

All three vars must be set in **every terminal** (API, each worker, CLI):

```powershell
$env:SPARKPILOT_DATABASE_URL="sqlite:///./sparkpilot_live.db"
$env:SPARKPILOT_DRY_RUN_MODE="false"
$env:SPARKPILOT_EMR_EXECUTION_ROLE_ARN="arn:aws:iam::<account-id>:role/SparkPilotEmrExecutionRole"
```

> **⚠ Silent killer:** If `SPARKPILOT_EMR_EXECUTION_ROLE_ARN` is not set, the
> code falls back to the default placeholder `arn:aws:iam::111111111111:role/...`.
> `StartJobRun` will succeed (no immediate error) but EMR will fail the job
> because the execution role doesn't exist. This was the single hardest bug to
> find in the live run.

> **Database URL:** Without `SPARKPILOT_DATABASE_URL`, each process defaults to
> its own in-memory SQLite, so the API, workers, and CLI all see different data.
> Point all of them at the same `sparkpilot_live.db` file.

---

## Phase 5 — Run It

### 5.1 Start services (4 terminals)

**Terminal A — API:**

```powershell
# (set env vars from Phase 4)
uvicorn sparkpilot.api:app --host 127.0.0.1 --port 8000
```

**Terminal B — Provisioner:**

```powershell
# (set env vars from Phase 4)
python -m sparkpilot.workers provisioner
```

**Terminal C — Scheduler:**

```powershell
# (set env vars from Phase 4)
python -m sparkpilot.workers scheduler
```

**Terminal D — Reconciler:**

```powershell
# (set env vars from Phase 4)
python -m sparkpilot.workers reconciler
```

### 5.2 CLI flow (Terminal E)

```powershell
# Create tenant
sparkpilot tenant-create --name "Live Test Tenant"
# → save tenant_id

# Create BYOC-Lite environment
sparkpilot env-create `
  --tenant-id <tenant_id> `
  --customer-role-arn arn:aws:iam::<account-id>:role/SparkPilotByocLiteRoleAdmin `
  --provisioning-mode byoc_lite `
  --eks-cluster-arn arn:aws:eks:us-east-1:<account-id>:cluster/sparkpilot-live-1 `
  --eks-namespace sparkpilot-team-234100 `
  --region us-east-1
# → save environment_id, operation id

# Wait for ready
sparkpilot env-get --environment-id <environment_id>
sparkpilot op-get --operation-id <operation_id>
# → status=ready, state=ready

# Create job template
sparkpilot job-create `
  --environment-id <environment_id> `
  --name word-count-test `
  --artifact-uri local:///usr/lib/spark/examples/jars/spark-examples.jar `
  --artifact-digest sha256:placeholder `
  --entrypoint org.apache.spark.examples.JavaWordCount `
  --arg s3://<bucket>/input/sample.txt `
  --conf spark.executor.instances=1 `
  --conf spark.executor.memory=1g `
  --conf spark.driver.memory=1g `
  --retry-max-attempts 1 `
  --timeout-seconds 600
# → save job_id

# Submit run
sparkpilot run-submit --job-id <job_id>
# → save run_id

# Monitor
sparkpilot run-list
sparkpilot run-get --run-id <run_id>

# After run reaches succeeded
sparkpilot run-logs --run-id <run_id>
sparkpilot usage-get --tenant-id <tenant_id>
```

---

## Success Checkpoints

| # | Check | How |
|---|---|---|
| 1 | Environment reaches `ready` | `env-get` status field |
| 2 | Run reaches `succeeded` | `run-get` state field |
| 3 | `run-logs` returns Spark driver output | `run-logs` returns lines |
| 4 | S3 output exists | `aws s3 ls s3://<bucket>/output/<run-prefix>/ --recursive` |

---

## Known Gotchas (from Feb 24 live run)

| Issue | Symptom | Root Cause | Fix |
|---|---|---|---|
| OIDC not associated | Pods fail with `InvalidIdentityToken` | `eksctl create cluster` does not auto-associate OIDC | Run `eksctl utils associate-iam-oidc-provider` (Phase 1.2) |
| Namespace collision | `CreateVirtualCluster` returns validation error | Another virtual cluster already exists in that namespace | Use a fresh namespace or delete existing VC first |
| Wrong execution role | Job accepted then fails; no clear error | Default placeholder `111111111111` used when env var not set | Set `SPARKPILOT_EMR_EXECUTION_ROLE_ARN` in every terminal |
| Missing database URL | CLI creates tenant but workers can't see it | Each process using separate in-memory SQLite | Set `SPARKPILOT_DATABASE_URL` to shared file path |
| Insufficient node capacity | Pods stuck `Pending`, Spark events show `Insufficient cpu` | Observed in this test: t3.large × 2 nodes was not enough for driver + executor pods | Scale node group (`--nodes-max 4`) or use Karpenter/EKS Auto Mode |
| Zombie pods from prior run | New run can't schedule; all CPU consumed | Old cancelled EMR job left pods running | `kubectl delete pods -n <ns> --force --grace-period=0`, cancel stale EMR job |
| `AccessDenied` on `StartJobRun` | 403 from EMR API | BYOC role missing `emr-containers:StartJobRun` or `iam:PassRole` | Verify role policy (Phase 2.1) |

---

## Cleanup / Cost Control

EKS nodes cost money when idle. After testing:

```bash
# Scale to zero (keeps cluster metadata, stops compute costs)
eksctl scale nodegroup \
  --cluster sparkpilot-live-1 \
  --name <nodegroup-name> \
  --nodes 0 --nodes-min 0 \
  --region us-east-1
```

Or delete the cluster entirely:

```bash
eksctl delete cluster --name sparkpilot-live-1 --region us-east-1
```

---

## Reference: Feb 24 Live Run Artifacts

| Resource | Value |
|---|---|
| AWS Account | `787587782916` |
| EKS Cluster | `sparkpilot-live-1` (us-east-1) |
| Namespace | `sparkpilot-team-234100` |
| Virtual Cluster ID | `837eczf6wy9khbvicxojvllb0` |
| BYOC Role | `SparkPilotByocLiteRoleAdmin` |
| Execution Role | `SparkPilotEmrExecutionRole` |
| S3 Bucket | `sparkpilot-live-787587782916-20260224203702` |
| Successful Run ID | `989dba34-a5be-4a0f-8d1d-1707ae64bdf2` |
| EMR Job Run ID | `0000000374i9j1pmcoo` |
