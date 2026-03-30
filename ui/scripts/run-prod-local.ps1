param(
  [Parameter(Mandatory = $true)][string]$ApiBase,
  [Parameter(Mandatory = $true)][string]$OidcIssuer,
  [Parameter(Mandatory = $true)][string]$OidcClientId,
  [Parameter(Mandatory = $true)][string]$OidcRedirectUri,
  [string]$OidcAudience = "sparkpilot-api",
  [int]$Port = 3000
)

$env:SPARKPILOT_API = $ApiBase
$env:SPARKPILOT_UI_ENFORCE_AUTH = "true"
$env:NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE = "false"
$env:NEXT_PUBLIC_OIDC_ISSUER = $OidcIssuer
$env:NEXT_PUBLIC_OIDC_CLIENT_ID = $OidcClientId
$env:NEXT_PUBLIC_OIDC_REDIRECT_URI = $OidcRedirectUri
$env:NEXT_PUBLIC_OIDC_AUDIENCE = $OidcAudience

npm run verify:prod-env
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

npm run build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

npm run start -- --hostname 0.0.0.0 --port $Port
