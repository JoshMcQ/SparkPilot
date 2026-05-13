#!/usr/bin/env bash
set -euo pipefail

require_env() {
  local var_name="$1"
  if [[ -z "${!var_name:-}" ]]; then
    echo "::error::Missing required environment variable: ${var_name}" >&2
    exit 1
  fi
}

normalize_bool() {
  local raw
  raw="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]' | xargs)"
  case "${raw}" in
    true|1|yes|y)
      echo "true"
      ;;
    false|0|no|n|"")
      echo "false"
      ;;
    *)
      echo "::error::Invalid boolean value '${1}'. Expected true/false." >&2
      exit 1
      ;;
  esac
}

normalize_nullable_bool() {
  local raw
  raw="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]' | xargs)"
  if [[ -z "${raw}" ]]; then
    echo "null"
    return
  fi
  normalize_bool "${raw}"
}

require_env "SPARKPILOT_ENVIRONMENT"
require_env "AWS_REGION"
require_env "TF_STATE_BUCKET"
require_env "TF_STATE_KEY"
require_env "TF_LOCK_TABLE"
require_env "VPC_ID"
require_env "PRIVATE_SUBNET_IDS_JSON"
require_env "DB_PASSWORD"
require_env "API_IMAGE_URI"
require_env "WORKER_IMAGE_URI"
require_env "OIDC_ISSUER"
require_env "OIDC_AUDIENCE"
require_env "OIDC_JWKS_URI"
require_env "INTERNAL_OIDC_ISSUER"
require_env "INTERNAL_OIDC_AUDIENCE"
require_env "INTERNAL_OIDC_JWKS_URI"
require_env "BOOTSTRAP_SECRET"
require_env "EMR_EXECUTION_ROLE_ARN"

if ! command -v terraform >/dev/null 2>&1; then
  echo "::error::terraform is required but was not found in PATH." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "::error::jq is required but was not found in PATH." >&2
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "::error::aws CLI is required but was not found in PATH." >&2
  exit 1
fi

terraform_root="${TERRAFORM_DIR:-infra/terraform/control-plane}"
if [[ ! -d "${terraform_root}" ]]; then
  echo "::error::Terraform directory not found: ${terraform_root}" >&2
  exit 1
fi

private_subnets_json="${PRIVATE_SUBNET_IDS_JSON}"
public_subnets_json="${PUBLIC_SUBNET_IDS_JSON:-[]}"

if ! echo "${private_subnets_json}" | jq -e 'type == "array" and length >= 2 and all(.[]; type == "string" and test("^subnet-[a-z0-9]+$"))' >/dev/null; then
  echo "::error::PRIVATE_SUBNET_IDS_JSON must be a JSON array with at least two subnet IDs." >&2
  exit 1
fi

if ! echo "${public_subnets_json}" | jq -e 'type == "array" and (length == 0 or length >= 2) and all(.[]; type == "string" and test("^subnet-[a-z0-9]+$"))' >/dev/null; then
  echo "::error::PUBLIC_SUBNET_IDS_JSON must be [] or a JSON array with at least two subnet IDs." >&2
  exit 1
fi

