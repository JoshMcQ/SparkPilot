# OIDC Provider Setup Guide

SparkPilot uses OIDC (OpenID Connect) for API authentication. Every API request must include a valid JWT access token in the `Authorization: Bearer <token>` header. This guide explains exactly what SparkPilot requires from an OIDC provider and how to configure the three most common ones.

---

## Required JWT Claims

SparkPilot validates the following claims on every token:

| Claim | Required | Description |
|-------|----------|-------------|
| `sub` | Yes | Subject — unique identifier for the caller (user or service account) |
| `iss` | Yes | Issuer — must exactly match `SPARKPILOT_OIDC_ISSUER` config value |
| `aud` | Yes | Audience — must exactly match `SPARKPILOT_OIDC_AUDIENCE` config value |
| `exp` | Yes | Expiry — token must not be expired |
| `kid` (header) | Recommended | Key ID — used to look up the correct signing key from JWKS |

SparkPilot does **not** require a `tenant_id` claim in the JWT itself. Tenant and team assignment are resolved from the `sub` claim by looking up the matching `UserIdentity` record in the SparkPilot database. The `sub` value is stored as the `actor` field in `UserIdentity`.

### Signing Algorithms

SparkPilot accepts: `RS256`, `RS384`, `RS512`, `ES256`, `ES384`, `ES512`

Symmetric algorithms (`HS256`, etc.) are not accepted.

### JWKS Key Rotation

SparkPilot caches JWKS keys with a 5-minute TTL and supports forced refresh when a token's `kid` is not found in the cache. The refresh is throttled to 5 refreshes per 60-second window to prevent refresh storms. If keys rotate, users must re-authenticate to get a token signed with the new key.

---

## SparkPilot Configuration Variables

```
SPARKPILOT_AUTH_MODE=oidc
SPARKPILOT_OIDC_ISSUER=https://your-idp.example.com
SPARKPILOT_OIDC_AUDIENCE=sparkpilot-api
SPARKPILOT_OIDC_JWKS_URI=https://your-idp.example.com/.well-known/jwks.json
```

The issuer URL must match exactly (including trailing slash behavior) what appears in the JWT's `iss` claim. Most providers use the base URL without a trailing slash.

---

## Cognito (Validated)

AWS Cognito User Pools with OIDC federation are the validated path for SparkPilot.

### Configuration

1. Create a Cognito User Pool with an App Client
2. Enable the `client_credentials` OAuth flow for machine-to-machine auth
3. Create a Resource Server with identifier `sparkpilot-api` and scope `sparkpilot-api/access`

```
SPARKPILOT_OIDC_ISSUER=https://cognito-idp.<region>.amazonaws.com/<user-pool-id>
SPARKPILOT_OIDC_AUDIENCE=sparkpilot-api
SPARKPILOT_OIDC_JWKS_URI=https://cognito-idp.<region>.amazonaws.com/<user-pool-id>/.well-known/jwks.json
```

Token endpoint for client credentials:
```
POST https://<cognito-domain>.auth.<region>.amazoncognito.com/oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=<app-client-id>
&client_secret=<app-client-secret>
&scope=sparkpilot-api/access
```

**Notes:**
- Cognito `iss` includes the region and pool ID, e.g. `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XXXXXXX`
- Cognito `aud` for client_credentials tokens is the App Client ID. Set `SPARKPILOT_OIDC_AUDIENCE` to the App Client ID.
- The `sub` claim is the App Client ID for machine tokens. Register this as the `actor` in SparkPilot's UserIdentity table.

### Validated Status

Cognito OIDC has been end-to-end validated with SparkPilot — see `artifacts/issue75-cognito-live-evidence-20260318-*` for evidence.

---

## Auth0

Auth0 supports `client_credentials` for machine-to-machine (M2M) applications. Configuration steps do not require a live test — the required claims are standard OIDC.

### Configuration

1. Create an API in the Auth0 dashboard with identifier `sparkpilot-api`
2. Create a Machine to Machine Application and authorize it against the API
3. Note the `Domain`, `Client ID`, and `Client Secret`

```
SPARKPILOT_OIDC_ISSUER=https://<your-auth0-domain>/
SPARKPILOT_OIDC_AUDIENCE=sparkpilot-api
SPARKPILOT_OIDC_JWKS_URI=https://<your-auth0-domain>/.well-known/jwks.json
```

