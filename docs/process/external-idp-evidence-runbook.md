# External IdP Evidence Runbook for Issue #75

Date: 2026-03-18
Owner: SparkPilot engineering
Purpose: Unblock closure-grade acceptance evidence for **#75** (production IdP login + subject mapping) using a non-prod external OIDC provider with Authorization Code + PKCE.

## Why this exists
Issue #75 requires evidence that cannot be generated from the current local mock OIDC issuer. This runbook defines the exact inputs and capture steps needed once a non-prod external IdP (Cognito/Auth0/Okta) is available.

## Required inputs (non-prod only)
1. External OIDC issuer URL (HTTPS)
2. OIDC client ID
3. Redirect/callback URL registered in IdP (for UI)
4. Audience/scope requirements
5. Non-prod test user(s) mapped to SparkPilot roles (admin/operator)
6. Approval to capture sanitized auth/network traces (no secrets, no tokens in clear text)

## SparkPilot config mapping
Set these for the UI/API runtime used for evidence capture:
- `SPARKPILOT_AUTH_MODE=oidc`
- `SPARKPILOT_OIDC_ISSUER=<external-issuer-url>`
- `SPARKPILOT_OIDC_AUDIENCE=<audience>`
- `SPARKPILOT_OIDC_JWKS_URI=<issuer-jwks-url>`

Notes:
- Keep manual token path as explicit dev/bootstrap fallback only.
- Do not store client secrets/tokens in repo, artifacts, or screenshots.

## Evidence checklist (must capture)

### A) External IdP login trace (OIDC code + PKCE)
Capture artifacts proving real external IdP path:
1. Browser flow: login redirect -> external issuer -> callback return
2. Session established in SparkPilot UI
3. Sanitized network trace showing authorization code flow endpoints (no credentials)

Suggested artifacts:
- `artifacts/issue75-external-idp-<timestamp>/login-trace.md`
- `.../browser-redirect-sequence.txt`
- `.../sanitized-network-har.json`

### B) Subject mapping + role-scoped API proof
1. Confirm authenticated `sub` maps to identity record (`/v1/auth/me` or equivalent UI proof)
2. Execute role-scoped API calls:
   - allowed action proof (2xx)
   - denied action proof (403) for out-of-scope request
3. Include runtime identifiers where applicable (`actor/sub`, `tenant_id`, `team_id`, `environment_id`, `run_id`)

Suggested artifacts:
- `.../auth-me.json`
- `.../role-allowed-response.json`
- `.../role-denied-response.json`

### C) Production-default UX proof
1. Demonstrate IdP sign-in is default path
2. Demonstrate manual token path is hidden or clearly marked dev-only
3. Include page captures from `/access` and top-level auth entry

Suggested artifacts:
- `.../access-page-production-default.html`
- `.../auth-entry-screenshot.png`
- `.../manual-token-dev-only-proof.txt`

## Validation commands to run and include in issue

- `python -m pytest` (from repo root with venv activated)
- `cd ui && npm run lint`
- `cd ui && npm audit`

If `npm audit` reports advisories requiring breaking upgrades, document the controlled upgrade path; do not run `npm audit fix --force` blindly.

## Safety / redaction rules
- Never capture or commit access tokens, refresh tokens, client secrets, passwords, or cookies.
- Redact authorization headers and query strings containing secrets.
- Use non-prod tenant/user data only.

## Issue-thread posting template (#75)
When evidence is captured, post:
1. Acceptance criteria mapping (line-by-line)
2. Artifact links
3. Runtime IDs used in proof
4. Validation command outputs summary
5. Any observed gaps + follow-up issue links

## Primary references
- OAuth 2.0 for Native Apps (PKCE): https://datatracker.ietf.org/doc/html/rfc7636
- OpenID Connect Core: https://openid.net/specs/openid-connect-core-1_0.html
- AWS Cognito OIDC/OAuth docs: https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-userpools-server-contract-reference.html