dry_run_mode="$(normalize_bool "${DRY_RUN_MODE:-false}")"
enable_full_byoc_mode="$(normalize_bool "${ENABLE_FULL_BYOC_MODE:-false}")"
allow_unsafe_rds_configuration="$(normalize_bool "${ALLOW_UNSAFE_RDS_CONFIGURATION:-false}")"
enable_ecs_exec="$(normalize_bool "${ENABLE_ECS_EXEC:-false}")"
acm_certificate_arn="$(echo "${ACM_CERTIFICATE_ARN:-}" | xargs)"
cloudflare_proxied="$(normalize_bool "${CLOUDFLARE_PROXIED:-false}")"
cors_origins_raw="$(echo "${CORS_ORIGINS:-http://localhost:3000}" | xargs)"
ui_image_uri="$(echo "${UI_IMAGE_URI:-}" | xargs)"
ui_api_base_url="$(echo "${UI_API_BASE_URL:-}" | xargs)"
app_base_url="$(echo "${APP_BASE_URL:-${UI_APP_BASE_URL:-}}" | xargs)"
customer_oidc_issuer="$(echo "${CUSTOMER_OIDC_ISSUER:-}" | xargs)"
customer_oidc_audience="$(echo "${CUSTOMER_OIDC_AUDIENCE:-}" | xargs)"
customer_oidc_jwks_uri="$(echo "${CUSTOMER_OIDC_JWKS_URI:-}" | xargs)"
internal_oidc_issuer="$(echo "${INTERNAL_OIDC_ISSUER}" | xargs)"
internal_oidc_audience="$(echo "${INTERNAL_OIDC_AUDIENCE}" | xargs)"
internal_oidc_jwks_uri="$(echo "${INTERNAL_OIDC_JWKS_URI}" | xargs)"
cognito_hosted_ui_url="$(echo "${COGNITO_HOSTED_UI_URL:-}" | xargs)"
resend_api_key="${RESEND_API_KEY:-}"
invite_email_from="$(echo "${INVITE_EMAIL_FROM:-}" | xargs)"
invite_email_reply_to="$(echo "${INVITE_EMAIL_REPLY_TO:-}" | xargs)"
invite_email_timeout_seconds="$(echo "${INVITE_EMAIL_TIMEOUT_SECONDS:-10}" | xargs)"
contact_email_recipient="$(echo "${CONTACT_EMAIL_RECIPIENT:-}" | xargs)"
contact_submit_token="$(echo "${CONTACT_SUBMIT_TOKEN:-}" | xargs)"
project_name_for_contact_secret="$(echo "${TF_VAR_project_name:-sparkpilot}" | xargs)"
contact_submit_token_secret_name="$(echo "${CONTACT_SUBMIT_TOKEN_SECRET_NAME:-${project_name_for_contact_secret}-${SPARKPILOT_ENVIRONMENT}-contact-submit-token}" | xargs)"

if ! jq -en --argjson timeout "${invite_email_timeout_seconds}" '$timeout > 0' >/dev/null 2>&1; then
  echo "::error::INVITE_EMAIL_TIMEOUT_SECONDS must be a positive number." >&2
  exit 1
fi
if [[ -n "${contact_submit_token}" && "${#contact_submit_token}" -lt 32 ]]; then
  echo "::error::CONTACT_SUBMIT_TOKEN must be at least 32 characters when set." >&2
  exit 1
fi

customer_oidc_any=false
if [[ -n "${customer_oidc_issuer}" || -n "${customer_oidc_audience}" || -n "${customer_oidc_jwks_uri}" ]]; then
  customer_oidc_any=true
fi
if [[ "${customer_oidc_any}" == "true" ]]; then
  if [[ -z "${customer_oidc_issuer}" || -z "${customer_oidc_audience}" || -z "${customer_oidc_jwks_uri}" ]]; then
    echo "::error::Customer OIDC configuration is partial. Set CUSTOMER_OIDC_ISSUER, CUSTOMER_OIDC_AUDIENCE, and CUSTOMER_OIDC_JWKS_URI together, or leave all empty to use legacy OIDC_* aliases." >&2
    exit 1
  fi
fi

# Reject localhost CORS in non-dev environments: deploy would succeed but ECS tasks would
# fail at runtime when the API's validate_runtime_settings() rejects localhost origins.
_env_lower="$(echo "${SPARKPILOT_ENVIRONMENT}" | tr '[:upper:]' '[:lower:]' | xargs)"
if [[ "${_env_lower}" != "dev" && "${_env_lower}" != "development" && "${_env_lower}" != "local" && "${_env_lower}" != "test" ]]; then
  if [[ -z "${CORS_ORIGINS:-}" ]] || echo "${cors_origins_raw}" | tr ',' '\n' | grep -qiE '(localhost|127\.0\.0\.1|::1)'; then
    echo "::error::CORS_ORIGINS must be set to a non-localhost value for non-dev environment '${SPARKPILOT_ENVIRONMENT}'. Set the CORS_ORIGINS variable (e.g. https://app.sparkpilot.cloud) before deploying." >&2
    exit 1
  fi
  if [[ -z "${resend_api_key}" ]]; then
    echo "::error::RESEND_API_KEY must be set for non-dev invite email delivery." >&2
    exit 1
  fi
  if [[ -z "${cognito_hosted_ui_url}" ]]; then
    echo "::error::COGNITO_HOSTED_UI_URL must be set for non-dev invite email redirects." >&2
    exit 1
  fi
  if [[ -z "${app_base_url}" ]]; then
    echo "::error::APP_BASE_URL or UI_APP_BASE_URL must be set for non-dev invite login redirects." >&2
    exit 1
  fi
  if [[ -z "${invite_email_from}" ]]; then
    echo "::error::INVITE_EMAIL_FROM must be set for non-dev invite email delivery." >&2
    exit 1
  fi
  internal_admins_gate="$(echo "${INTERNAL_ADMINS:-}" | xargs)"
  if [[ -z "${internal_admins_gate}" ]]; then
    echo "::error::INTERNAL_ADMINS must be non-empty for non-dev so internal-admin API routes can authorize operators (comma-separated emails)." >&2
    exit 1
  fi
fi

# Convert comma-separated string to JSON array for Terraform
cors_origins_json="$(echo "${cors_origins_raw}" | tr ',' '\n' | awk 'NF' | jq -R . | jq -s .)"
rds_deletion_protection="$(normalize_nullable_bool "${RDS_DELETION_PROTECTION:-}")"
rds_skip_final_snapshot="$(normalize_nullable_bool "${RDS_SKIP_FINAL_SNAPSHOT:-}")"
cur_athena_database="$(echo "${CUR_ATHENA_DATABASE:-}" | xargs)"
cur_athena_table="$(echo "${CUR_ATHENA_TABLE:-}" | xargs)"
cur_athena_workgroup="$(echo "${CUR_ATHENA_WORKGROUP:-primary}" | xargs)"
cur_athena_output_location="$(echo "${CUR_ATHENA_OUTPUT_LOCATION:-}" | xargs)"
cur_run_id_column="$(echo "${CUR_RUN_ID_COLUMN:-resource_tags_user_sparkpilot_run_id}" | xargs)"
cur_cost_column="$(echo "${CUR_COST_COLUMN:-line_item_unblended_cost}" | xargs)"
cost_center_policy_json="${COST_CENTER_POLICY_JSON:-}"
assume_role_external_id="$(echo "${ASSUME_ROLE_EXTERNAL_ID:-}" | xargs)"
internal_admins="$(echo "${INTERNAL_ADMINS:-}" | xargs)"

if [[ -n "${cur_athena_database}" || -n "${cur_athena_table}" || -n "${cur_athena_output_location}" ]]; then
  if [[ -z "${cur_athena_database}" || -z "${cur_athena_table}" || -z "${cur_athena_output_location}" ]]; then
    echo "::error::CUR Athena configuration is partial. Set CUR_ATHENA_DATABASE, CUR_ATHENA_TABLE, and CUR_ATHENA_OUTPUT_LOCATION together." >&2
    exit 1
  fi
fi

# Terraform determines var-file format from extension; ensure JSON extension.
backend_file="$(mktemp "${TMPDIR:-/tmp}/sparkpilot-backend-XXXXXX.hcl")"
tfvars_file="$(mktemp "${TMPDIR:-/tmp}/sparkpilot-vars-XXXXXX.tfvars.json")"
plan_file="$(mktemp "${TMPDIR:-/tmp}/sparkpilot-plan-XXXXXX.tfplan")"
contact_secret_error_file="$(mktemp "${TMPDIR:-/tmp}/sparkpilot-contact-secret-XXXXXX.err")"
cleanup() {
  rm -f "${backend_file}" "${tfvars_file}" "${plan_file}" "${contact_secret_error_file}"
}
trap cleanup EXIT

cat > "${backend_file}" <<EOF
bucket         = "${TF_STATE_BUCKET}"
key            = "${TF_STATE_KEY}"
region         = "${AWS_REGION}"
dynamodb_table = "${TF_LOCK_TABLE}"
encrypt        = true
EOF

# bootstrap_secret is intentionally excluded from Terraform vars. It is written
# directly to Secrets Manager after apply so the value never enters TF state.
jq -n \
  --arg environment "${SPARKPILOT_ENVIRONMENT}" \
  --arg region "${AWS_REGION}" \
  --arg vpc_id "${VPC_ID}" \
  --argjson private_subnet_ids "${private_subnets_json}" \
  --argjson public_subnet_ids "${public_subnets_json}" \
  --arg db_password "${DB_PASSWORD}" \
  --arg api_image_uri "${API_IMAGE_URI}" \
  --arg worker_image_uri "${WORKER_IMAGE_URI}" \
  --arg oidc_issuer "${OIDC_ISSUER}" \
  --arg oidc_audience "${OIDC_AUDIENCE}" \
  --arg oidc_jwks_uri "${OIDC_JWKS_URI}" \
  --arg customer_oidc_issuer "${customer_oidc_issuer}" \
  --arg customer_oidc_audience "${customer_oidc_audience}" \
  --arg customer_oidc_jwks_uri "${customer_oidc_jwks_uri}" \
  --arg internal_oidc_issuer "${internal_oidc_issuer}" \
  --arg internal_oidc_audience "${internal_oidc_audience}" \
  --arg internal_oidc_jwks_uri "${internal_oidc_jwks_uri}" \
  --argjson dry_run_mode "${dry_run_mode}" \
  --argjson enable_full_byoc_mode "${enable_full_byoc_mode}" \
  --arg emr_execution_role_arn "${EMR_EXECUTION_ROLE_ARN}" \
  --arg assume_role_external_id "${assume_role_external_id}" \
  --argjson allow_unsafe_rds_configuration "${allow_unsafe_rds_configuration}" \
  --argjson rds_deletion_protection "${rds_deletion_protection}" \
  --argjson rds_skip_final_snapshot "${rds_skip_final_snapshot}" \
  --arg rds_final_snapshot_identifier "${RDS_FINAL_SNAPSHOT_IDENTIFIER:-}" \
  --arg cur_athena_database "${cur_athena_database}" \
  --arg cur_athena_table "${cur_athena_table}" \
  --arg cur_athena_workgroup "${cur_athena_workgroup}" \
  --arg cur_athena_output_location "${cur_athena_output_location}" \
  --arg cur_run_id_column "${cur_run_id_column}" \
  --arg cur_cost_column "${cur_cost_column}" \
  --arg cost_center_policy_json "${cost_center_policy_json}" \
  --arg acm_certificate_arn "${acm_certificate_arn}" \
  --argjson cloudflare_proxied "${cloudflare_proxied}" \
  --argjson cors_origins "${cors_origins_json}" \
  --argjson enable_ecs_exec "${enable_ecs_exec}" \
  --arg ui_image_uri "${ui_image_uri}" \
  --arg ui_api_base_url "${ui_api_base_url}" \
  --arg app_base_url "${app_base_url}" \
  --arg cognito_hosted_ui_url "${cognito_hosted_ui_url}" \
  --arg invite_email_from "${invite_email_from}" \
  --arg invite_email_reply_to "${invite_email_reply_to}" \
  --argjson invite_email_timeout_seconds "${invite_email_timeout_seconds}" \
  --arg internal_admins "${internal_admins}" \
  '{
    environment: $environment,
    region: $region,
    vpc_id: $vpc_id,
    private_subnet_ids: $private_subnet_ids,
    public_subnet_ids: $public_subnet_ids,
    db_password: $db_password,
    api_image_uri: $api_image_uri,
    worker_image_uri: $worker_image_uri,
    oidc_issuer: $oidc_issuer,
    oidc_audience: $oidc_audience,
    oidc_jwks_uri: $oidc_jwks_uri,
    customer_oidc_issuer: $customer_oidc_issuer,
    customer_oidc_audience: $customer_oidc_audience,
    customer_oidc_jwks_uri: $customer_oidc_jwks_uri,
    internal_oidc_issuer: $internal_oidc_issuer,
    internal_oidc_audience: $internal_oidc_audience,
    internal_oidc_jwks_uri: $internal_oidc_jwks_uri,
    dry_run_mode: $dry_run_mode,
    enable_full_byoc_mode: $enable_full_byoc_mode,
    emr_execution_role_arn: $emr_execution_role_arn,
    assume_role_external_id: $assume_role_external_id,
    allow_unsafe_rds_configuration: $allow_unsafe_rds_configuration,
    rds_deletion_protection: $rds_deletion_protection,
    rds_skip_final_snapshot: $rds_skip_final_snapshot,
    rds_final_snapshot_identifier: $rds_final_snapshot_identifier,
    cur_athena_database: $cur_athena_database,
    cur_athena_table: $cur_athena_table,
    cur_athena_workgroup: $cur_athena_workgroup,
    cur_athena_output_location: $cur_athena_output_location,
    cur_run_id_column: $cur_run_id_column,
    cur_cost_column: $cur_cost_column,
    cost_center_policy_json: $cost_center_policy_json,
    acm_certificate_arn: $acm_certificate_arn,
    cloudflare_proxied: $cloudflare_proxied,
    cors_origins: $cors_origins,
    enable_ecs_exec: $enable_ecs_exec,
    ui_image_uri: $ui_image_uri,
    ui_api_base_url: $ui_api_base_url,
    app_base_url: $app_base_url,
    cognito_hosted_ui_url: $cognito_hosted_ui_url,
    invite_email_from: $invite_email_from,
    invite_email_reply_to: $invite_email_reply_to,
    invite_email_timeout_seconds: $invite_email_timeout_seconds,
    internal_admins: $internal_admins
  }' > "${tfvars_file}"

