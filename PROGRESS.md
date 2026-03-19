# SparkPilot Production Hardening Progress

Last updated: 2026-03-19 13:39 ET

## Proof rule

Only mark an item complete when there is direct evidence in-repo or captured command output from this machine/session. If evidence is missing, the item stays unchecked.

## Phase 0 - Tracker correction

- [x] Replace the inaccurate completion-only tracker with a proof-based tracker. <!-- completed 2026-03-19 13:24 ET -->

### Blocker log
- 2026-03-19 13:24 ET - Prior tracker overstated completion. Multiple areas called complete were not backed by current proof in repo/session history.

## Phase 4 - UI overhaul (production-grade proof required)

- [ ] Build and validate a real AWS login/onboarding flow with evidence (implementation + tested happy path + failure states).
- [x] Add dark mode with implementation proof and UI verification evidence. <!-- completed 2026-03-19 13:49 ET -->
- [ ] Run a Lighthouse audit and record results/artifacts.
- [ ] Perform responsive testing and record viewport/device evidence.
- [ ] Perform cross-browser testing and record browser-by-browser evidence.

### Blocker log
- 2026-03-19 13:24 ET - No current proof captured for a production-grade AWS onboarding flow, dark mode, Lighthouse audit, responsive validation, or cross-browser validation.
- 2026-03-19 13:28 ET - Added a dedicated `/onboarding/aws` route that connects sign-in, identity verification, access review, and environment setup entry points, but the item remains unchecked because there is still no captured browser evidence for happy path, failure states, responsive behavior, or cross-browser behavior.

## Phase 5 - Demo evidence

- [ ] Record the required demo and store/link the artifact.

### Blocker log
- 2026-03-19 13:24 ET - No demo recording artifact has been proven in this session.

## Phase 6 - CUR reconciliation

- [ ] Test CUR reconciliation against real CUR data and capture evidence.

### Blocker log
- 2026-03-19 13:24 ET - No proof yet of real CUR-data reconciliation execution.

## Phase 7 - Clean code follow-through

- [ ] Re-scan remaining complexity hotspots, document the current list with evidence, and complete the next refactor in priority order.

### Blocker log
- 2026-03-19 13:24 ET - Prior notes referenced unresolved C901 hotspots / incomplete clean-code follow-through. Current tracker had incorrectly implied clean-code completion.

## Verification passes

### 2026-03-19 13:24 ET (tracker correction)
- `git status --short --branch`
  - Result: working tree is not clean; there are modified and untracked files, including tracker/log updates plus pre-existing service/UI/tmp artifacts.
- Complexity scan (AST branch-count proxy over `src/**/*.py`)
  - Result: multiple high-complexity candidates still exist, including `src/sparkpilot/services/preflight_checks.py`, `src/sparkpilot/services/preflight.py`, `src/sparkpilot/services/preflight_byoc.py`, `src/sparkpilot/services/workers_provisioning.py`, and others.
- Evidence gap review
  - Result: no current proof was captured for demo recording, Lighthouse, responsive testing, cross-browser testing, dark mode, real AWS onboarding flow validation, or real CUR reconciliation. Those items remain unchecked until proven.

### 2026-03-19 13:28 ET (Phase 4 first unchecked item - in progress, not complete)
- Added dedicated onboarding route: `ui/app/onboarding/aws/page.tsx`
  - Result: new guided AWS onboarding page now exists and ties together OIDC/manual auth state, identity verification, access review, and environment setup entry points.
- Updated navigation / entry points
  - Result: top nav now includes `Onboarding`; home CTA now points to `/onboarding/aws`; environments page links back to onboarding.
- `python -m pytest -q`
  - Result: `327 passed, 6 skipped`.
- `cd ui && npm run lint`
  - Result: clean after fixing one initial React hook warning in the new onboarding page.
- `cd ui && npm audit`
  - Result: `found 0 vulnerabilities`.
- Truth check
  - Result: the AWS onboarding phase remains unchecked because there is still no browser-captured proof for end-to-end login/onboarding success, no failure-path evidence, and no responsive/cross-browser/Lighthouse proof.

### 2026-03-19 13:39 ET (Phase 4 first unchecked item - completed with browser evidence)
- Added browser smoke harness for onboarding flow
  - Result: added `ui/playwright.config.ts`, `ui/tests/e2e/onboarding.spec.ts`, and `ui/.gitignore`; UI lint config now ignores transient Playwright output directories.
- Fixed onboarding runtime issue uncovered by Chromium
  - Result: restored the missing `USER_ACCESS_TOKEN_CHANGED_EVENT` import and confirmed the page no longer crashes during browser navigation.
- `cd ui && npm run test:e2e:onboarding`
  - Result: `3 passed` covering unauthenticated guidance, authenticated happy-path visibility, and missing-scope/failure-path behavior.
- `python -m pytest -q`
  - Result: `327 passed, 6 skipped`.
- `cd ui && npm run lint`
  - Result: clean after excluding transient `playwright-report/`, `test-results/`, and `.next/` artifacts from ESLint traversal.
- `cd ui && npm audit`
  - Result: `found 0 vulnerabilities`.
- Scope note
  - Result: this completes the login/onboarding implementation + browser-tested happy/failure-path evidence requirement, but does not count as responsive/cross-browser/Lighthouse/dark-mode proof; those remain separate unchecked items below.

### 2026-03-19 13:49 ET (Phase 4 dark mode - completed with UI verification evidence)
- Added persisted theme toggle
  - Result: new `ui/components/theme-toggle.tsx` toggles light/dark mode, persists the choice in `localStorage`, and applies the theme via `data-theme` on the root element.
- Added dark-theme tokens and header wiring
  - Result: `ui/app/styles/tokens.css` now defines a dark palette; `ui/app/layout.tsx` exposes the toggle in the header; `ui/app/globals.css` adds dark-mode-aware header/nav styling hooks.
- Added browser verification for dark mode
  - Result: `ui/tests/e2e/theme-toggle.spec.ts` verifies dark-mode toggle behavior and persistence after reload in Chromium.
- `cd ui && npm run test:e2e:theme`
  - Result: `1 passed`.
- `cd ui && npm run test:e2e:onboarding && npm run test:e2e:theme`
  - Result: `3 passed` + `1 passed` after the dark-mode change.
- `python -m pytest -q`
  - Result: `327 passed, 6 skipped`.
- `cd ui && npm run lint`
  - Result: clean after fixing an intermediate layout syntax error and a hydration mismatch in the first dark-mode implementation.
- `cd ui && npm audit`
  - Result: `found 0 vulnerabilities`.

### 2026-03-19 13:50 ET (mandatory 3-task verification pass)
- `cd C:\Users\JoshMcQueary\SparkPilot && .\.venv\Scripts\python -m pytest`
  - Result: `327 passed, 6 skipped in 37.35s`.
- `cd C:\Users\JoshMcQueary\SparkPilot\ui && npm run lint`
  - Result: clean.
- `cd C:\Users\JoshMcQueary\SparkPilot && git diff --stat`
  - Result: current unstaged diff still includes intentional tracker/dark-mode updates plus pre-existing unrelated service/UI changes already present on this branch.
- `cd C:\Users\JoshMcQueary\SparkPilot && git log -5 -p | Select-String "AKIA|sk-|password|secret"`
  - Result: no credential-like secret strings detected; only generic documentation/test references to `secret`.
onsive/cross-browser/Lighthouse proof.
hthouse/dark-mode proof; those remain separate unchecked items below.
onsive/cross-browser/Lighthouse proof.
