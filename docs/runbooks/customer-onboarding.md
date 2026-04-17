# Customer Onboarding Runbook (Direct Order Form, Tenant #1)

## Placeholders
- `{{AWS_REGION}}`
- `{{COGNITO_USER_POOL_ID}}`
- `{{COGNITO_DOMAIN_PREFIX}}`
- `{{SPARKPILOT_APP_URL}}`
- `{{SPARKPILOT_API_BASE_URL}}`
- `{{SPARKPILOT_UI_CLIENT_ID}}`
- `{{SPARKPILOT_BOOTSTRAP_SECRET}}`
- `{{CUSTOMER_LEGAL_NAME}}`
- `{{CUSTOMER_ADMIN_EMAIL}}`
- `{{CUSTOMER_IDP_NAME}}`
- `{{CUSTOMER_SAML_METADATA_URL}}`
- `{{CUSTOMER_OIDC_ISSUER}}`
- `{{CUSTOMER_OIDC_CLIENT_ID}}`
- `{{CUSTOMER_OIDC_CLIENT_SECRET}}`
- `{{CUSTOMER_DOMAIN_HINT}}`

## Scope
- This runbook is for direct Order Form + invoice onboarding (no Marketplace).
- This is for tenant #1 bootstrap on a shared Cognito user pool.
- Cognito is the only SparkPilot front-door IdP.

## 1. Confirm Commercial Readiness
1. Verify signed Order Form is in the deal record for `{{CUSTOMER_LEGAL_NAME}}`.
2. Verify wire/ACH settlement is confirmed in finance tooling.
3. Open an internal onboarding ticket with owner + SLA.

TODO: build `onboarding-ticket-template` generator.
Spec: one command creates a prefilled ticket with customer, contract date, and required technical checklist.

## 2. Prepare Shared Cognito Federation
1. Confirm the shared pool exists and is active.

```bash
aws cognito-idp describe-user-pool \
  --region {{AWS_REGION}} \
  --user-pool-id {{COGNITO_USER_POOL_ID}}
```

```powershell
aws cognito-idp describe-user-pool `
  --region {{AWS_REGION}} `
  --user-pool-id {{COGNITO_USER_POOL_ID}}
```

2. Add customer external IdP to shared pool (choose one path):

Path A: SAML metadata URL

```bash
aws cognito-idp create-identity-provider \
  --region {{AWS_REGION}} \
  --user-pool-id {{COGNITO_USER_POOL_ID}} \
  --provider-name {{CUSTOMER_IDP_NAME}} \
  --provider-type SAML \
  --provider-details MetadataURL={{CUSTOMER_SAML_METADATA_URL}} \
  --attribute-mapping email="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",username="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"
```

```powershell
aws cognito-idp create-identity-provider `
  --region {{AWS_REGION}} `
  --user-pool-id {{COGNITO_USER_POOL_ID}} `
  --provider-name {{CUSTOMER_IDP_NAME}} `
  --provider-type SAML `
  --provider-details MetadataURL={{CUSTOMER_SAML_METADATA_URL}} `
  --attribute-mapping email="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",username="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"
```

Path B: OIDC federation

```bash
aws cognito-idp create-identity-provider \
  --region {{AWS_REGION}} \
  --user-pool-id {{COGNITO_USER_POOL_ID}} \
  --provider-name {{CUSTOMER_IDP_NAME}} \
  --provider-type OIDC \
  --provider-details oidc_issuer={{CUSTOMER_OIDC_ISSUER}},client_id={{CUSTOMER_OIDC_CLIENT_ID}},client_secret={{CUSTOMER_OIDC_CLIENT_SECRET}},authorize_scopes="openid email profile",attributes_request_method=GET \
  --attribute-mapping email=email,username=sub \
  --idp-identifiers {{CUSTOMER_DOMAIN_HINT}}
```

```powershell
aws cognito-idp create-identity-provider `
  --region {{AWS_REGION}} `
  --user-pool-id {{COGNITO_USER_POOL_ID}} `
  --provider-name {{CUSTOMER_IDP_NAME}} `
  --provider-type OIDC `
  --provider-details oidc_issuer={{CUSTOMER_OIDC_ISSUER}},client_id={{CUSTOMER_OIDC_CLIENT_ID}},client_secret={{CUSTOMER_OIDC_CLIENT_SECRET}},authorize_scopes="openid email profile",attributes_request_method=GET `
  --attribute-mapping email=email,username=sub `
  --idp-identifiers {{CUSTOMER_DOMAIN_HINT}}