if ! jq -e 'type == "object"' "${tfvars_file}" >/dev/null 2>&1; then
  echo "::error::Generated Terraform var-file must be a valid JSON object: ${tfvars_file}" >&2
  exit 1
fi

echo "Deploying control-plane Terraform for environment '${SPARKPILOT_ENVIRONMENT}'"
echo "Terraform root: ${terraform_root}"

contact_secret_exists=false
if aws secretsmanager describe-secret \
  --secret-id "${contact_submit_token_secret_name}" \
  --region "${AWS_REGION}" \
  --output json > /dev/null 2>"${contact_secret_error_file}"; then
  contact_secret_exists=true
else
  if grep -q "ResourceNotFoundException" "${contact_secret_error_file}"; then
    contact_secret_exists=false
  else
    echo "::error::Unable to describe contact submit token secret '${contact_submit_token_secret_name}'." >&2
    cat "${contact_secret_error_file}" >&2
    exit 1
  fi
fi
if [[ -z "${contact_submit_token}" && "${contact_secret_exists}" == "true" ]]; then
  if ! existing_contact_submit_token="$(
    aws secretsmanager get-secret-value \
      --secret-id "${contact_submit_token_secret_name}" \
      --region "${AWS_REGION}" \
      --query SecretString \
      --output text 2>"${contact_secret_error_file}"
  )"; then
    echo "::error::Unable to read existing contact submit token secret '${contact_submit_token_secret_name}'." >&2
    cat "${contact_secret_error_file}" >&2
    exit 1
  fi
  if [[ -n "${existing_contact_submit_token}" && "${existing_contact_submit_token}" != "None" && "${existing_contact_submit_token}" != "null" ]]; then
    contact_submit_token="${existing_contact_submit_token}"
  fi
