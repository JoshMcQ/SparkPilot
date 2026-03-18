param(
  [Parameter(Mandatory = $true)]
  [string]$EmrExecutionRoleArn,
  [string]$AwsProfile = "default",
  [string]$AwsRegion = "us-east-1",
  [string]$BootstrapSecret = "sparkpilot-local-bootstrap-secret",
  [string]$UiSubject = "user:demo-admin",
  [switch]$NoBuild,
  [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RequiredCommand([string]$name) {
  $command = Get-Command $name -ErrorAction SilentlyContinue
  if (-not $command) {
    throw "Required command '$name' was not found in PATH."
  }
}

function Get-AwsConfigValue([string]$key, [string]$profile) {
  $homeDir = [Environment]::GetFolderPath("UserProfile")
  if ([string]::IsNullOrWhiteSpace($homeDir)) {
    return ""
  }
  $credentialsPath = Join-Path $homeDir ".aws\credentials"
  $configPath = Join-Path $homeDir ".aws\config"

  $profileName = $profile.Trim()
  if ([string]::IsNullOrWhiteSpace($profileName)) {
    $profileName = "default"
  }
  $configProfileName = if ($profileName -eq "default") { "default" } else { "profile $profileName" }

  function Get-IniValue([string]$path, [string[]]$sections, [string]$targetKey) {
    if (-not (Test-Path -LiteralPath $path)) {
      return ""
    }
    $currentSection = ""
    $lowerTarget = $targetKey.ToLowerInvariant()
    foreach ($rawLine in Get-Content -LiteralPath $path) {
      $line = $rawLine.Trim()
      if (-not $line -or $line.StartsWith("#") -or $line.StartsWith(";")) {
        continue
      }
      if ($line -match "^\[(.+)\]$") {
        $currentSection = $Matches[1].Trim()
        continue
      }
      if (-not ($sections -contains $currentSection)) {
        continue
      }
      if ($line -match "^(?<k>[^=]+?)\s*=\s*(?<v>.*)$") {
        $candidateKey = $Matches["k"].Trim().ToLowerInvariant()
        if ($candidateKey -eq $lowerTarget) {
          return $Matches["v"].Trim()
        }
      }
    }
    return ""
  }

  $value = Get-IniValue $credentialsPath @($profileName) $key
  if (-not [string]::IsNullOrWhiteSpace($value)) {
    return $value
  }
  $value = Get-IniValue $configPath @($configProfileName, $profileName) $key
  if (-not [string]::IsNullOrWhiteSpace($value)) {
    return $value
  }
  return ""
}

function Wait-HttpOk([string]$url, [int]$timeoutSeconds) {
  $deadline = (Get-Date).AddSeconds($timeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -Uri $url -Method Get -UseBasicParsing -TimeoutSec 5
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
        return
      }
    } catch {
      Start-Sleep -Seconds 2
      continue
    }
    Start-Sleep -Seconds 2
  }
  throw "Timed out waiting for $url"
}

Get-RequiredCommand "docker"

if ($BootstrapSecret.Length -lt 16) {
  throw "BootstrapSecret must be at least 16 characters."
}

$roleArn = ($EmrExecutionRoleArn -replace "[^\x20-\x7E]", "" -replace "\s+", "").Trim()
if ([string]::IsNullOrWhiteSpace($roleArn)) {
  throw "EmrExecutionRoleArn is required."
}
if ($roleArn.Contains("<") -or $roleArn.Contains(">")) {
  throw "EmrExecutionRoleArn contains placeholder markers (< >). Replace with a real ARN, e.g. arn:aws:iam::123456789012:role/SparkPilotEmrExecutionRole."
}
if ($roleArn -notmatch '^arn:aws[a-zA-Z-]*:iam::\d{12}:role\/.+$') {
  throw "EmrExecutionRoleArn is invalid. Received '$roleArn'. Expected format: arn:aws:iam::<12-digit-account-id>:role/<role-name>."
}

$accessKeyId = $env:AWS_ACCESS_KEY_ID
$secretAccessKey = $env:AWS_SECRET_ACCESS_KEY
$sessionToken = $env:AWS_SESSION_TOKEN