```

3. Add `{{CUSTOMER_IDP_NAME}}` to the SparkPilot UI app client supported IdPs.
4. Validate callback URL exists: `{{SPARKPILOT_APP_URL}}/auth/callback`.

TODO: build `sparkpilot idp attach` automation.
Spec: one command upserts IdP and app-client supported providers idempotently.

## 3. Prepare First Admin Bootstrap Package
1. Confirm customer admin email: `{{CUSTOMER_ADMIN_EMAIL}}`.
2. Prepare onboarding package:
   - app URL: `{{SPARKPILOT_APP_URL}}`
   - login URL: `https://{{COGNITO_DOMAIN_PREFIX}}.auth.{{AWS_REGION}}.amazoncognito.com/login?client_id={{SPARKPILOT_UI_CLIENT_ID}}&response_type=code&scope=openid+profile+email&redirect_uri={{SPARKPILOT_APP_URL}}/auth/callback&identity_provider={{CUSTOMER_IDP_NAME}}`
   - support contact and office hours
3. Deliver bootstrap secret `{{SPARKPILOT_BOOTSTRAP_SECRET}}` in a separate channel.

Required delivery split:
- Channel A (email/ticket): app URL, login URL, process notes.
- Channel B (secure one-time secret channel): bootstrap secret only.

Do not send in the same channel as bootstrap secret:
- invoice email thread
- shared Slack channels
- plain text documents in shared drives

TODO: build one-time bootstrap secret delivery.
Spec: generate one-time retrieval link that expires in <= 15 minutes and logs access.

## 4. Customer Claims First Admin at `/access`
1. Customer signs in through Cognito hosted UI.
2. Customer opens `{{SPARKPILOT_APP_URL}}/access`.
3. Customer enters `{{SPARKPILOT_BOOTSTRAP_SECRET}}` in Claim First Admin flow.
4. Validate success by calling:

```bash
curl -sS \
  -H "Authorization: Bearer {{CUSTOMER_ACCESS_TOKEN}}" \
  {{SPARKPILOT_API_BASE_URL}}/v1/auth/me
```

```powershell
curl.exe -sS `
  -H "Authorization: Bearer {{CUSTOMER_ACCESS_TOKEN}}" `
  {{SPARKPILOT_API_BASE_URL}}/v1/auth/me
```

Expected: role is `admin`.

## 5. Provision Tenant #1 (Post-Admin Claim)
Current product behavior requires an authenticated admin before tenant creation.

1. Create tenant.

```bash
curl -sS -X POST \
  -H "Authorization: Bearer {{CUSTOMER_ACCESS_TOKEN}}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: onboarding-tenant-{{CUSTOMER_LEGAL_NAME}}" \
  {{SPARKPILOT_API_BASE_URL}}/v1/tenants \
  -d '{"name":"{{CUSTOMER_LEGAL_NAME}}"}'
```

```powershell
curl.exe -sS -X POST `
  -H "Authorization: Bearer {{CUSTOMER_ACCESS_TOKEN}}" `
  -H "Content-Type: application/json" `
  -H "Idempotency-Key: onboarding-tenant-{{CUSTOMER_LEGAL_NAME}}" `
  {{SPARKPILOT_API_BASE_URL}}/v1/tenants `
  -d '{"name":"{{CUSTOMER_LEGAL_NAME}}"}'
```

2. Create first team in `/access` (or API).
3. Create initial environment in `/access` onboarding flow.

TODO: build `tenant-bootstrap` API for first-tenant creation with explicit audit trail.
Spec: authenticated admin endpoint that atomically creates tenant + first team + baseline policies.

## 6. Customer Adds Additional Users
Current path:
1. Admin opens `{{SPARKPILOT_APP_URL}}/access`.
2. Admin creates `user-identities` for additional users manually.
3. Admin assigns tenant/team scopes.

Future path:
- SCIM provisioning from customer IdP.

TODO: build SCIM 2.0 `/Users` and `/Groups` support.
Spec: map SCIM users/groups to `user_identities` and team scopes with idempotent upsert semantics.