fi
if [[ -z "${contact_submit_token}" ]]; then
  contact_submit_token="$(openssl rand -base64 48 | tr -d '\n')"
  echo "Generated new contact submit token for ${SPARKPILOT_ENVIRONMENT}."
else
  echo "Using configured or existing contact submit token for ${SPARKPILOT_ENVIRONMENT}."
fi
if [[ "${#contact_submit_token}" -lt 32 ]]; then
  echo "::error::CONTACT_SUBMIT_TOKEN must be at least 32 characters." >&2
  exit 1
fi
if [[ "${contact_secret_exists}" == "true" ]]; then
  aws secretsmanager put-secret-value \
    --secret-id "${contact_submit_token_secret_name}" \
    --secret-string "${contact_submit_token}" \
    --region "${AWS_REGION}" \
    --output json > /dev/null
else
  aws secretsmanager create-secret \
    --name "${contact_submit_token_secret_name}" \
    --description "SparkPilot ${SPARKPILOT_ENVIRONMENT} server-side contact form submit token" \
    --secret-string "${contact_submit_token}" \
    --region "${AWS_REGION}" \
    --tags "Key=Project,Value=${project_name_for_contact_secret}" "Key=Environment,Value=${SPARKPILOT_ENVIRONMENT}" "Key=ManagedBy,Value=deploy_control_plane" \
    --output json > /dev/null
