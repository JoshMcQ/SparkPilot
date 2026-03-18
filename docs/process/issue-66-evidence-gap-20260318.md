# Issue #66 Evidence Gap Matrix (Live AWS)

Date: 2026-03-18 17:58 ET
Issue: https://github.com/JoshMcQ/SparkPilot/issues/66

## Acceptance Criteria Mapping

| Acceptance Criterion | Live Artifact Evidence | Status | Notes |
|---|---|---|---|
| Missing/incorrect execution-role trust fails pre-dispatch with deterministic check code + remediation | `artifacts/e2e-20260301-203939/p3-op-final.json`, `artifacts/issue65-second-operator-20260317-230121/summary.json` | PARTIAL | Live failure captured (`UpdateAssumeRolePolicy` LimitExceeded) but not an explicit malformed/missing trust-policy scenario with deterministic check-code output in thread. |
| Missing `iam:PassRole` fails pre-dispatch with deterministic check code + remediation | No explicit linked live artifact found | GAP | Need non-prod run where customer role lacks `iam:PassRole` and preflight/provisioning captures deterministic failure and remediation text. |
| Missing OIDC association fails pre-dispatch with deterministic check code + remediation | No explicit linked live artifact found | GAP | Need non-prod run against cluster without OIDC provider association showing `byoc_lite.oidc_association` failure + remediation command evidence. |
| Namespace collision/invalid namespace fails deterministically with remediation | `artifacts/e2e-20260301-203939/p6b-collision-op-final.json`, `artifacts/e2e-20260301-203939/p6b-malformed_arn-op-final.json` | PARTIAL | Collision evidence is explicit. Invalid namespace itself (DNS/reserved) not explicitly evidenced in live run artifact set; malformed ARN is a separate prerequisite failure. |
| Release/runtime incompatibility scenarios where applicable | `artifacts/e2e-20260301-203939/p6b-fake_cluster-op-final.json` | PARTIAL | Runtime mismatch/failure is evidenced via missing cluster path. No explicit EMR release incompatibility artifact linked. |
| No hard-fail scenario reaches `StartJobRun` | `artifacts/e2e-20260301-203939/summary.md` + failed operation artifacts above | PARTIAL | Strong indication from failed provisioning operations; thread still needs explicit line-by-line mapping in issue comment. |
| Evidence includes `operation_id`/`environment_id`/`run_id` where applicable | Multiple artifacts include operation/environment IDs; successful run IDs in `artifacts/issue65-second-operator-20260317-230206/summary.json` | PARTIAL | IDs exist across artifacts, but issue thread lacks consolidated mapping table tying IDs to each acceptance criterion. |

## Required Follow-up Before Re-close

1. Add explicit Issue #66 comment with line-by-line acceptance mapping and direct artifact paths.
2. Capture missing live-AWS scenarios (at least):
   - missing `iam:PassRole`
   - missing OIDC association
   - invalid namespace (reserved/format) in live path
3. Include consolidated runtime identifier table per scenario (`operation_id`, `environment_id`, `run_id`, EMR JobRun ID where run attempted).
4. Re-run regression suite after evidence capture and include command outputs in comment.

## Current Decision

Keep Issue #66 **OPEN** until GAP items are resolved and evidence is posted in-thread.