if ([string]::IsNullOrWhiteSpace($accessKeyId) -or [string]::IsNullOrWhiteSpace($secretAccessKey)) {
  $accessKeyId = (Get-AwsConfigValue "aws_access_key_id" $AwsProfile).Trim()
  $secretAccessKey = (Get-AwsConfigValue "aws_secret_access_key" $AwsProfile).Trim()
  $sessionToken = (Get-AwsConfigValue "aws_session_token" $AwsProfile).Trim()
}

if ([string]::IsNullOrWhiteSpace($accessKeyId) -or [string]::IsNullOrWhiteSpace($secretAccessKey)) {
  throw "AWS credentials not found. Set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, or configure profile '$AwsProfile' in ~/.aws/credentials."
}

$env:AWS_ACCESS_KEY_ID = $accessKeyId
$env:AWS_SECRET_ACCESS_KEY = $secretAccessKey
if ([string]::IsNullOrWhiteSpace($sessionToken)) {
  Remove-Item Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
} else {
  $env:AWS_SESSION_TOKEN = $sessionToken
}
$env:AWS_REGION = $AwsRegion
$env:AWS_DEFAULT_REGION = $AwsRegion

$env:SPARKPILOT_DRY_RUN_MODE = "false"
$env:SPARKPILOT_ENABLE_FULL_BYOC_MODE = "false"
$env:SPARKPILOT_EMR_EXECUTION_ROLE_ARN = $roleArn
$env:SPARKPILOT_BOOTSTRAP_SECRET = $BootstrapSecret

$composeArgs = @("compose", "up", "-d", "--remove-orphans")
if (-not $NoBuild) {
  $composeArgs += "--build"
}

Write-Host "Starting SparkPilot stack in live AWS mode..."
& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
  Write-Host "docker compose up failed. Recent sparkpilot-api logs:"
  & docker compose logs --no-color --tail 120 sparkpilot-api
  throw "docker compose up failed."
}

Write-Host "Waiting for API/OIDC/UI readiness..."
Wait-HttpOk "http://localhost:8080/healthz" 180
Wait-HttpOk "http://localhost:8000/healthz" 180
Wait-HttpOk "http://localhost:3000/" 180

$basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("sparkpilot-cli:sparkpilot-cli-secret"))
$tokenResponse = Invoke-RestMethod -Method Post -Uri "http://localhost:8080/oauth/token" -Headers @{ Authorization = "Basic $basic" } -Body @{
  grant_type = "client_credentials"
  audience = "sparkpilot-api"
  subject = $UiSubject
}
$accessToken = [string]$tokenResponse.access_token
if ([string]::IsNullOrWhiteSpace($accessToken)) {
  throw "OIDC token mint failed: empty access token."
}
$accessToken = $accessToken.Trim()

$bootstrapHeaders = @{
  Authorization = "Bearer $accessToken"
  "X-Bootstrap-Secret" = $BootstrapSecret
  "Content-Type" = "application/json"
}
$bootstrapBody = @{
  actor = $UiSubject
  role = "admin"
  active = $true
} | ConvertTo-Json -Compress

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/v1/user-identities" -Headers $bootstrapHeaders -Body $bootstrapBody | Out-Null
Invoke-RestMethod -Uri "http://localhost:3000/api/sparkpilot/v1/environments" -Headers @{ Authorization = "Bearer $accessToken" } | Out-Null

try {
  $accessToken | Set-Clipboard
  Write-Host "Bearer token copied to clipboard."
} catch {
  Write-Host "Could not copy token to clipboard. You can still copy from output below."
}

Write-Host ""
Write-Host "SparkPilot live mode is up."
Write-Host "UI: http://localhost:3000"
Write-Host "Subject: $UiSubject"
Write-Host "Token (if clipboard failed):"
Write-Host $accessToken
Write-Host ""
Write-Host "In the UI, paste token and click Apply once."
Write-Host "To stop stack: docker compose down"

if (-not $NoBrowser) {
  Start-Process "http://localhost:3000" | Out-Null
}
