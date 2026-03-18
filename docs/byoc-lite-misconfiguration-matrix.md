# BYOC-Lite Misconfiguration Preflight Matrix

> Issue: #66 — Real-AWS BYOC-Lite misconfiguration preflight matrix

## Overview

Every BYOC-Lite deployment depends on correct IAM, OIDC, namespace, and cluster
configuration. This matrix documents the deterministic failure behavior the
preflight system enforces **before** any EMR `StartJobRun` call is made.

## Misconfiguration Matrix

| # | Scenario | Check Code | Expected Status | Remediation Includes |
|---|----------|------------|-----------------|---------------------|
| 1 | OIDC provider not associated with EKS cluster | `byoc_lite.oidc_association` | `fail` | `eksctl utils associate-iam-oidc-provider` |
| 2 | Execution role trust policy missing EMR web-identity | `byoc_lite.execution_role_trust` | `fail` | Grant trust / error message |
| 3 | Customer role missing `iam:PassRole` | `byoc_lite.iam_pass_role` | `fail` | Allow `iam:PassRole` on execution role |
| 4 | Customer role missing EMR dispatch actions | `byoc_lite.customer_role_dispatch` | `fail` | Allow `StartJobRun`, `DescribeJobRun`, `CancelJobRun` |
| 5 | Reserved namespace (e.g. `kube-system`) | `byoc_lite.namespace_bootstrap` | `fail` | Use a dedicated namespace |
| 6 | Namespace format invalid (>63 chars, uppercase) | `byoc_lite.eks_namespace_format` | `fail` | Regex: `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$` |
| 7 | Cross-account mismatch (role ≠ cluster account) | `byoc_lite.account_alignment` | `fail` | Use same AWS account |
| 8 | Pod Identity agent not installed | `byoc_lite.pod_identity_readiness` | `warning` | Install EKS Pod Identity addon |
| 9 | EKS access mode = `CONFIG_MAP` only | `byoc_lite.access_entry_mode` | `warning` | Upgrade to `API_AND_CONFIG_MAP` |

## Scheduler Guard Rail

When any check has `status == "fail"`, the scheduler **blocks the run** before
`StartJobRun` is invoked and records the failure as:

```
run.state = "failed"
run.error_message = "Preflight failed: <summary>"
```

An audit event with action `run.preflight_failed` is persisted for traceability.

## Evidence Artifacts

Every preflight response includes:

- `environment_id` — links to the environment under test
- `run_id` — links to the specific run (when triggered by scheduler)
- `generated_at` — ISO timestamp of check execution
- Per-check `code`, `status`, `message`, `remediation`, and `details`

## Test Coverage

10 automated tests in `tests/test_api.py` (prefix `test_matrix_*`):

| Test | Validates |
|------|-----------|
| `test_matrix_oidc_association_missing_fails` | OIDC not associated → fail + eksctl remediation |
| `test_matrix_execution_role_trust_fails` | Trust policy error → fail |
| `test_matrix_iam_pass_role_missing_fails` | Missing PassRole → fail + remediation |
| `test_matrix_dispatch_permission_missing_fails` | Missing dispatch → fail + StartJobRun remediation |
| `test_matrix_namespace_reserved_fails` | Reserved namespace → fail |
| `test_matrix_namespace_format_invalid_fails` | Invalid format → fail |
| `test_matrix_all_checks_pass_flow` | All checks pass with correct config |
| `test_matrix_scheduler_blocks_on_preflight_fail` | Scheduler blocks run, state=failed |
| `test_matrix_account_alignment_mismatch_fails` | Cross-account → fail |
| `test_matrix_evidence_artifacts_present` | Response has env_id, timestamps, remediation on fails |
