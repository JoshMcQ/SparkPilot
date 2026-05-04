#!/usr/bin/env bash
# deploy_preflight.sh - validate deploy gates/secrets before AWS auth.
#
# Environment variables expected (all injected from GHA secrets/vars):
#   DEPLOY_ENV              - lowercase env name: dev | staging | prod
#   DEPLOY_ENABLED          - optional gate. true enables deploy; false skips job.
#   ROLE_ARN                - AWS deploy role ARN (AWS_{ENV}_DEPLOY_ROLE_ARN)
#   TF_STATE_BUCKET         - Terraform state S3 bucket
#   TF_LOCK_TABLE           - Terraform DynamoDB lock table
#   VPC_ID                  - VPC ID for the environment
#   PRIVATE_SUBNET_IDS_JSON - JSON array of private subnet IDs
#   DB_PASSWORD             - RDS database password
#   OIDC_ISSUER             - legacy/customer OIDC issuer URL
#   OIDC_AUDIENCE           - legacy/customer OIDC audience
#   OIDC_JWKS_URI           - legacy/customer OIDC JWKS URI
#   CUSTOMER_OIDC_ISSUER    - optional customer OIDC issuer URL
#   CUSTOMER_OIDC_AUDIENCE  - optional customer OIDC audience
#   CUSTOMER_OIDC_JWKS_URI  - optional customer OIDC JWKS URI
#   INTERNAL_OIDC_ISSUER    - internal OIDC issuer URL
#   INTERNAL_OIDC_AUDIENCE  - internal OIDC audience
#   INTERNAL_OIDC_JWKS_URI  - internal OIDC JWKS URI
#   COGNITO_HOSTED_UI_URL   - Cognito Hosted UI authorize URL for invite accept redirects
#   BOOTSTRAP_SECRET        - API bootstrap secret
#   EMR_EXECUTION_ROLE_ARN  - EMR execution role ARN
#   RESEND_API_KEY          - Resend API key (raw); deploy script writes to Terraform-managed Secrets Manager secret
#   INVITE_EMAIL_FROM       - sender address for invite emails
#   UI_APP_BASE_URL         - public app URL used for OIDC callback build args when UI is deployed
#
# Outputs (via GITHUB_OUTPUT):
#   skip=true   - deploy disabled, role missing, or environment not configured
#   skip=false  - all required gates/secrets present; proceed with deploy
#
# Exit codes:
#   0 - skip=true (not configured/disabled) or skip=false (all good)
#   1 - deploy is enabled and one or more required secrets are missing

set -euo pipefail

normalize_bool() {
  local raw="${1:-}"
  raw="$(echo "${raw}" | tr '[:upper:]' '[:lower:]' | xargs)"
  case "${raw}" in
    true|1|yes|y|on) echo "true" ;;
    false|0|no|n|off|"") echo "false" ;;
    *)
      echo "::error::Invalid boolean value '${1}' for DEPLOY_ENABLED. Use true/false." >&2
      exit 1
      ;;
  esac
}

ENV_UPPER="${DEPLOY_ENV^^}"
DEPLOY_ENABLED_NORMALIZED="$(normalize_bool "${DEPLOY_ENABLED:-true}")"

# Gate 0: explicit deploy lane switch (cost control / freeze switch)
if [[ "${DEPLOY_ENABLED_NORMALIZED}" != "true" ]]; then
  echo "INFO: ${DEPLOY_ENV} deploy skipped - DEPLOY_ENABLED is false."
  echo "      Set ${ENV_UPPER}_DEPLOY_ENABLED=true (GitHub environment variable) to re-enable this lane."
  echo "skip=true" >> "${GITHUB_OUTPUT}"
  exit 0
fi

# Gate 1: Is this environment configured at all?
if [ -z "${ROLE_ARN:-}" ]; then
  echo "INFO: ${DEPLOY_ENV} deploy skipped - AWS_${ENV_UPPER}_DEPLOY_ROLE_ARN is not set."
  echo "      Configure this secret in the '${DEPLOY_ENV}' GitHub environment to enable ${DEPLOY_ENV} deploys."
  echo "skip=true" >> "${GITHUB_OUTPUT}"
  exit 0
fi

# Gate 2: Role ARN is present - validate all other required secrets
declare -a MISSING=()

