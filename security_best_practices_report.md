# SparkPilot Security Best Practices Review

Date: 2026-03-04  
Updated: 2026-03-04  
Scope reviewed: `src/`, `ui/`, `providers/airflow/`, `infra/cloudformation/`, `docker/`

## Executive Summary

All previously reported findings (`F-001` through `F-008`) are now remediated in code.  
The highest-risk items (identity spoofing and browser-side credential exposure) were fixed first, then platform hardening changes were completed across IAM policy scope, CORS/docs posture, container runtime user, and Airflow provider auth behavior.

## Verification Summary

- Backend/API/provider test suite: `pytest -q` => `113 passed, 1 skipped` (run on 2026-03-04)
- UI build/typecheck: `npm --prefix ui run build` => success (run on 2026-03-04)

## Findings Status

### F-001: Actor Impersonation via Unbound `X-Actor` Header
- Rule ID: `FASTAPI-AUTH-001` / `FASTAPI-AUTHZ-001`
- Original Severity: Critical
- Status: Fixed
- Implementation:
  - Authenticated actor is now derived from verified OIDC token `sub`, not a caller-supplied header.
  - OIDC validation is enforced for bearer tokens before RBAC context resolution.
- Code references:
  - `src/sparkpilot/api.py:122`
  - `src/sparkpilot/api.py:137`
  - `src/sparkpilot/api.py:154`
  - `src/sparkpilot/oidc.py:125`
- Validation references:
  - `tests/test_api.py:102`
  - `tests/test_security_hardening.py:29`

### F-002: API Bearer Token Exposure to Browser Code
- Rule ID: `NEXT-SECRETS-001` / `NEXT-AUTH-001`
- Original Severity: Critical
- Status: Fixed
- Implementation:
  - Browser API module now calls same-origin proxy routes only (`/api/sparkpilot`).
  - Authorization header creation moved server-side in route handler/server helper using OIDC client credentials.
  - Removed browser path dependence on public bearer token env vars.
- Code references:
  - `ui/lib/api.ts:1`
  - `ui/app/api/sparkpilot/[...path]/route.ts:49`
  - `ui/app/api/sparkpilot/[...path]/route.ts:109`
  - `ui/lib/api-server.ts:45`
  - `ui/lib/api-server.ts:111`

### F-003: Over-Permissive BYOC Bootstrap IAM Role
- Rule ID: `CLOUD-IAM-LEAST-PRIVILEGE`
- Original Severity: High
- Status: Fixed
- Implementation:
  - Broad permissions were decomposed into scoped statements.
  - Tag-based conditions and role/resource scoping were applied for managed resources.
  - `iam:PassRole` constrained to execution role patterns.
- Code references:
  - `infra/cloudformation/customer-bootstrap.yaml:36`
  - `infra/cloudformation/customer-bootstrap.yaml:50`
  - `infra/cloudformation/customer-bootstrap.yaml:132`
  - `infra/cloudformation/customer-bootstrap.yaml:151`

### F-004: FastAPI Docs/OpenAPI Enabled by Default
- Rule ID: `FASTAPI-OPENAPI-001`
- Original Severity: Medium
- Status: Fixed
- Implementation:
  - `/docs`, `/redoc`, and `/openapi.json` are disabled when environment is production.
- Code references:
  - `src/sparkpilot/api.py:95`
  - `src/sparkpilot/api.py:96`
  - `src/sparkpilot/api.py:97`

### F-005: Missing Baseline Next.js Security Headers
- Rule ID: `NEXT-HEADERS-BASELINE`
- Original Severity: Medium
- Status: Fixed
- Implementation:
  - Added CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`.
- Code references:
  - `ui/next.config.mjs:23`
  - `ui/next.config.mjs:27`
  - `ui/next.config.mjs:31`
  - `ui/next.config.mjs:35`
  - `ui/next.config.mjs:39`

### F-006: Broad CORS and Weak Origin Validation
- Rule ID: `FASTAPI-CORS-001`
- Original Severity: Medium
- Status: Fixed
- Implementation:
  - CORS methods and headers were narrowed to explicit allowlists.
  - Startup validation now rejects wildcard origins and malformed origin strings under credentialed CORS.
- Code references:
  - `src/sparkpilot/api.py:116`
  - `src/sparkpilot/api.py:117`
  - `src/sparkpilot/config.py:98`
  - `src/sparkpilot/config.py:103`
- Validation references:
  - `tests/test_api.py:142`
  - `tests/test_config.py:80`

### F-007: API/Worker Containers Running as Root
- Rule ID: `CONTAINER-HARDENING-001`
- Original Severity: Low
- Status: Fixed
- Implementation:
  - API and worker images now create and switch to non-root `sparkpilot` user.
- Code references:
  - `docker/api.Dockerfile:16`
  - `docker/api.Dockerfile:20`
  - `docker/worker.Dockerfile:16`
  - `docker/worker.Dockerfile:20`

### F-008: Airflow Hook Fail-Open on Missing Auth
- Rule ID: `AUTH-FAIL-CLOSED-001`
- Original Severity: Low
- Status: Fixed
- Implementation:
  - Hook now requires OIDC fields and raises on missing auth config.
  - Request headers are built with bearer token auth by design; no unauthenticated fallback path.
- Code references:
  - `providers/airflow/src/airflow/providers/sparkpilot/hooks/sparkpilot.py:149`
  - `providers/airflow/src/airflow/providers/sparkpilot/hooks/sparkpilot.py:163`
  - `providers/airflow/src/airflow/providers/sparkpilot/hooks/sparkpilot.py:190`
  - `providers/airflow/src/airflow/providers/sparkpilot/hooks/sparkpilot.py:243`
- Validation references:
  - `tests/test_airflow_provider.py:42`
  - `tests/test_airflow_provider.py:75`
  - `tests/test_airflow_provider.py:97`

## Additional Remediation Hardening

During fix verification, additional auth-hardening robustness updates were applied:

- OIDC `file://` JWKS loading now handles Windows local paths correctly.
- Malformed bearer tokens now consistently map to `OIDCValidationError` flows instead of decode exceptions.
- Test harness now uses per-process JWKS files and deterministic bootstrap identity seeding to avoid key-race false negatives in CI.

Code references:
- `src/sparkpilot/oidc.py:35`
- `src/sparkpilot/oidc.py:41`
- `src/sparkpilot/oidc.py:102`
- `tests/conftest.py:27`
- `tests/conftest.py:92`

## Current Recommendation

Keep this report as the remediation baseline and treat any regression in the referenced files/tests as a release blocker.
