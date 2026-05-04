# Auth configuration (OIDC discovery values)

These are the public OIDC discovery values for the SparkPilot Cognito pools.
None of these values are secrets — they appear in JWT `iss` and `aud` claims
and on the Cognito Hosted UI URL. They live here for convenient reference
outside of Terraform state.

The actual signing keys are fetched at runtime from each pool's JWKS URI.

## Customer pool — `sparkpilot-customer-pool`

Used for tenant admin and end-user auth. Created and managed by Terraform
in `infra/terraform/control-plane/cognito_customer.tf`.

| Field | Value |
|---|---|
| Pool ID | `us-east-1_zwItYYA5g` |
| Pool ARN | `arn:aws:cognito-idp:us-east-1:787587782916:userpool/us-east-1_zwItYYA5g` |
| App client ID (PKCE / SPA) | `6vs8uei47gdc8r367ov95ca12h` |
| App client name | `sparkpilot-customer-spa-client` |
| Issuer (`iss`) | `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_zwItYYA5g` |
| JWKS URI | `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_zwItYYA5g/.well-known/jwks.json` |
| Hosted UI domain prefix | `sparkpilot-customers` |
| Hosted UI authorize URL | `https://sparkpilot-customers.auth.us-east-1.amazoncognito.com/oauth2/authorize` |
| Callback URL | `https://app.sparkpilot.cloud/auth/callback` |
| Logout URL | `https://app.sparkpilot.cloud/` |

These values map to GitHub-secret variables on the staging environment as:

```
STAGING_CUSTOMER_OIDC_ISSUER     = https://cognito-idp.us-east-1.amazonaws.com/us-east-1_zwItYYA5g
STAGING_CUSTOMER_OIDC_CLIENT_ID  = 6vs8uei47gdc8r367ov95ca12h
STAGING_CUSTOMER_OIDC_AUDIENCE   = 6vs8uei47gdc8r367ov95ca12h
STAGING_CUSTOMER_OIDC_JWKS_URI   = https://cognito-idp.us-east-1.amazonaws.com/us-east-1_zwItYYA5g/.well-known/jwks.json
STAGING_COGNITO_HOSTED_UI_URL    = https://sparkpilot-customers.auth.us-east-1.amazoncognito.com/oauth2/authorize
STAGING_UI_APP_BASE_URL          = https://app.sparkpilot.cloud
```

The deployed UI default login must use the same customer client:

```
NEXT_PUBLIC_OIDC_ISSUER       = https://cognito-idp.us-east-1.amazonaws.com/us-east-1_zwItYYA5g
NEXT_PUBLIC_OIDC_CLIENT_ID    = 6vs8uei47gdc8r367ov95ca12h
NEXT_PUBLIC_OIDC_AUDIENCE     = 6vs8uei47gdc8r367ov95ca12h
NEXT_PUBLIC_OIDC_REDIRECT_URI = https://app.sparkpilot.cloud/auth/callback
```

## Internal-admin pool — `SparkPilotDevUsers`

Used for SparkPilot internal admin auth (founder + future hires). The pool
itself is **unmanaged** — created outside Terraform before this module
existed. Only the dedicated `sparkpilot-internal-admin-client` app client is
Terraform-managed (via `cognito_customer.tf`, by literal pool-ID reference).

The two legacy app clients (`sparkpilot-dev-client`, `sparkpilot-staging-public-client`)
are intentionally untouched and slated for a post-launch cleanup PR.

| Field | Value |
|---|---|
| Pool ID | `us-east-1_m6veGu9gU` |
| Pool ARN | `arn:aws:cognito-idp:us-east-1:787587782916:userpool/us-east-1_m6veGu9gU` |
| Pool name | `SparkPilotDevUsers` |
| App client ID (internal admin) | `dgtn1v094t1iurbojmltl7hth` |
| App client name (internal admin) | `sparkpilot-internal-admin-client` |
| Issuer (`iss`) | `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_m6veGu9gU` |
| JWKS URI | `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_m6veGu9gU/.well-known/jwks.json` |
| Hosted UI domain prefix | `sparkpilot-auth` (legacy, unmanaged) |
| Hosted UI authorize URL | `https://sparkpilot-auth.auth.us-east-1.amazoncognito.com/oauth2/authorize` |
| Callback URL | `https://app.sparkpilot.cloud/auth/callback` |
| Logout URL | `https://app.sparkpilot.cloud/` |

These values map to GitHub-secret variables on the staging environment as:

```
STAGING_INTERNAL_OIDC_ISSUER    = https://cognito-idp.us-east-1.amazonaws.com/us-east-1_m6veGu9gU
STAGING_INTERNAL_OIDC_CLIENT_ID = dgtn1v094t1iurbojmltl7hth
STAGING_INTERNAL_OIDC_AUDIENCE  = dgtn1v094t1iurbojmltl7hth
STAGING_INTERNAL_OIDC_JWKS_URI  = https://cognito-idp.us-east-1.amazonaws.com/us-east-1_m6veGu9gU/.well-known/jwks.json
```

The deployed UI internal-admin login must use the same internal client:

```
NEXT_PUBLIC_INTERNAL_OIDC_ISSUER       = https://cognito-idp.us-east-1.amazonaws.com/us-east-1_m6veGu9gU
NEXT_PUBLIC_INTERNAL_OIDC_CLIENT_ID    = dgtn1v094t1iurbojmltl7hth
NEXT_PUBLIC_INTERNAL_OIDC_AUDIENCE     = dgtn1v094t1iurbojmltl7hth
NEXT_PUBLIC_INTERNAL_OIDC_REDIRECT_URI = https://app.sparkpilot.cloud/auth/callback
```

Invite acceptance is UI-mediated: `/v1/invite/accept` validates and consumes
the magic-link token, then redirects to `/login?pool=customer&invite_state=...`.
The UI completes Cognito PKCE login and calls `/v1/invite/callback` through the
API proxy to bind the authenticated customer-pool identity to the invited user.

## Backend / state

Both pools live in AWS account `787587782916`, region `us-east-1`. The
customer pool's Terraform state is in
`s3://sparkpilot-tfstate-787587782916/sparkpilot/control-plane/staging.tfstate`,
locked via DynamoDB table `sparkpilot-tfstate-lock`.
