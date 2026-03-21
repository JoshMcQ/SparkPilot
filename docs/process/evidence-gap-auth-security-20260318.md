# Evidence Gap Action List — #58 #59 #60 #75

Date: 2026-03-18 18:05 ET

## Scope

Issues reopened because `status:needs-live-aws-evidence` / live-IdP proof requirements were not satisfied in-thread.

## Gap Matrix

| Issue | Required Evidence (from issue DoD/Acceptance) | Current Gap | Action to Close Gap |
|---|---|---|---|
| #58 | Non-prod evidence artifacts + runtime IDs + test/build results proving token is not readable from JS storage and CSP has no `unsafe-inline` in production | Thread only has generic tests/build pass note | Attach: browser/network capture or playwright artifact showing cookie-backed session flow, CSP header snapshot from non-prod runtime, and proof no `localStorage` token persistence; include run/build IDs and command outputs. |
| #59 | Non-prod evidence artifacts + runtime IDs + test/build results proving external OIDC issuer origins are allowlisted and non-allowlisted blocked | Thread only has generic tests/build pass note | Attach: one successful external issuer login trace + one blocked non-allowlisted origin trace with CSP error evidence; include runtime/build IDs. |
| #60 | Non-prod evidence artifacts + runtime IDs + test/build results proving JWKS refresh throttling under malformed token flood and successful key-rotation recovery | Thread only has generic tests/build pass note | Attach: telemetry/log artifact showing forced refresh throttling counters + key-rotation recovery path with explicit timestamps/IDs. |
| #75 | Non-prod external IdP login trace + role-scoped API requests + production-default behavior without manual token paste | Thread only has generic tests/build pass note | Attach: end-to-end login artifact (IdP -> callback -> session), role-scoped API call traces, and screenshot/video evidence that manual token path is hidden/dev-only in production config. |

## Current Decision

Keep #58/#59/#60/#75 OPEN until explicit artifact links and acceptance mapping are attached in each issue thread.
