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
cleanup() {
  rm -f "${backend_file}" "${tfvars_file}" "${plan_file}"
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
  --argjson enable_ecs_exec "${enable_ecs_exec}" \
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
    enable_ecs_exec: $enable_ecs_exec
  }' > "${tfvars_file}"

if ! jq -e 'type == "object"' "${tfvars_file}" >/dev/null 2>&1; then
  echo "::error::Generated Terraform var-file must be a valid JSON object: ${tfvars_file}" >&2
  exit 1
fi

echo "Deploying control-plane Terraform for environment '${SPARKPILOT_ENVIRONMENT}'"
echo "Terraform root: ${terraform_root}"

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
db_name="$(terraform -chdir="${terraform_root}" output -raw postgres_db_name 2>/dev/null || true)"
db_username="$(terraform -chdir="${terraform_root}" output -raw postgres_db_username 2>/dev/null || true)"
database_url_secret_arn="$(terraform -chdir="${terraform_root}" output -raw database_url_secret_arn 2>/dev/null || true)"
bootstrap_secret_arn="$(terraform -chdir="${terraform_root}" output -raw bootstrap_secret_arn 2>/dev/null || true)"
ecs_cluster_name="$(terraform -chdir="${terraform_root}" output -raw ecs_cluster_name 2>/dev/null || true)"
ecs_worker_service_names_json="$(terraform -chdir="${terraform_root}" output -json ecs_worker_service_names 2>/dev/null || echo '{}')"
ecs_api_service_name="$(terraform -chdir="${terraform_root}" output -raw ecs_api_service_name 2>/dev/null || true)"

if [[ -z "${database_url_secret_arn}" ]]; then
  echo "::error::Terraform output 'database_url_secret_arn' is empty." >&2
  exit 1
fi
if [[ -z "${bootstrap_secret_arn}" ]]; then
  echo "::error::Terraform output 'bootstrap_secret_arn' is empty." >&2
  exit 1
fi
if [[ -z "${postgres_address}" ]]; then
  echo "::error::Terraform output 'postgres_address' is empty." >&2
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

echo "Secrets written. Forcing ECS service update to pull AWSCURRENT versions..."
if [[ -n "${ecs_cluster_name}" && -n "${ecs_api_service_name}" ]]; then
  aws ecs update-service \
    --cluster "${ecs_cluster_name}" \
    --service "${ecs_api_service_name}" \
    --force-new-deployment \
    --region "${AWS_REGION}" \
    --output json > /dev/null
  echo "ECS API service update triggered."

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
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "api_base_url=${api_base_url}" >> "${GITHUB_OUTPUT}"
fi
