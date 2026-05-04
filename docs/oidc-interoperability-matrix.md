# OIDC Interoperability Matrix

> Issue: #69 — OIDC interoperability matrix with real IdPs (Cognito/Auth0/Okta)

## Overview

SparkPilot's authentication layer supports any OIDC-compliant Identity Provider
via standard discovery, authorization code + PKCE flow, and JWKS-backed JWT
verification. This document details the interoperability matrix, failure modes,
and evidence patterns.

## Architecture

```
Browser → OIDC IdP (Cognito/Auth0/Okta) → Authorization Code + PKCE
    ↓
Callback → Token Exchange → access_token (JWT)
    ↓
POST /api/auth/session → HttpOnly cookie (sparkpilot.session)
    ↓
API Request → Bearer token → OIDCTokenVerifier → verify claims → authorize
```

## IdP Configuration Matrix

| IdP | Issuer URL Pattern | Discovery | PKCE | Notes |
|-----|--------------------|-----------|------|-------|
| **AWS Cognito** | `https://cognito-idp.{region}.amazonaws.com/{pool-id}` | `/.well-known/openid-configuration` | S256 | Requires `NEXT_PUBLIC_OIDC_AUDIENCE` = Cognito App Client ID |
| **Auth0** | `https://{tenant}.auth0.com/` | Standard | S256 | Use audience = API identifier |
| **Okta** | `https://{org}.okta.com/oauth2/{server}` | Standard | S256 | Use custom auth server for audience |
| **Keycloak** | `https://{host}/realms/{realm}` | Standard | S256 | Works out of the box |
| **Azure AD** | `https://login.microsoftonline.com/{tenant}/v2.0` | Standard | S256 | Use v2.0 endpoints |

## Environment Configuration

### Backend (`src/sparkpilot/config.py`)

```bash
SPARKPILOT_AUTH_MODE=oidc
SPARKPILOT_OIDC_ISSUER=https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XXXXXX
SPARKPILOT_OIDC_AUDIENCE=sparkpilot-api
SPARKPILOT_OIDC_JWKS_URI=https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XXXXXX/.well-known/jwks.json
```

### UI (`ui/.env.local`)

```bash
NEXT_PUBLIC_OIDC_ISSUER=https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XXXXXX
NEXT_PUBLIC_OIDC_CLIENT_ID=<cognito-app-client-id>
NEXT_PUBLIC_OIDC_REDIRECT_URI=https://app.example.com/auth/callback
NEXT_PUBLIC_OIDC_AUDIENCE=<cognito-app-client-id>
```

### CSP connect-src (`ui/next.config.mjs`)

```bash
# Automatically derived from NEXT_PUBLIC_OIDC_ISSUER
# Additional origins: comma-separated
NEXT_PUBLIC_OIDC_CONNECT_ORIGINS=https://token.example.com,https://auth.example.com
```

## Verified Flows

### 1. OIDC Discovery
- Fetches `/.well-known/openid-configuration`
- Extracts `authorization_endpoint` and `token_endpoint`
- Supports `file://` URI for test/local JWKS

### 2. Authorization Code + PKCE
- Generates 32-byte random code verifier + SHA-256 challenge
- State parameter prevents CSRF
- Token exchange uses `code_verifier` for proof
- No client secret required (public client)

### 3. JWT Verification
- **RS256/ES256** algorithm support
- Validates `iss`, `aud`, `exp`, `sub` claims
- JWKS cached with TTL (default 300s)
- Automatic forced refresh on kid mismatch

### 4. Key Rotation
- Detects unknown `kid` → forces JWKS refresh
- Detects signature failure → retries with refreshed JWKS
- Raises `OIDCKeyRotationError` with user-facing message
- API returns `X-SparkPilot-Auth-Hint: key-rotation` header

### 5. Session Management
- `POST /api/auth/session` stores token in HttpOnly cookie
- `DELETE /api/auth/session` clears cookie
- `GET /api/auth/session` returns `{authenticated: true/false}`
- Cookie: `HttpOnly; Secure; SameSite=Strict; Path=/`

## Failure Modes & Remediation

| Failure | HTTP Status | Error Detail | Remediation |
|---------|-------------|--------------|-------------|
| Missing bearer token | 401 | "Missing or invalid bearer token." | Sign in via IdP or provide Authorization header |
| Expired token | 401 | "Expired Signature" | Re-authenticate with IdP |
| Wrong audience | 401 | "Invalid audience" | Set `SPARKPILOT_OIDC_AUDIENCE` to match IdP config |
| Wrong issuer | 401 | "Invalid issuer" | Set `SPARKPILOT_OIDC_ISSUER` to match token issuer |
| Key rotation | 401 | "Signing keys have changed" | Re-authenticate (header: `X-SparkPilot-Auth-Hint: key-rotation`) |
| JWKS refresh throttled | 401 | "JWKS refresh was throttled" | Wait and retry, or re-authenticate |
| Unknown kid | 401 | "JWT kid was not found" | Verify JWKS URI contains the correct signing keys |
| CSP blocks IdP | Browser error | CSP `connect-src` violation | Add IdP origin to `NEXT_PUBLIC_OIDC_CONNECT_ORIGINS` |
| No identity mapping | 403 | RBAC forbidden | Create user identity via `POST /v1/user-identities` |

## JWKS Refresh Throttle Policy

| Parameter | Default | Purpose |
|-----------|---------|---------|
| Min refresh interval | 10s | Prevents rapid successive refreshes |
| Throttle window | 60s | Sliding window for counting refreshes |
| Max refreshes per window | 5 | Caps forced refreshes to prevent storms |

Telemetry exposed via `verifier.jwks_refresh_stats`:
```json
{"total": 3, "forced": 1, "throttled": 0}
```

## Test Coverage

14 automated tests in `tests/test_api.py` (prefix `test_oidc_*`):

| Test | Validates |
|------|-----------|
| `test_oidc_discovery_rs256_token_verified` | RS256 token verification end-to-end |
| `test_oidc_expired_token_rejected` | Expired token → OIDCValidationError |
| `test_oidc_wrong_audience_rejected` | Wrong audience → rejected |
| `test_oidc_wrong_issuer_rejected` | Wrong issuer → rejected |
| `test_oidc_key_rotation_triggers_refresh` | New kid → forced JWKS refresh |
| `test_oidc_throttle_prevents_refresh_storm` | Rapid refreshes throttled |
| `test_oidc_api_rejects_missing_bearer` | 401 for missing token |
| `test_oidc_api_rejects_malformed_jwt` | 401 for invalid JWT |
| `test_oidc_auth_me_returns_identity` | /auth/me returns subject and role |
| `test_oidc_session_cookie_flow` | Bearer token reuse pattern |
| `test_oidc_multiple_idp_config_pattern` | Cross-issuer isolation |
| `test_oidc_verifier_jwks_stats` | Telemetry counters exposed |
| `test_byoc_lite_oidc_missing_fails_before_trust_update` | OIDC ↔ BYOC integration |
| `test_matrix_oidc_association_missing_fails` | Preflight matrix OIDC check |
