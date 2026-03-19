# Issue #3 — Preflight Check Sequence Design

Date: 2026-03-18

## Required Gate Order (before any dispatch)

Preflight execution order for scheduler dispatch should be deterministic and short-circuit on hard failures:

1. `sts:GetCallerIdentity`
2. `iam:SimulatePrincipalPolicy`
3. `eks:DescribeCluster`
4. IRSA trust/service-account subject validation

This sequence runs in `process_scheduler_once` before `_dispatch_run(...)` so `EmrEksClient.start_job_run(...)` is never called when prerequisites fail.

## Why this order

- **STS first** proves credential chain and caller identity before deeper checks.
- **IAM simulation second** validates permission intent while avoiding side effects.
- **EKS describe third** validates the cluster exists/accessible in target account+region.
- **IRSA subject check last** validates role trust details using OIDC issuer + namespace/service-account pattern.

## Proposed check contract

Each check should emit a normalized result:

```json
{
  "code": "iam.runtime_identity",
  "status": "pass|warning|fail",
  "message": "human summary",
  "remediation": "optional exact remediation command",
  "details": {"structured": "metadata"}
}
```

`ready = true` only when no check has `status == "fail"`.

## Check details

### 1) STS identity (`sts:GetCallerIdentity`)

- API: `sts.get_caller_identity()`
- Inputs: assumed customer role session (same session used for dispatch prechecks)
- Pass criteria:
  - API returns Account/Arn/UserId
  - Account ID matches expected account from `environment.customer_role_arn`
- Fail examples:
  - expired/invalid credentials
  - access denied assuming customer role
- Remediation:
  - verify role assumption chain + trust policy for runtime principal

### 2) Permission simulation (`iam:SimulatePrincipalPolicy`)

- API: `iam.simulate_principal_policy()` against `environment.customer_role_arn`
- Simulate required actions:
  - `emr-containers:StartJobRun`
  - `emr-containers:DescribeJobRun`
  - `emr-containers:CancelJobRun`
  - `iam:PassRole` on `SPARKPILOT_EMR_EXECUTION_ROLE_ARN`
  - `eks:DescribeCluster`
- Pass criteria:
  - all required actions evaluate to `allowed`
- Fail output:
  - explicit denied actions list
  - explicit role ARN resource context for PassRole
- Remediation:
  - include exact IAM policy actions/resources to add

### 3) EKS cluster inspection (`eks:DescribeCluster`)

- API: `eks.describe_cluster(name=<cluster from arn>)`
- Pass criteria:
  - cluster exists and is reachable
  - cluster status in acceptable state (`ACTIVE` expected)
  - OIDC issuer is present under `cluster.identity.oidc.issuer`
  - described cluster ARN/account/region align with environment metadata
- Fail output:
  - mismatch details (expected vs observed account/region/cluster)
- Remediation:
  - exact `aws eks describe-cluster` / `eksctl` commands for verification

### 4) IRSA trust + service-account subject pattern

- Data sources:
  - OIDC issuer from step 3
  - execution role trust policy via `iam.get_role`
  - namespace from `environment.eks_namespace`
- Pass criteria:
  - trust policy has `sts:AssumeRoleWithWebIdentity`
  - federated principal matches derived OIDC provider ARN
  - `StringLike` subject matches SparkPilot EMR SA pattern
    - `system:serviceaccount:<namespace>:emr-containers-sa-*-*-<account>-<role>`
- Fail output:
  - missing/mismatched principal or subject condition details
- Remediation:
  - exact `aws emr-containers update-role-trust-policy --cluster-name ... --namespace ... --role-name ... --region ...`

## Existing code reuse

- `sparkpilot.services.workers_scheduling.process_scheduler_once` already performs preflight before dispatch.
- `sparkpilot.aws_clients.EmrEksClient.check_customer_role_dispatch_permissions` already wraps IAM simulation.
- `sparkpilot.aws_clients.EmrEksClient.check_execution_role_trust_policy` already validates OIDC + trust/subject pattern.
- `sparkpilot.services.iam_validation.validate_runtime_identity` already provides runtime identity checks.

## Integration target

For Issue #3 implementation, these checks are grouped in `src/sparkpilot/services/preflight_checks.py`, wired from `src/sparkpilot/services/preflight.py`, and surfaced through API/CLI/UI diagnostics.