fi
for attempt in {1..10}; do
  if aws secretsmanager describe-secret \
    --secret-id "${contact_submit_token_secret_name}" \
    --region "${AWS_REGION}" \
    --output json > /dev/null 2>"${contact_secret_error_file}"; then
    break
  fi
  if [[ "${attempt}" == "10" ]]; then
    echo "::error::Contact submit token secret '${contact_submit_token_secret_name}' was not visible after create/update." >&2
    cat "${contact_secret_error_file}" >&2
    exit 1
  fi
  sleep 2
done

export TF_IN_AUTOMATION=1
terraform -chdir="${terraform_root}" fmt -check -recursive
terraform -chdir="${terraform_root}" init -input=false -reconfigure -backend-config="${backend_file}"
terraform -chdir="${terraform_root}" validate
terraform -chdir="${terraform_root}" plan -input=false -lock-timeout=10m -out="${plan_file}" -var-file="${tfvars_file}"
terraform -chdir="${terraform_root}" apply -input=false -lock-timeout=10m -auto-approve "${plan_file}"

# ---------------------------------------------------------------------------
# Post-apply: write secret values to Secrets Manager.
#
# Secret contents are intentionally never passed to Terraform — keeping them
# out of TF state entirely. The deploy script writes them directly via the
# AWS CLI after apply, using the Terraform-provisioned secret container ARNs.
# ---------------------------------------------------------------------------

