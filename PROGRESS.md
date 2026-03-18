# SparkPilot Production Hardening Progress

Last updated: 2026-03-18 18:20 ET

## Phase 0 — Tracker bootstrap

- [x] Initialize PROGRESS.md with live GitHub open-issue baseline and execution phases. <!-- completed 2026-03-18 18:11 ET -->
- [x] Attach explicit live-AWS evidence mapping comment for #66 (operation_id/environment_id/run_id + artifact links) and close if acceptance criteria are satisfied. <!-- completed 2026-03-18 18:14 ET; left open pending missing trust/PassRole fail artifacts -->
- [x] Attach explicit live-AWS evidence mapping comments for #18/#19/#20/#21 and close only when each acceptance mapping is complete. <!-- completed 2026-03-18 18:17 ET; all 4 remain open pending additional live fail-path artifacts -->

### Blocker log
- 2026-03-18 18:14 ET — #66 remains open: issue thread now has collision/malformed-arn/fake-cluster live fail artifacts, but still missing explicit live fail artifacts for (a) execution-role trust hard-fail and (b) missing iam:PassRole hard-fail within this issue’s acceptance set.
- 2026-03-18 18:17 ET — #18/#19/#20/#21 evidence comments posted, but closure is blocked on additional live fail-path artifacts (invalid namespace case, AccessDenied trust-policy guidance path, and OIDC-missing detect+instruct fail path with runtime IDs).

## Phase 1 — Evidence-gated issue integrity

- [ ] Audit closed issues with `status:needs-live-aws-evidence`; reopen any issue missing explicit artifact links and runtime identifiers.
- [ ] Produce evidence ledger table (issue -> acceptance criteria -> artifacts -> reopen/close decision).

### Blocker log
- None.

## Phase 2 — Open critical path

- [ ] Complete #3 preflight IAM/IRSA validation evidence and closure package.
- [ ] Complete #7 UI BYOC vs BYOC-Lite differentiation and validation package.
- [ ] Complete #75 production IdP login + subject mapping evidence package.
- [ ] Complete #81 access-page guided workflow polish + validation package.

### Blocker log
- None.

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