[ -z "${TF_STATE_BUCKET:-}" ]         && MISSING+=("${ENV_UPPER}_TF_STATE_BUCKET")
[ -z "${TF_LOCK_TABLE:-}" ]           && MISSING+=("${ENV_UPPER}_TF_LOCK_TABLE")
[ -z "${VPC_ID:-}" ]                  && MISSING+=("${ENV_UPPER}_VPC_ID")
if [ -z "${PRIVATE_SUBNET_IDS_JSON:-}" ]; then
  MISSING+=("${ENV_UPPER}_PRIVATE_SUBNET_IDS_JSON")
elif ! echo "${PRIVATE_SUBNET_IDS_JSON}" | jq -e 'type == "array" and length >= 2 and all(.[]; type == "string" and test("^subnet-[a-z0-9]+$"))' >/dev/null 2>&1; then
  echo "::error::${ENV_UPPER}_PRIVATE_SUBNET_IDS_JSON must be a JSON array with at least two subnet IDs (e.g. [\"subnet-abc\",\"subnet-def\"])."
  exit 1
fi
[ -z "${DB_PASSWORD:-}" ]             && MISSING+=("${ENV_UPPER}_DB_PASSWORD")
[ -z "${OIDC_ISSUER:-}" ]             && MISSING+=("${ENV_UPPER}_OIDC_ISSUER")
[ -z "${OIDC_AUDIENCE:-}" ]           && MISSING+=("${ENV_UPPER}_OIDC_AUDIENCE")
[ -z "${OIDC_JWKS_URI:-}" ]           && MISSING+=("${ENV_UPPER}_OIDC_JWKS_URI")
[ -z "${INTERNAL_OIDC_ISSUER:-}" ]    && MISSING+=("${ENV_UPPER}_INTERNAL_OIDC_ISSUER")
[ -z "${INTERNAL_OIDC_AUDIENCE:-}" ]  && MISSING+=("${ENV_UPPER}_INTERNAL_OIDC_AUDIENCE")
[ -z "${INTERNAL_OIDC_JWKS_URI:-}" ]  && MISSING+=("${ENV_UPPER}_INTERNAL_OIDC_JWKS_URI")
[ -z "${BOOTSTRAP_SECRET:-}" ]        && MISSING+=("${ENV_UPPER}_BOOTSTRAP_SECRET")
[ -z "${EMR_EXECUTION_ROLE_ARN:-}" ]  && MISSING+=("${ENV_UPPER}_EMR_EXECUTION_ROLE_ARN")

ui_desired_count="${TF_VAR_ui_desired_count:-0}"
if [[ "${ui_desired_count}" != "0" && -z "${UI_APP_BASE_URL:-}" ]]; then
  MISSING+=("${ENV_UPPER}_UI_APP_BASE_URL")
fi

customer_oidc_any=false
[ -n "${CUSTOMER_OIDC_ISSUER:-}" ] && customer_oidc_any=true
[ -n "${CUSTOMER_OIDC_AUDIENCE:-}" ] && customer_oidc_any=true
[ -n "${CUSTOMER_OIDC_JWKS_URI:-}" ] && customer_oidc_any=true
if [[ "${customer_oidc_any}" == "true" ]]; then
  [ -z "${CUSTOMER_OIDC_ISSUER:-}" ] && MISSING+=("${ENV_UPPER}_CUSTOMER_OIDC_ISSUER")
  [ -z "${CUSTOMER_OIDC_AUDIENCE:-}" ] && MISSING+=("${ENV_UPPER}_CUSTOMER_OIDC_AUDIENCE")
  [ -z "${CUSTOMER_OIDC_JWKS_URI:-}" ] && MISSING+=("${ENV_UPPER}_CUSTOMER_OIDC_JWKS_URI")
fi

if [[ "${DEPLOY_ENV}" != "dev" ]]; then
  [ -z "${COGNITO_HOSTED_UI_URL:-}" ] && MISSING+=("${ENV_UPPER}_COGNITO_HOSTED_UI_URL")
  [ -z "${RESEND_API_KEY:-}" ]        && MISSING+=("${ENV_UPPER}_RESEND_API_KEY")
  [ -z "${INVITE_EMAIL_FROM:-}" ]     && MISSING+=("${ENV_UPPER}_INVITE_EMAIL_FROM")
fi

if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "::error::${DEPLOY_ENV} deploy preflight FAILED - role ARN is set but ${#MISSING[@]} required secret(s) are missing:"
  for key in "${MISSING[@]}"; do
    echo "  missing: ${key}"
  done
  echo ""
  echo "Add the above secrets to the '${DEPLOY_ENV}' GitHub environment and re-run."
  exit 1
fi

echo "skip=false" >> "${GITHUB_OUTPUT}"
echo "INFO: ${DEPLOY_ENV} deploy preflight passed - all required secrets present."