postgres_address="$(terraform -chdir="${terraform_root}" output -raw postgres_address 2>/dev/null || true)"
postgres_identifier="$(terraform -chdir="${terraform_root}" output -raw postgres_identifier 2>/dev/null || true)"
db_name="$(terraform -chdir="${terraform_root}" output -raw postgres_db_name 2>/dev/null || true)"
db_username="$(terraform -chdir="${terraform_root}" output -raw postgres_db_username 2>/dev/null || true)"
database_url_secret_arn="$(terraform -chdir="${terraform_root}" output -raw database_url_secret_arn 2>/dev/null || true)"
bootstrap_secret_arn="$(terraform -chdir="${terraform_root}" output -raw bootstrap_secret_arn 2>/dev/null || true)"
contact_submit_token_secret_arn="$(terraform -chdir="${terraform_root}" output -raw contact_submit_token_secret_arn 2>/dev/null || true)"
resend_api_key_secret_arn="$(terraform -chdir="${terraform_root}" output -raw resend_api_key_secret_arn 2>/dev/null || true)"
ecs_cluster_name="$(terraform -chdir="${terraform_root}" output -raw ecs_cluster_name 2>/dev/null || true)"
ecs_worker_service_names_json="$(terraform -chdir="${terraform_root}" output -json ecs_worker_service_names 2>/dev/null || echo '{}')"
ecs_api_service_name="$(terraform -chdir="${terraform_root}" output -raw ecs_api_service_name 2>/dev/null || true)"
ecs_task_execution_role_arn="$(terraform -chdir="${terraform_root}" output -raw ecs_task_execution_role_arn 2>/dev/null || true)"
ecs_task_runtime_role_arn="$(terraform -chdir="${terraform_root}" output -raw ecs_task_runtime_role_arn 2>/dev/null || true)"
ecs_tasks_security_group_id="$(terraform -chdir="${terraform_root}" output -raw ecs_tasks_security_group_id 2>/dev/null || true)"
alb_internal="$(terraform -chdir="${terraform_root}" output -raw alb_internal 2>/dev/null || echo "false")"
ui_enabled_out="$(terraform -chdir="${terraform_root}" output -raw ui_enabled 2>/dev/null || echo "false")"
ui_service_name="$(terraform -chdir="${terraform_root}" output -raw ui_service_name 2>/dev/null || true)"
ui_base_url="$(terraform -chdir="${terraform_root}" output -raw ui_base_url 2>/dev/null || true)"

if [[ -z "${alb_internal}" ]]; then
  alb_internal="false"
fi

if [[ -z "${database_url_secret_arn}" ]]; then
  echo "::error::Terraform output 'database_url_secret_arn' is empty." >&2
  exit 1
fi
if [[ -z "${bootstrap_secret_arn}" ]]; then
  echo "::error::Terraform output 'bootstrap_secret_arn' is empty." >&2
  exit 1
fi
if [[ -z "${contact_submit_token_secret_arn}" ]]; then
  echo "::error::Terraform output 'contact_submit_token_secret_arn' is empty." >&2
  exit 1
fi
if [[ -z "${resend_api_key_secret_arn}" ]]; then
  echo "::error::Terraform output 'resend_api_key_secret_arn' is empty." >&2
  exit 1
fi
if [[ -z "${postgres_address}" ]]; then
  echo "::error::Terraform output 'postgres_address' is empty." >&2
  exit 1
fi
if [[ -z "${postgres_identifier}" ]]; then
  echo "::error::Terraform output 'postgres_identifier' is empty." >&2
  exit 1
