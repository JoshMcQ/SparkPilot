#!/usr/bin/env pwsh
# Validates all full-BYOC Terraform modules: fmt, init, validate.
# Usage: ./scripts/terraform/validate_full_byoc.ps1
# Exit code 0 = all checks passed, 1 = any check failed.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$byocRoot = Join-Path $root "infra/terraform/full-byoc"
$dirs = @(
    $byocRoot,
    (Join-Path $byocRoot "network"),
    (Join-Path $byocRoot "eks"),
    (Join-Path $byocRoot "emr")
)

$terraformCmd = $env:TERRAFORM_BIN
if (-not $terraformCmd) {
    try {
        $terraformCmd = (Get-Command terraform -ErrorAction Stop).Source
    } catch {
        $localTerraform = Join-Path $root "tools/terraform/1.7.5/terraform.exe"
        if (Test-Path $localTerraform) {
            $terraformCmd = $localTerraform
        } else {
            throw "Terraform binary not found. Set TERRAFORM_BIN or install terraform in PATH."
        }
    }
}

function Invoke-Terraform {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )
    & $terraformCmd @Args
}

$failed = $false

Write-Host "=== Terraform fmt check ===" -ForegroundColor Cyan
Invoke-Terraform @("fmt", "-check", "-recursive", $byocRoot)
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: fmt check failed" -ForegroundColor Red
    $failed = $true
} else {
    Write-Host "PASS: fmt check" -ForegroundColor Green
}

foreach ($dir in $dirs) {
    Write-Host ""
    Write-Host "=== $dir ===" -ForegroundColor Cyan

    Push-Location $dir
    try {
        Invoke-Terraform @("init", "-backend=false", "-input=false", "-no-color")
        if ($LASTEXITCODE -ne 0) {
            Write-Host "FAIL: init in $dir" -ForegroundColor Red
            $failed = $true
        } else {
            Invoke-Terraform @("validate", "-no-color")
            if ($LASTEXITCODE -ne 0) {
                Write-Host "FAIL: validate in $dir" -ForegroundColor Red
                $failed = $true
            } else {
                Write-Host "PASS: $dir" -ForegroundColor Green
            }
        }
    } finally {
        Pop-Location
    }
}

Write-Host ""
if ($failed) {
    Write-Host "=== VALIDATION FAILED ===" -ForegroundColor Red
    exit 1
} else {
    Write-Host "=== VALIDATION PASSED ===" -ForegroundColor Green
    exit 0
}
