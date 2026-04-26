# Onboarding Gaps (Manual Risk Ranking)

## Placeholders
- None

## Ranking Method
- Rank 1 is highest risk to break onboarding or leak sensitive data.
- Priority weights: secret exposure risk > auth misconfiguration blast radius > repeated operator error rate.

## Ranked Gaps

| Rank | Manual Step | Current Risk | Why It Breaks/Leaks | Automation Target |
|---|---|---|---|---|
| 1 | Bootstrap secret delivered manually over ad-hoc channels | Secret leak | Human copy/paste into wrong thread or persistent chat; global bootstrap secret exposure risk is high | One-time secret broker with TTL, recipient binding, access audit |
| 2 | Cognito external IdP setup done manually per customer | Login outage | Mis-typed metadata URL, wrong cert, wrong issuer, wrong client secret blocks all sign-ins for that customer | IdP onboarding command that validates metadata and dry-runs auth before enabling |
| 3 | App client callback/logout + supported IdP updates done manually | Auth redirect failures | Missing callback or provider mapping causes hosted UI loops or `redirect_uri_mismatch` | Declarative app-client policy sync with drift detection |
| 4 | Tenant/team bootstrap done via manual API/UI sequence | Inconsistent authorization state | Missing tenant/team link produces partial onboarding and post-login 403s | Atomic bootstrap transaction endpoint (`tenant + team + scopes`) |
| 5 | User identity mapping entered manually in `/access` | Wrong principal mapped | Operator typo in `sub` or wrong role grants/denies access incorrectly | Admin import workflow from signed user list + claim preview |
| 6 | Staging/prod deploy gates rely on manually maintained GitHub env vars | Environment drift | Missing `*_CORS_ORIGINS` or wrong `*_UI_APP_BASE_URL` breaks runtime after deploy | Policy-as-code check for required vars/secrets before deploy starts |
| 7 | Runtime verification depends on ad-hoc command execution | Incomplete evidence | Operators skip negative-path checks (invalid JWT, unknown actor, startup fail cases) | Single command verification harness that emits pass/fail report artifact |
| 8 | Customer comms package assembled manually | Process inconsistency | Wrong URL, stale instructions, or mixed channel handling for sensitive data | Versioned onboarding packet generator with enforced channel split |

## Immediate Next Automations
1. One-time bootstrap secret delivery service.
2. Cognito IdP + app-client declarative sync tooling.
3. Bootstrap transaction API for tenant/team/scopes.
4. Automated staging verification harness (startup gate + Cognito auth + bootstrap flow).

