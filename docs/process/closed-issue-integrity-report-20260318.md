# Closed-Issue Integrity Report — 2026-03-18

Status: In progress (phase 1 started)

## Snapshot (live GitHub)

- Open issues (live `gh`): 7 (`#3, #7, #18, #19, #20, #21, #81`)
- Closed issues (live `gh`): 84
- Source commands:
  - `gh issue list --state open --limit 200 --json number,title,labels,url`
  - `gh issue list --state closed --limit 200 --json number,title,closedAt,labels,url`

## Initial integrity heuristic

Filter used:
- Closed issues with label `status:needs-live-aws-evidence`
- Issue body missing obvious evidence markers (`artifacts/`, `docs/validation`, `Acceptance`, `Evidence`, `query_execution_id`, `JobRun ID`, `operation_id`)

Initial candidates for manual re-audit:
- #25 Full BYOC 1B: Terraform orchestrator and operation checkpointing
- #26 Full BYOC 1C: Implement provisioning_network stage
- #27 Full BYOC 1D: Implement provisioning_eks and provisioning_emr stages
- #28 Full BYOC 1E: Failure classification, compensation, and cleanup workflow
- #29 Full BYOC 1F: Security hardening and full-BYOC permission baseline

Note: This is a triage heuristic only. A missing evidence string in issue body does not prove bad closure; evidence may exist in comments, linked docs, commits, or follow-up issues.

## Progress update (2026-03-18 20:36 ET)

Completed:
- Re-validated live issue state directly from GitHub CLI.
- Performed broad scan of closed issues carrying `status:needs-live-aws-evidence`.
- Expanded evidence check from issue body-only to body+comments.
- Reopened issues failing explicit evidence-gate standards:
  - #75 `[Auth] Production IdP login + subject mapping (remove manual token as default)`
  - #58 `[Security] Replace localStorage bearer token handling and remove unsafe-inline CSP`
  - #59 `[Auth] Allowlist external OIDC issuer/token origins in CSP connect-src`
  - #60 `[Security] Throttle JWKS forced refresh on invalid signatures`
  - #66 `[Validation] Real-AWS BYOC-Lite misconfiguration preflight matrix`

Action rationale applied in each reopen comment:
- Label and Definition-of-Done require explicit non-prod evidence artifacts and runtime identifiers.
- Closure notes containing only test/build pass statements are insufficient for evidence-gated close.

Updated live issue state after corrective actions:
- Open issues: 12 (`#3, #7, #18, #19, #20, #21, #58, #59, #60, #66, #75, #81`)
- Closed issues: 79

## Next steps (continuing)

1. Manual issue-by-issue acceptance audit for the remaining 83 closed issues.
2. For each issue, record:
   - acceptance criteria present?
   - code proof path(s)
   - test proof (command + result)
   - live AWS proof artifact IDs if required
   - reopen recommendation (yes/no + reason)
3. Reopen any additional issue that fails evidence quality gates.

## Rules for closure confirmation

An issue is "validly closed" only if all apply:
- Acceptance criteria traceability exists.
- Evidence is specific and reproducible (not generic claims).
- For `status:needs-live-aws-evidence`, artifacts include concrete runtime identifiers.
- Claimed behavior matches current code on `main`.
- No contradicting open regressions without explicit supersession link.
