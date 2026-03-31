#!/usr/bin/env bash
# deploy_preflight.sh — validate required deploy secrets before AWS auth.
#
# Environment variables expected (all injected from GHA secrets/vars):
#   DEPLOY_ENV          — lowercase env name: dev | staging | prod
#   ROLE_ARN            — AWS deploy role ARN (AWS_{ENV}_DEPLOY_ROLE_ARN)
#   TF_STATE_BUCKET     — Terraform state S3 bucket
#   TF_LOCK_TABLE       — Terraform DynamoDB lock table
#   VPC_ID              — VPC ID for the environment
#   PRIVATE_SUBNET_IDS_JSON — JSON array of private subnet IDs
#   DB_PASSWORD         — RDS database password
#   OIDC_ISSUER         — OIDC issuer URL
#   OIDC_AUDIENCE       — OIDC audience
#   OIDC_JWKS_URI       — OIDC JWKS URI
#   BOOTSTRAP_SECRET    — API bootstrap secret
#
# Outputs (via GITHUB_OUTPUT):
#   skip=true   — role ARN not set; environment not configured; job should skip remaining steps
#   skip=false  — all required secrets present; proceed with deploy
#
# Exit codes:
#   0  — skip=true (not configured) or skip=false (all good)
#   1  — role ARN is set but one or more other required secrets are missing (actionable error)

set -euo pipefail

ENV_UPPER="${DEPLOY_ENV^^}"

# ── Gate 1: Is this environment configured at all? ──────────────────────────
if [ -z "${ROLE_ARN:-}" ]; then
  echo "INFO: ${DEPLOY_ENV} deploy skipped — AWS_${ENV_UPPER}_DEPLOY_ROLE_ARN is not set."
  echo "      Configure this secret in the '${DEPLOY_ENV}' GitHub environment to enable ${DEPLOY_ENV} deploys."
  echo "skip=true" >> "${GITHUB_OUTPUT}"
  exit 0
fi

# ── Gate 2: Role ARN is present — validate all other required secrets ────────
declare -a MISSING=()

[ -z "${TF_STATE_BUCKET:-}" ]         && MISSING+=("${ENV_UPPER}_TF_STATE_BUCKET")
[ -z "${TF_LOCK_TABLE:-}" ]           && MISSING+=("${ENV_UPPER}_TF_LOCK_TABLE")
[ -z "${VPC_ID:-}" ]                  && MISSING+=("${ENV_UPPER}_VPC_ID")
[ -z "${PRIVATE_SUBNET_IDS_JSON:-}" ] && MISSING+=("${ENV_UPPER}_PRIVATE_SUBNET_IDS_JSON")
[ -z "${DB_PASSWORD:-}" ]             && MISSING+=("${ENV_UPPER}_DB_PASSWORD")
[ -z "${OIDC_ISSUER:-}" ]             && MISSING+=("${ENV_UPPER}_OIDC_ISSUER")
[ -z "${OIDC_AUDIENCE:-}" ]           && MISSING+=("${ENV_UPPER}_OIDC_AUDIENCE")
[ -z "${OIDC_JWKS_URI:-}" ]           && MISSING+=("${ENV_UPPER}_OIDC_JWKS_URI")
[ -z "${BOOTSTRAP_SECRET:-}" ]        && MISSING+=("${ENV_UPPER}_BOOTSTRAP_SECRET")

if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "::error::${DEPLOY_ENV} deploy preflight FAILED — role ARN is set but ${#MISSING[@]} required secret(s) are missing:"
  for key in "${MISSING[@]}"; do
    echo "  missing: ${key}"
  done
  echo ""
  echo "Add the above secrets to the '${DEPLOY_ENV}' GitHub environment and re-run."
  exit 1
fi

echo "skip=false" >> "${GITHUB_OUTPUT}"
echo "INFO: ${DEPLOY_ENV} deploy preflight passed — all required secrets present."