fi
if [[ -z "${db_name}" ]]; then
  echo "::error::Terraform output 'postgres_db_name' is empty." >&2
  exit 1
fi
if [[ -z "${db_username}" ]]; then
  echo "::error::Terraform output 'postgres_db_username' is empty." >&2
  exit 1
fi

db_instance_status="$(
  aws rds describe-db-instances \
    --db-instance-identifier "${postgres_identifier}" \
    --region "${AWS_REGION}" \
    --query 'DBInstances[0].DBInstanceStatus' \
    --output text 2>/dev/null || true
)"

if [[ "${db_instance_status}" == "stopped" ]]; then
  echo "::notice::RDS instance ${postgres_identifier} is stopped; starting it for deployment."
  aws rds start-db-instance \
    --db-instance-identifier "${postgres_identifier}" \
    --region "${AWS_REGION}" \
    --output json > /dev/null
  aws rds wait db-instance-available \
    --db-instance-identifier "${postgres_identifier}" \
    --region "${AWS_REGION}"
elif [[ "${db_instance_status}" == "stopping" ]]; then
  echo "::notice::RDS instance ${postgres_identifier} is stopping; waiting for stop, then starting."
  aws rds wait db-instance-stopped \
    --db-instance-identifier "${postgres_identifier}" \
    --region "${AWS_REGION}"
  aws rds start-db-instance \
    --db-instance-identifier "${postgres_identifier}" \
    --region "${AWS_REGION}" \
    --output json > /dev/null
  aws rds wait db-instance-available \
    --db-instance-identifier "${postgres_identifier}" \
    --region "${AWS_REGION}"
elif [[ "${db_instance_status}" != "available" ]]; then
  echo "::notice::RDS instance ${postgres_identifier} status is '${db_instance_status}'; waiting for available."
  aws rds wait db-instance-available \
    --db-instance-identifier "${postgres_identifier}" \
    --region "${AWS_REGION}"
fi

# Construct the database URL from the RDS endpoint now that it is known.
db_url="postgresql+psycopg://$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1],safe=''))" "${db_username}"):$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1],safe=''))" "${DB_PASSWORD}")@${postgres_address}:5432/${db_name}"

echo "Writing database URL to Secrets Manager..."
aws secretsmanager put-secret-value \
  --secret-id "${database_url_secret_arn}" \
  --secret-string "${db_url}" \
  --region "${AWS_REGION}" \
  --output json > /dev/null

echo "Writing bootstrap secret to Secrets Manager..."
aws secretsmanager put-secret-value \
  --secret-id "${bootstrap_secret_arn}" \
  --secret-string "${BOOTSTRAP_SECRET}" \
  --region "${AWS_REGION}" \
  --output json > /dev/null

if [[ -n "${resend_api_key}" ]]; then
  echo "Writing Resend API key to Secrets Manager..."
  aws secretsmanager put-secret-value \
    --secret-id "${resend_api_key_secret_arn}" \
    --secret-string "${resend_api_key}" \
    --region "${AWS_REGION}" \
    --output json > /dev/null
else
  echo "::notice::RESEND_API_KEY not set; skipping put-secret-value for Resend (dev environment)."
fi

echo "Running database migrations..."
# ---------------------------------------------------------------------------
# Run Alembic migrations as a one-off ECS Fargate task before bringing up
# the API service. The task uses the same API image + execution/runtime roles
# so it inherits the exact same secret injection the API service uses. We
# pass the DATABASE_URL directly (not via Secrets Manager) to avoid a timing
# race: Secrets Manager replication can lag by a few seconds after put-secret-value,
# and the Fargate task needs the value immediately at cold start.
# ---------------------------------------------------------------------------
subnet_ids_csv="$(echo "${private_subnets_json}" | jq -r 'join(",")')"

if [[ -z "${ecs_task_execution_role_arn}" || -z "${ecs_task_runtime_role_arn}" || -z "${ecs_tasks_security_group_id}" ]]; then
  echo "::error::Missing ECS role/SG Terraform outputs; cannot run migration task." >&2
  exit 1
fi

migration_overrides="$(jq -n \
  --arg db_url "${db_url}" \
  '{
    containerOverrides: [
      {
        name: "sparkpilot-api",
        command: ["alembic", "upgrade", "head"],
        environment: [
          { name: "SPARKPILOT_DATABASE_URL", value: $db_url }
        ]
      }
    ]
  }')"

