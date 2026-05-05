param(
  [Parameter(Mandatory = $true)][string]$ApiBase,
  [Parameter(Mandatory = $true)][string]$OidcIssuer,
  [Parameter(Mandatory = $true)][string]$OidcClientId,
  [Parameter(Mandatory = $true)][string]$OidcRedirectUri,
  [Parameter(Mandatory = $true)][string]$InternalOidcIssuer,
  [Parameter(Mandatory = $true)][string]$InternalOidcClientId,
  [string]$InternalOidcRedirectUri = "",
  [string]$OidcAudience = "sparkpilot-api",
  [string]$InternalOidcAudience = "",
  [int]$Port = 3000
)

$env:SPARKPILOT_API = $ApiBase
$env:SPARKPILOT_UI_ENFORCE_AUTH = "true"
$env:NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE = "false"
$env:NEXT_PUBLIC_OIDC_ISSUER = $OidcIssuer
$env:NEXT_PUBLIC_OIDC_CLIENT_ID = $OidcClientId
$env:NEXT_PUBLIC_OIDC_REDIRECT_URI = $OidcRedirectUri
$env:NEXT_PUBLIC_OIDC_AUDIENCE = $OidcAudience
$env:NEXT_PUBLIC_INTERNAL_OIDC_ISSUER = $InternalOidcIssuer
$env:NEXT_PUBLIC_INTERNAL_OIDC_CLIENT_ID = $InternalOidcClientId
$env:NEXT_PUBLIC_INTERNAL_OIDC_REDIRECT_URI = if ($InternalOidcRedirectUri) { $InternalOidcRedirectUri } else { $OidcRedirectUri }
$env:NEXT_PUBLIC_INTERNAL_OIDC_AUDIENCE = if ($InternalOidcAudience) { $InternalOidcAudience } else { $InternalOidcClientId }

npm run verify:prod-env
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

npm run build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:PORT = "$Port"
$env:HOSTNAME = "0.0.0.0"
node .next/standalone/server.js
