# SparkPilot Production Hardening Progress

Last updated: 2026-03-18 20:14 ET

## Phase 0 - Tracker bootstrap

- [x] Initialize PROGRESS.md with live GitHub open-issue baseline and execution phases. <!-- completed 2026-03-18 18:11 ET -->
- [x] Attach explicit live-AWS evidence mapping comment for #66 (operation_id/environment_id/run_id + artifact links) and close if acceptance criteria are satisfied. <!-- completed 2026-03-18 18:14 ET; left open pending missing trust/PassRole fail artifacts -->
- [x] Attach explicit live-AWS evidence mapping comments for #18/#19/#20/#21 and close only when each acceptance mapping is complete. <!-- completed 2026-03-18 18:17 ET; all 4 remain open pending additional live fail-path artifacts -->

### Blocker log
- 2026-03-18 18:14 ET - #66 remains open: issue thread now has collision/malformed-arn/fake-cluster live fail artifacts, but still missing explicit live fail artifacts for (a) execution-role trust hard-fail and (b) missing iam:PassRole hard-fail within this issue's acceptance set.
- 2026-03-18 18:17 ET - #18/#19/#20/#21 evidence comments posted, but closure is blocked on additional live fail-path artifacts (invalid namespace case, AccessDenied trust-policy guidance path, and OIDC-missing detect+instruct fail path with runtime IDs).

## Phase 1 - Evidence-gated issue integrity

- [x] Audit closed issues with `status:needs-live-aws-evidence`; reopen any issue missing explicit artifact links and runtime identifiers. <!-- completed 2026-03-18 18:22 ET; no closed issues remain with this label after reopen actions -->
- [x] Produce evidence ledger table (issue -> acceptance criteria -> artifacts -> reopen/close decision). <!-- completed 2026-03-18 18:24 ET; see docs/process/evidence-ledger-20260318.md -->

### Blocker log
- None.

## Phase 2 - Open critical path

- [x] Complete #3 preflight IAM/IRSA validation evidence and closure package. <!-- completed 2026-03-18 19:03 ET; evidence refresh posted in issue #3 comment with live run.preflight_failed + run.preflight_diagnostic artifacts -->
- [x] Complete #7 UI BYOC vs BYOC-Lite differentiation and validation package. <!-- completed 2026-03-18 19:06 ET; live evidence bundle + runtime IDs posted in issue #7 comment -->
- [x] Complete #75 production IdP login + subject mapping evidence package. <!-- completed 2026-03-18 20:12 ET; external Cognito auth-code+PKCE + subject-mapped role-scoped API evidence posted and issue closed -->
- [x] Complete #81 access-page guided workflow polish + validation package. <!-- completed 2026-03-18 19:16 ET; access workflow helpers + inline validation + error mapping tests + live UI evidence posted -->
- [x] Prepare external IdP evidence-capture runbook and environment template to unblock #75. <!-- completed 2026-03-18 19:31 ET; added docs/process/external-idp-evidence-runbook.md -->

### Blocker log
- 2026-03-18 19:03 ET - #3 evidence package refreshed: added live run.preflight_failed artifacts for PassRole deny + trust-policy AccessDenied and legacy reconciler `run.preflight_diagnostic` artifact with runtime IDs; posted in issue #3 comment.
- 2026-03-18 19:09 ET - #75 blocked for completion in this pass: required non-prod *external* IdP OIDC auth-code+PKCE trace is not currently configured in this local stack (current issuer is internal mock OIDC). Need external IdP tenant/client config + callback setup to capture closure-grade artifacts.
- 2026-03-18 19:12 ET - Re-validated blocker for #75 while executing this heartbeat: local environment still uses internal mock issuer; cannot produce required external-IdP acceptance artifacts without external tenant/client details.
- 2026-03-18 19:17 ET - Posted blocker/evidence request in issue #75 comment (`#issuecomment-4086219182`) listing required external IdP tenant/client/callback config needed to complete acceptance package.
- 2026-03-18 19:18 ET - Re-checked #75 as first unchecked task this heartbeat; still blocked until external IdP tenant/client config is available. No further closure-grade evidence can be generated in current mock-only setup.
- 2026-03-18 19:31 ET - Added unblocking runbook `docs/process/external-idp-evidence-runbook.md` and posted issue #75 comment (`#issuecomment-4086293886`) with required external IdP inputs + evidence capture checklist.
- 2026-03-18 20:12 ET - #75 blocker resolved: captured external AWS Cognito auth-code+PKCE trace + subject-mapped role-scoped API evidence, posted in issue #75 (`#issuecomment-4086498885`), closed issue, and completed full teardown (user pool/domain/client/test user + temp API container + temp DB mapping rows).
- 2026-03-18 20:14 ET - All checklist items in PROGRESS.md are now checked; wrote `docs/process/completion-report.md` per heartbeat completion rule.