migration_task_arn="$(
  aws ecs run-task \
    --cluster "${ecs_cluster_name}" \
    --task-definition "${ecs_api_service_name}" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${subnet_ids_csv}],securityGroups=[${ecs_tasks_security_group_id}],assignPublicIp=DISABLED}" \
    --overrides "${migration_overrides}" \
    --region "${AWS_REGION}" \
    --output json \
  | jq -r '.tasks[0].taskArn'
)"

if [[ -z "${migration_task_arn}" || "${migration_task_arn}" == "null" ]]; then
  echo "::error::Failed to start migration ECS task." >&2
  exit 1
fi

echo "Migration task started: ${migration_task_arn}"
echo "Waiting for migration task to complete..."
aws ecs wait tasks-stopped \
  --cluster "${ecs_cluster_name}" \
  --tasks "${migration_task_arn}" \
  --region "${AWS_REGION}"

migration_exit_code="$(
  aws ecs describe-tasks \
    --cluster "${ecs_cluster_name}" \
    --tasks "${migration_task_arn}" \
    --region "${AWS_REGION}" \
    --output json \
  | jq -r '.tasks[0].containers[0].exitCode // 1'
)"

if [[ "${migration_exit_code}" != "0" ]]; then
  echo "::error::Database migration task exited with code ${migration_exit_code}. Check CloudWatch logs for details." >&2
  exit 1
fi

echo "Database migration completed successfully (exit code ${migration_exit_code})."

echo "Secrets written. Forcing ECS service update to pull AWSCURRENT versions..."
if [[ -n "${ecs_cluster_name}" && -n "${ecs_api_service_name}" ]]; then
  aws ecs update-service \
    --cluster "${ecs_cluster_name}" \
    --service "${ecs_api_service_name}" \
    --force-new-deployment \
    --region "${AWS_REGION}" \
    --output json > /dev/null
  echo "ECS API service update triggered."

  # Redeploy UI service if deployed.
  if [[ "${ui_enabled_out:-false}" == "true" && -n "${ui_service_name:-}" ]]; then
    aws ecs update-service \
      --cluster "${ecs_cluster_name}" \
      --service "${ui_service_name}" \
      --force-new-deployment \
      --region "${AWS_REGION}" \
      --output json > /dev/null
    echo "ECS UI service update triggered: ${ui_service_name}"
  fi

  # Redeploy worker services — they consume the same secrets and must also pick
  # up AWSCURRENT after secret values change.
  worker_service_names="$(echo "${ecs_worker_service_names_json}" | jq -r 'values[]' 2>/dev/null || true)"
  while IFS= read -r worker_svc; do
    [[ -z "${worker_svc}" ]] && continue
    aws ecs update-service \
      --cluster "${ecs_cluster_name}" \
      --service "${worker_svc}" \
      --force-new-deployment \
      --region "${AWS_REGION}" \
      --output json > /dev/null
    echo "ECS worker service update triggered: ${worker_svc}"
  done <<< "${worker_service_names}"
else
  echo "::warning::Could not determine ECS cluster/service name; skipping force-update."
fi

api_base_url="$(terraform -chdir="${terraform_root}" output -raw api_base_url 2>/dev/null || true)"
if [[ -z "${api_base_url}" ]]; then
  echo "::error::Terraform output 'api_base_url' is empty. Check control-plane outputs and deployment state." >&2
  exit 1
fi

echo "Deployed API base URL: ${api_base_url}"
if [[ "${ui_enabled_out}" == "true" && -n "${ui_base_url}" ]]; then
  echo "Deployed UI base URL: ${ui_base_url}"
fi
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "api_base_url=${api_base_url}" >> "${GITHUB_OUTPUT}"
  echo "ecs_cluster_name=${ecs_cluster_name}" >> "${GITHUB_OUTPUT}"
  echo "ecs_api_service_name=${ecs_api_service_name}" >> "${GITHUB_OUTPUT}"
  echo "alb_internal=${alb_internal}" >> "${GITHUB_OUTPUT}"
  echo "ui_enabled=${ui_enabled_out}" >> "${GITHUB_OUTPUT}"
  echo "ui_base_url=${ui_base_url}" >> "${GITHUB_OUTPUT}"
  echo "ui_service_name=${ui_service_name}" >> "${GITHUB_OUTPUT}"
fi
