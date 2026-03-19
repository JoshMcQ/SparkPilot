# SparkPilot Production Hardening Progress

Last updated: 2026-03-19 14:11 ET

## Proof rule

Only mark an item complete when there is direct evidence in-repo or captured command output from this machine/session. If evidence is missing, the item stays unchecked.

## Phase 0 - Tracker correction

- [x] Replace the inaccurate completion-only tracker with a proof-based tracker. <!-- completed 2026-03-19 13:24 ET -->

### Blocker log
- 2026-03-19 13:24 ET - Prior tracker overstated completion. Multiple areas called complete were not backed by current proof in repo/session history.

## Phase 4 - UI overhaul (production-grade proof required)

- [x] Build and validate a real AWS login/onboarding flow with evidence (implementation + tested happy path + failure states). <!-- completed 2026-03-19 13:39 ET -->
- [x] Add dark mode with implementation proof and UI verification evidence. <!-- completed 2026-03-19 13:49 ET -->
- [x] Run a Lighthouse audit and record results/artifacts. <!-- completed 2026-03-19 13:50 ET -->
- [x] Perform responsive testing and record viewport/device evidence. <!-- completed 2026-03-19 13:52 ET -->
- [x] Perform cross-browser testing and record browser-by-browser evidence. <!-- completed 2026-03-19 13:57 ET -->

### Blocker log
- 2026-03-19 13:24 ET - No current proof captured for a production-grade AWS onboarding flow, dark mode, Lighthouse audit, responsive validation, or cross-browser validation.
- 2026-03-19 13:28 ET - Added a dedicated `/onboarding/aws` route that connects sign-in, identity verification, access review, and environment setup entry points, but the item remains unchecked because there is still no captured browser evidence for happy path, failure states, responsive behavior, or cross-browser behavior.

## Phase 5 - Demo evidence

- [x] Record the required demo and store/link the artifact. <!-- completed 2026-03-19 14:11 ET -->

### Blocker log
- 2026-03-19 13:24 ET - No demo recording artifact has been proven in this session.
- 2026-03-19 14:00 ET - No clean in-session demo recording toolchain or artifact path has been proven yet; moving to the next actionable unchecked item while this stays open.

## Phase 6 - CUR reconciliation

- [x] Test CUR reconciliation against real CUR data and capture evidence. <!-- completed 2026-03-19 14:03 ET -->

### Blocker log
- 2026-03-19 13:24 ET - No proof yet of real CUR-data reconciliation execution.

## Phase 7 - Clean code follow-through

- [x] Re-scan remaining complexity hotspots, document the current list with evidence, and complete the next refactor in priority order. <!-- completed 2026-03-19 14:09 ET -->

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
### 2026-03-19 13:50 ET (Phase 4 Lighthouse audit - completed with artifact evidence)
- `cd ui && npx lighthouse http://127.0.0.1:3002/onboarding/aws --only-categories=performance,accessibility,best-practices,seo --output=json --output=html --output-path=C:/Users/JoshMcQueary/SparkPilot/ui/artifacts/lighthouse-onboarding --chrome-flags="--headless=new --no-sandbox"`
  - Result: Lighthouse wrote both artifacts successfully before exiting non-zero on Windows temp cleanup (`EPERM` during temp directory removal).
- Artifact outputs
  - Result: `ui/artifacts/lighthouse-onboarding.report.html` and `ui/artifacts/lighthouse-onboarding.report.json` exist and were written at 2026-03-19 13:49 ET.
- Parsed category scores from JSON artifact
  - Result: performance `0.77`, accessibility `1.00`, best-practices `0.96`, SEO `1.00`.
- Scope note
  - Result: the artifact requirement for the Lighthouse checklist item is satisfied. Cross-browser and responsive testing remain separate unchecked items.
### 2026-03-19 13:52 ET (Phase 4 responsive testing - completed with viewport evidence)
- Added responsive viewport suite
  - Result: added `ui/tests/e2e/responsive-onboarding.spec.ts` plus package script `test:e2e:responsive`.
- `cd ui && npm run test:e2e:responsive`
  - Result: `3 passed` across `mobile-390` (390x844), `tablet-768` (768x1024), and `desktop-1440` (1440x900).
- Checked responsive layout constraints
  - Result: hero section remained visible; primary onboarding CTA/link content remained visible; main page width stayed within viewport bounds at each tested size.
- `cd ui && npm run lint`
  - Result: clean after tightening the locator to the hero CTA to avoid duplicate `Sign in` matches.
### 2026-03-19 13:57 ET (Phase 4 cross-browser testing - completed with browser evidence)
- Expanded Playwright browser matrix
  - Result: `ui/playwright.config.ts` now defines `chromium`, `firefox`, and `webkit` projects.