## Phase 3 - Clean code

- [x] Functions: extract `_job_template_response`, `_interactive_endpoint_response`, and `_compute_active_vcpu` helpers in `api.py` to eliminate three-way response-construction duplication and inline vCPU loop. <!-- completed 2026-03-18; 324 passed, 6 skipped -->

## Phase 4 - Open UI backlog follow-through (2026-03-19)

- [x] #91: tighten JSON-mode error diagnostics (line/column from parser position) and add one-click export of last submitted run payload for deterministic reruns. <!-- completed 2026-03-19 09:22 ET; commit 379ac82 -->

### Blocker log
- None.

## Verification passes

### 2026-03-18 18:20 ET (after 3 completed tasks)
- `python -m pytest (from repo root with venv activated)`
  - Result: `314 passed, 1 skipped` (35.36s)
- `cd ui && npm run lint`
  - Result: completed with warnings (no hard errors):
    - `_cookieOptions` unused (`ui/app/api/auth/session/route.ts`)
    - missing hook deps in `ui/app/costs/page.tsx` and `ui/app/runs/page.tsx`
- `git diff --stat`
  - Result: working tree currently includes local modifications in `ui/*` and `PROGRESS.md` (see diff stat output); no destructive ops performed.
- `git log -5 -p | Select-String "AKIA|sk-|password|secret"`
  - Result: no credential-like secret strings detected (only generic doc/test text references to the word `secret`).

### 2026-03-18 19:16 ET (after next 3 completed tasks: #3, #7, #81)
- `python -m pytest (from repo root with venv activated)`
  - Result: `317 passed, 3 skipped` (35.31s)
- `cd ui && npm run lint`
  - Result: completed with warnings (no hard errors):
    - `_cookieOptions` unused (`ui/app/api/auth/session/route.ts`)
    - missing hook deps in `ui/app/costs/page.tsx` and `ui/app/runs/page.tsx`
- `cd ui && npm audit`
  - Result: 1 moderate vulnerability in `next` (`GHSA-3x4c-7xq6-9pq8`, `GHSA-ggv3-7p47-pfv8`); fix requires breaking upgrade path (`next@16.2.0`). Logged for controlled remediation (no `--force`).
- `git diff --stat`
  - Result: includes this pass updates to `ui/app/access/page.tsx`, `ui/lib/access-workflow.ts`, `ui/tests/access-workflow.test.ts`, `ui/package*.json`, plus pre-existing in-progress UI/test files.
- `git log -5 -p | Select-String "AKIA|sk-|password|secret"`
  - Result: no credential-like secret strings detected.

### 2026-03-19 09:22 ET (#91 incremental follow-through)
- `python -m pytest (from repo root with venv activated)`
  - Result: `324 passed, 6 skipped` (36.31s)
- `cd ui && npm run lint`
  - Result: clean (`eslint` completed with no errors/warnings in this run).
- `cd ui && npm audit`
  - Result: `found 0 vulnerabilities`.

### 2026-03-19 09:43 ET (PR #92 review remediation + CI parity)
- `pytest -q`
  - Result: `325 passed, 6 skipped` (fixed import-path parity for `pytest` direct invocation via `tests/__init__.py` + `tests.conftest` imports).
- `python -m pytest -q` (venv)
  - Result: `325 passed, 6 skipped`.
- `cd ui && npm run lint`
  - Result: clean (`eslint` completed with no errors/warnings).
- `cd ui && npm audit`
  - Result: `found 0 vulnerabilities`.
- `cd ui && npm test`
  - Result: `6 passed` (`tests/access-workflow.test.ts`) after workflow validation hardening updates.

### 2026-03-19 09:40 ET (CI follow-up: OIDC cache-expiry parity)
- Updated `tests/test_oidc.py::test_stale_token_after_oidc_restart_raises_key_rotation_error` to force JWKS cache expiry relative to `time.monotonic()` (`cached_at = now - ttl - 1`) instead of hardcoding `0`, which was non-expired on short-lived CI runners.
- `pytest -q`
  - Result: `325 passed, 6 skipped`.
- `cd ui && npm run lint`
  - Result: clean (`eslint` completed with no errors/warnings).
- `cd ui && npm audit`
  - Result: `found 0 vulnerabilities`.

