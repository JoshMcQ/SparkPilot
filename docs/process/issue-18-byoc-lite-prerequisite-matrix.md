# Issue #18 — BYOC-Lite Prerequisite Matrix

Date: 2026-03-18

## Objective
Define deterministic prerequisite checks for BYOC-Lite environments before run dispatch.

## Matrix

| Category | Prerequisite | Why it matters | Validation API/check | Pass criteria | Remediation command guidance |
|---|---|---|---|---|---|
| Identity | Customer role can be assumed | SparkPilot cannot run any customer-account checks/actions without STS assume-role success | `sts:GetCallerIdentity` through assumed session | returned account/arn match target role account | Verify trust policy + caller principal: `aws iam get-role --role-name <customer-role>` |
| IAM permissions | Dispatch actions allowed | Scheduler dispatch needs EMR on EKS lifecycle actions | `iam:SimulatePrincipalPolicy` | `StartJobRun`, `DescribeJobRun`, `CancelJobRun` evaluate `allowed` | Add allows on customer role for `emr-containers:StartJobRun/DescribeJobRun/CancelJobRun` |
| IAM permissions | `iam:PassRole` on execution role | EMR on EKS submit fails if role pass is denied | `iam:SimulatePrincipalPolicy` with execution role ARN resource | `iam:PassRole` decision is `allowed` | Add `iam:PassRole` scoped to `SPARKPILOT_EMR_EXECUTION_ROLE_ARN` |
| Cluster access | Target EKS cluster exists and is readable | Namespace/bootstrap and IRSA checks depend on cluster metadata | `eks:DescribeCluster` | cluster status `ACTIVE`, ARN/region align, OIDC issuer present | `aws eks describe-cluster --name <cluster> --region <region>` |
| OIDC | OIDC provider is associated | IRSA trust cannot work without issuer/provider | `eks:DescribeCluster` issuer + trust policy provider ARN check | issuer present and mapped provider ARN in trust policy | `eksctl utils associate-iam-oidc-provider --cluster <cluster> --region <region> --approve` |
| IRSA trust | Execution role trust has web-identity statement | EMR SA cannot assume execution role otherwise | `iam:GetRole` trust document parse | has `sts:AssumeRoleWithWebIdentity` + expected federated provider ARN + `StringLike` subject pattern | `aws emr-containers update-role-trust-policy --cluster-name <cluster> --namespace <ns> --role-name <role> --region <region>` |
| Namespace | Namespace format + expected ownership | Invalid/mis-targeted namespace causes SA and policy mismatch | static validation + (future) live namespace existence check | DNS-1123 compliant, policy-compliant prefix, no forbidden chars/case | `kubectl create namespace <namespace>` (when missing) and ensure configured value matches |
| Runtime dependency | EMR virtual cluster ID configured (or discoverable) | Dispatch cannot target EMR on EKS without VC context | environment preflight config check | non-empty virtual cluster ID for dispatch path | Provision/attach VC during environment setup; re-run preflight |
| Runtime dependency | SparkPilot execution role ARN configured | IAM simulation and trust checks require explicit role target | settings/runtime validation | non-placeholder valid IAM role ARN | set `SPARKPILOT_EMR_EXECUTION_ROLE_ARN=arn:aws:iam::<acct>:role/<name>` |
| Networking | API endpoint path reachable from UI/CLI | Submission UX requires stable API path for preflight and run submit | API health + request checks | `/v1/environments/{id}/preflight` and `/v1/jobs/{id}/runs` respond as expected | verify gateway/API deployment and auth proxy configuration |
| Observability | Diagnostic audit event persistence enabled | Operators need deterministic failure reasons for remediation | `run.preflight_*` audit event checks | latest run contains preflight summary + checks | fix scheduler audit writes / DB persistence and verify via `/v1/runs/{id}` |

## Required outcome for Issue #18

- Each prerequisite maps to one deterministic check function.
- Each failed check emits a machine-readable `code` + human remediation text.
- BYOC-Lite preflight reports all non-blocking warnings and blocks dispatch on hard fails.
