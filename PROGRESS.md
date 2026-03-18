# SparkPilot Production Hardening Progress

Last updated: 2026-03-18 19:16 ET

## Phase 0 — Tracker bootstrap

- [x] Initialize PROGRESS.md with live GitHub open-issue baseline and execution phases. <!-- completed 2026-03-18 18:11 ET -->
- [x] Attach explicit live-AWS evidence mapping comment for #66 (operation_id/environment_id/run_id + artifact links) and close if acceptance criteria are satisfied. <!-- completed 2026-03-18 18:14 ET; left open pending missing trust/PassRole fail artifacts -->
- [x] Attach explicit live-AWS evidence mapping comments for #18/#19/#20/#21 and close only when each acceptance mapping is complete. <!-- completed 2026-03-18 18:17 ET; all 4 remain open pending additional live fail-path artifacts -->

### Blocker log
- 2026-03-18 18:14 ET — #66 remains open: issue thread now has collision/malformed-arn/fake-cluster live fail artifacts, but still missing explicit live fail artifacts for (a) execution-role trust hard-fail and (b) missing iam:PassRole hard-fail within this issue’s acceptance set.
- 2026-03-18 18:17 ET — #18/#19/#20/#21 evidence comments posted, but closure is blocked on additional live fail-path artifacts (invalid namespace case, AccessDenied trust-policy guidance path, and OIDC-missing detect+instruct fail path with runtime IDs).

## Phase 1 — Evidence-gated issue integrity

- [x] Audit closed issues with `status:needs-live-aws-evidence`; reopen any issue missing explicit artifact links and runtime identifiers. <!-- completed 2026-03-18 18:22 ET; no closed issues remain with this label after reopen actions -->
- [x] Produce evidence ledger table (issue -> acceptance criteria -> artifacts -> reopen/close decision). <!-- completed 2026-03-18 18:24 ET; see docs/process/evidence-ledger-20260318.md -->

### Blocker log
- None.

## Phase 2 — Open critical path

- [x] Complete #3 preflight IAM/IRSA validation evidence and closure package. <!-- completed 2026-03-18 19:03 ET; evidence refresh posted in issue #3 comment with live run.preflight_failed + run.preflight_diagnostic artifacts -->
- [x] Complete #7 UI BYOC vs BYOC-Lite differentiation and validation package. <!-- completed 2026-03-18 19:06 ET; live evidence bundle + runtime IDs posted in issue #7 comment -->
- [ ] Complete #75 production IdP login + subject mapping evidence package.
- [x] Complete #81 access-page guided workflow polish + validation package. <!-- completed 2026-03-18 19:16 ET; access workflow helpers + inline validation + error mapping tests + live UI evidence posted -->

### Blocker log
- 2026-03-18 19:03 ET — #3 evidence package refreshed: added live run.preflight_failed artifacts for PassRole deny + trust-policy AccessDenied and legacy reconciler `run.preflight_diagnostic` artifact with runtime IDs; posted in issue #3 comment.
- 2026-03-18 19:09 ET — #75 blocked for completion in this pass: required non-prod *external* IdP OIDC auth-code+PKCE trace is not currently configured in this local stack (current issuer is internal mock OIDC). Need external IdP tenant/client config + callback setup to capture closure-grade artifacts.
- 2026-03-18 19:12 ET — Re-validated blocker for #75 while executing this heartbeat: local environment still uses internal mock issuer; cannot produce required external-IdP acceptance artifacts without external tenant/client details.

## Verification passes

### 2026-03-18 18:20 ET (after 3 completed tasks)
- `cd C:\Users\JoshMcQueary\SparkPilot && .\.venv\Scripts\python -m pytest`
  - Result: `314 passed, 1 skipped` (35.36s)
- `cd C:\Users\JoshMcQueary\SparkPilot\ui && npm run lint`
  - Result: completed with warnings (no hard errors):
    - `_cookieOptions` unused (`ui/app/api/auth/session/route.ts`)
    - missing hook deps in `ui/app/costs/page.tsx` and `ui/app/runs/page.tsx`
- `cd C:\Users\JoshMcQueary\SparkPilot && git diff --stat`
  - Result: working tree currently includes local modifications in `ui/*` and `PROGRESS.md` (see diff stat output); no destructive ops performed.
- `cd C:\Users\JoshMcQueary\SparkPilot && git log -5 -p | Select-String "AKIA|sk-|password|secret"`
  - Result: no credential-like secret strings detected (only generic doc/test text references to the word `secret`).

### 2026-03-18 19:16 ET (after next 3 completed tasks: #3, #7, #81)
- `cd C:\Users\JoshMcQueary\SparkPilot && .\.venv\Scripts\python -m pytest`
  - Result: `317 passed, 3 skipped` (35.31s)
- `cd C:\Users\JoshMcQueary\SparkPilot\ui && npm run lint`
  - Result: completed with warnings (no hard errors):
    - `_cookieOptions` unused (`ui/app/api/auth/session/route.ts`)
    - missing hook deps in `ui/app/costs/page.tsx` and `ui/app/runs/page.tsx`
- `cd C:\Users\JoshMcQueary\SparkPilot\ui && npm audit`
  - Result: 1 moderate vulnerability in `next` (`GHSA-3x4c-7xq6-9pq8`, `GHSA-ggv3-7p47-pfv8`); fix requires breaking upgrade path (`next@16.2.0`). Logged for controlled remediation (no `--force`).
- `cd C:\Users\JoshMcQueary\SparkPilot && git diff --stat`
  - Result: includes this pass updates to `ui/app/access/page.tsx`, `ui/lib/access-workflow.ts`, `ui/tests/access-workflow.test.ts`, `ui/package*.json`, plus pre-existing in-progress UI/test files.
- `cd C:\Users\JoshMcQueary\SparkPilot && git log -5 -p | Select-String "AKIA|sk-|password|secret"`
  - Result: no credential-like secret strings detected.