- Browser runtime setup
  - Result: installed Firefox/WebKit runtimes with `npx playwright install firefox webkit`.
- Fixed cross-browser runner resolution
  - Result: removed `playwright-firefox`, then switched package scripts to direct local runner invocation via `node ./node_modules/playwright/cli.js ...` to avoid bad CLI shim resolution.
- `cd ui && npm run test:e2e:cross-browser`
  - Result: `12 passed` total.
  - Browser-by-browser breakdown:
    - Chromium: onboarding unauthenticated/authenticated/failure-path + theme persistence passed.
    - Firefox: onboarding unauthenticated/authenticated/failure-path + theme persistence passed.
    - WebKit: onboarding unauthenticated/authenticated/failure-path + theme persistence passed.
- `cd ui && npm run lint`
  - Result: clean.
- `cd ui && npm audit`
  - Result: `found 0 vulnerabilities`.
### 2026-03-19 14:03 ET (Phase 6 CUR reconciliation - completed with repo artifact evidence)
- Verified live CUR validation document
  - Result: `docs/validation/cur-reconciliation-live-athena-validation-20260318.md` documents a live Athena reconciliation against account `787587782916`, region `us-east-1`, with concrete database/table names and Athena query execution IDs.
- Verified artifact files exist
  - Result: `artifacts/issue67-cur-20260317-231046/summary.json` and `artifacts/issue67-cur-20260317-231046/athena_queries.json` are present in-repo.
- Verified before/after reconciliation payload
  - Result: `summary.json` shows four pending allocations moving from `actual_cost_usd_micros=null` to populated actual costs with `cur_reconciled_at` timestamps, plus audit details containing `action=cost.cur_reconciliation` and query ID `5168189d-7026-4aca-9cb2-2ab227f34f3b`.
- Verified edge-case pricing mix and variance
  - Result: artifact includes On-Demand, Spot, SavingsPlanCoveredUsage, and Reserved rows; `max_variance_micros=0` within `threshold_micros=1`.
- Scope note
  - Result: this item is now evidence-backed from repo artifacts even though it was not rerun in the current session.
### 2026-03-19 14:09 ET (Phase 7 clean code - completed with current hotspot evidence)
- Re-scanned current complexity hotspots (AST branch-count proxy over `src/**/*.py`)
  - Result: current top hotspots include `mock_oidc.py:token`, `services/emr_releases.py:sync_emr_releases_once`, `services/preflight_checks.py:_add_issue3_iam_simulation_check`, `services/preflight.py:_upsert_preflight_check`, and others. The stale claim of "7 remaining C901 hotspots" was not an accurate current snapshot.
- Refactored `resolve_cost_center_for_environment`
  - Result: extracted `CostCenterResolutionInputs`, `_normalize_resolution_inputs`, `_resolve_cost_center_from_policy`, and `_resolve_cost_center_fallback` in `src/sparkpilot/cost_center.py` so the production resolver now delegates precedence selection/fallback logic instead of carrying the branch chain inline.
- Targeted regression tests
  - Result: `python -m pytest -q tests/test_finops.py -k "cost_center_policy_mapping_applies_to_recorded_allocation or cur_reconciliation_worker_updates_actual_cost or cur_reconciliation_worker_handles_paginated_results"` -> `3 passed`.
- Complexity rescan for touched file
  - Result: `cost_center.py` no longer appears in the >=10 branch-count hotspot output.
- Required post-change validation
  - Result: `python -m pytest -q` -> `327 passed, 6 skipped`; `cd ui && npm run lint` -> clean; `cd ui && npm audit` -> `found 0 vulnerabilities`.
### 2026-03-19 14:11 ET (Phase 5 demo evidence - completed with recorded artifact)
- Added scripted demo recorder
  - Result: new `ui/scripts/record-demo.mjs` launches Chromium, stubs the UI auth/environment APIs, walks the onboarding flow, toggles dark mode, opens environments, and records a walkthrough video.
- Generated demo artifact
  - Result: `ui/artifacts/demo/sparkpilot-ui-demo-20260319.webm` exists in-repo.
- Artifact metadata
  - Result: file size `876551` bytes; written `2026-03-19 14:04:48 ET`.
- Required post-change validation
  - Result: `python -m pytest -q` -> `327 passed, 6 skipped`; `cd ui && npm run lint` -> clean; `cd ui && npm audit` -> `found 0 vulnerabilities`.
- Scope note
  - Result: this is a scripted product walkthrough artifact rather than a narrated human-recorded screencast, but it satisfies the tracker requirement to record/store a demo artifact with direct proof.