Token request:
```
POST https://<your-auth0-domain>/oauth/token
Content-Type: application/json

{
  "grant_type": "client_credentials",
  "client_id": "<client-id>",
  "client_secret": "<client-secret>",
  "audience": "sparkpilot-api"
}
```

**Notes:**
- Auth0 `iss` includes a trailing slash: `https://<domain>/`. Set `SPARKPILOT_OIDC_ISSUER` with the trailing slash.
- The `sub` for M2M tokens is `<client-id>@clients`. Register this pattern as the `actor` in UserIdentity.
- Auth0 RS256 signing keys are rotated periodically. SparkPilot handles this automatically via JWKS refresh.

### Claim Compatibility

Auth0 M2M tokens include `sub`, `iss`, `aud`, `exp`, and `iat` — all required claims are present with no custom configuration needed.

---

## Okta

Okta Workforce Identity and Customer Identity Cloud (formerly Auth0) both work. These steps cover Okta Workforce Identity (OIDC with OAuth 2.0).

### Configuration

1. In Okta Admin Console, create an OAuth 2.0 Service App (for M2M)
2. Grant the app the `client_credentials` flow
3. Create a custom Authorization Server (or use `default`) with audience `sparkpilot-api`

```
SPARKPILOT_OIDC_ISSUER=https://<okta-domain>/oauth2/<auth-server-id>
SPARKPILOT_OIDC_AUDIENCE=sparkpilot-api
SPARKPILOT_OIDC_JWKS_URI=https://<okta-domain>/oauth2/<auth-server-id>/v1/keys
```

For the default auth server:
```
SPARKPILOT_OIDC_ISSUER=https://<okta-domain>/oauth2/default
SPARKPILOT_OIDC_JWKS_URI=https://<okta-domain>/oauth2/default/v1/keys
```

Token request:
```
POST https://<okta-domain>/oauth2/<auth-server-id>/v1/token
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64(client_id:client_secret)>

grant_type=client_credentials
&scope=sparkpilot-api
```

**Notes:**
- Okta `iss` is `https://<okta-domain>/oauth2/<auth-server-id>` — must match exactly.
- The `sub` for service apps is the Client ID. Register this as `actor` in UserIdentity.
- Okta custom Authorization Servers support audience configuration. The `default` auth server uses `api://default` as the audience — use a custom auth server if you need `sparkpilot-api` as the audience value.

### Required Custom Scope

Okta requires at least one scope to be requested on client_credentials. Create a custom scope named `sparkpilot-api` on your Authorization Server.

---

## Local Development (Mock OIDC)

For local development, SparkPilot ships with a mock OIDC server (`sparkpilot.mock_oidc`).

```
SPARKPILOT_OIDC_ISSUER=http://localhost:8080
SPARKPILOT_OIDC_AUDIENCE=sparkpilot-api
SPARKPILOT_OIDC_JWKS_URI=http://localhost:8080/.well-known/jwks.json
```

Default clients (configurable via `MOCK_OIDC_CLIENTS` env var):
- `sparkpilot-ui` / `sparkpilot-ui-secret`
- `sparkpilot-cli` / `sparkpilot-cli-secret`

---

## Registering Actors in SparkPilot

After configuring OIDC, you must register the JWT `sub` value as a `UserIdentity` in SparkPilot. Use the bootstrap endpoint:

```
POST /v1/bootstrap/user-identities
X-Bootstrap-Secret: <SPARKPILOT_BOOTSTRAP_SECRET>

{
  "actor": "<sub-claim-from-jwt>",
  "role": "admin",
  "tenant_id": null,
  "team_id": null,
  "active": true
}
```

Roles: `admin` (full access), `operator` (tenant-scoped), `user` (tenant + team scoped, own runs only).

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `OIDC JWT is missing required subject claim` | Token has empty `sub` | Enable `sub` claim in IdP configuration |
| `JWT kid was not found in configured JWKS` | Key rotation or wrong JWKS URI | Verify `SPARKPILOT_OIDC_JWKS_URI` points to live endpoint |
| `OIDC JWT validation failed: Invalid audience` | `aud` mismatch | Align `SPARKPILOT_OIDC_AUDIENCE` with what the IdP puts in `aud` |
| `OIDC JWT validation failed: Invalid issuer` | `iss` mismatch | Align `SPARKPILOT_OIDC_ISSUER` exactly, including trailing slash |
| `Signing keys have changed. Please sign in again` | Key rotation event | Re-authenticate to get a new token |
| `Unknown or inactive actor` | `sub` not registered | Call `/v1/bootstrap/user-identities` to register the actor |
