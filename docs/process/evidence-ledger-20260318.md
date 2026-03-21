# Evidence Ledger — Live AWS Evidence-Gated Issues (2026-03-18)

Source of truth: GitHub live issue state (`gh issue list/view`) and in-repo artifacts under `artifacts/`.

## Priority evidence-gated issues (current execution focus)

| Issue | Status | Acceptance mapping state | Evidence linked in-thread | Gap to close |
|---|---|---|---|---|
| #66 | OPEN | Partial | yes (comment `#issuecomment-4085884840`) | Missing explicit live fail artifacts for `execution_role_trust` hard fail and missing `iam:PassRole` hard fail with runtime IDs. |
| #18 | OPEN | Partial | yes (comment `#issuecomment-4085889916`) | Need explicit criterion-by-criterion live artifacts for role-policy/runtime prerequisite outputs. |
| #19 | OPEN | Partial | yes (comment `#issuecomment-4085889991`) | Need explicit invalid-namespace live artifact (reserved/DNS format) with operation/environment IDs. |
| #20 | OPEN | Partial | yes (comment `#issuecomment-4085890074`) | Need explicit live AccessDenied remediation-path artifact showing required permissions + command guidance text. |
| #21 | OPEN | Partial | yes (comment `#issuecomment-4085890150`) | Need explicit live OIDC-missing detect+instruct fail artifact (no IAM mutation) + runtime IDs. |
| #58 | OPEN | Not started this cycle | reopen rationale posted | Requires linked non-prod artifacts/runtime IDs in issue thread per DoD. |
| #59 | OPEN | Not started this cycle | reopen rationale posted | Requires linked non-prod artifacts/runtime IDs in issue thread per DoD. |
| #60 | OPEN | Not started this cycle | reopen rationale posted | Requires linked non-prod artifacts/runtime IDs in issue thread per DoD. |
| #75 | OPEN | Not started this cycle | reopen rationale posted | Requires explicit non-prod external IdP login trace + role-scoped API evidence mapping. |
| #3 | OPEN | Not started this cycle | existing historical references only | Need updated explicit live evidence mapping in-thread against current acceptance criteria. |

## Primary artifact references used today

- `artifacts/e2e-20260301-203939/p6b-collision-op-final.json`
- `artifacts/e2e-20260301-203939/p6b-malformed_arn-op-final.json`
- `artifacts/e2e-20260301-203939/p6b-fake_cluster-op-final.json`
- `artifacts/e2e-20260301-203939/m9-matrix-evidence.json`
- `artifacts/issue65-second-operator-20260317-230121/summary.json`
- `artifacts/issue65-second-operator-20260317-230206/summary.json`

## Decision rule

Issue closes only when:
1. Acceptance criteria are mapped line-by-line in-thread.
2. Evidence includes concrete runtime identifiers (`operation_id`, `environment_id`, `run_id`, `EMR JobRun ID` where applicable).
3. Artifacts are linked explicitly in-thread (not implied by docs/code).
4. Current validation snapshot is attached (`pytest`, `lint`, relevant security checks).
