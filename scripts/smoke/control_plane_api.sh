#!/usr/bin/env bash
set -euo pipefail

require_env() {
  local var_name="$1"
  if [[ -z "${!var_name:-}" ]]; then
    echo "::error::Missing required environment variable: ${var_name}" >&2
    exit 1
  fi
}

if ! command -v curl >/dev/null 2>&1; then
  echo "::error::curl is required but was not found in PATH." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "::error::jq is required but was not found in PATH." >&2
  exit 1
fi

require_env "API_BASE_URL"

api_base_url="${API_BASE_URL%/}"
health_url="${api_base_url}/healthz"
auth_probe_url="${api_base_url}/v1/environments"
max_attempts="${SMOKE_MAX_ATTEMPTS:-30}"
sleep_seconds="${SMOKE_SLEEP_SECONDS:-5}"
internal_max_attempts="${SMOKE_INTERNAL_MAX_ATTEMPTS:-90}"
api_host="${api_base_url#*://}"
api_host="${api_host%%/*}"
alb_internal_raw="${ALB_INTERNAL:-}"
alb_internal_normalized="$(echo "${alb_internal_raw}" | tr '[:upper:]' '[:lower:]')"
is_internal_alb="false"

if [[ "${alb_internal_normalized}" == "true" ]]; then
  is_internal_alb="true"
elif [[ "${alb_internal_normalized}" == "false" ]]; then
  is_internal_alb="false"
elif [[ "${api_host}" == internal-* ]]; then
  # Backward compatibility if ALB_INTERNAL was not exported yet.
  is_internal_alb="true"
fi

echo "Running control-plane smoke checks against ${api_base_url}"

# GitHub-hosted runners cannot reach private/internal ALBs directly.
# For internal endpoints, validate ECS service health via the ECS API instead.
if [[ "${is_internal_alb}" == "true" ]]; then
  require_env "ECS_CLUSTER_NAME"
  require_env "ECS_API_SERVICE_NAME"
  require_env "AWS_REGION"

  if ! command -v aws >/dev/null 2>&1; then
    echo "::error::aws CLI is required for internal endpoint smoke checks." >&2
    exit 1
  fi

  echo "::notice::Detected internal ALB endpoint (${api_host}); using ECS service health checks instead of direct HTTP."

  attempt=1
  last_service_payload=""
  while [[ "${attempt}" -le "${internal_max_attempts}" ]]; do
    service_payload="$(
      aws ecs describe-services \
        --cluster "${ECS_CLUSTER_NAME}" \
        --services "${ECS_API_SERVICE_NAME}" \
        --region "${AWS_REGION}" \
        --output json || true
    )"

    if [[ -n "${service_payload}" ]]; then
      last_service_payload="${service_payload}"
      service_count="$(echo "${service_payload}" | jq -r '.services | length')"
      if [[ "${service_count}" -gt 0 ]]; then
        service_status="$(echo "${service_payload}" | jq -r '.services[0].status // ""')"
        desired_count="$(echo "${service_payload}" | jq -r '.services[0].desiredCount // 0')"
        running_count="$(echo "${service_payload}" | jq -r '.services[0].runningCount // 0')"
        pending_count="$(echo "${service_payload}" | jq -r '.services[0].pendingCount // 0')"
        primary_rollout_state="$(echo "${service_payload}" | jq -r '([.services[0].deployments[]? | select(.status == "PRIMARY")][0].rolloutState) // ""')"

        if [[ "${service_status}" == "ACTIVE" && "${desired_count}" -gt 0 && "${running_count}" -ge "${desired_count}" && "${pending_count}" -eq 0 && "${primary_rollout_state}" != "FAILED" ]]; then
          echo "ECS service health check passed on attempt ${attempt}/${internal_max_attempts}."
          echo "Skipping unauthenticated HTTP probe for internal endpoint."
          echo "Smoke checks passed."
          exit 0
        fi

        echo "ECS service not ready (attempt ${attempt}/${internal_max_attempts}): status=${service_status}, desired=${desired_count}, running=${running_count}, pending=${pending_count}, primary_rollout_state=${primary_rollout_state}"
      else
        echo "ECS service lookup returned no services (attempt ${attempt}/${internal_max_attempts})."
      fi
    else
      echo "ECS service lookup failed (attempt ${attempt}/${internal_max_attempts})."
    fi

    if [[ "${attempt}" -eq "${internal_max_attempts}" ]]; then
      echo "::error::ECS service did not reach a healthy state within ${internal_max_attempts} attempts." >&2
      if [[ -n "${last_service_payload}" ]]; then
        echo "Last ECS describe-services payload:"
        echo "${last_service_payload}" | jq .
      fi
      exit 1
    fi

    sleep "${sleep_seconds}"
    attempt=$((attempt + 1))
  done
fi

echo "::notice::Endpoint (${api_host}) is external; proceeding with HTTP health checks."

attempt=1
last_payload=""
while [[ "${attempt}" -le "${max_attempts}" ]]; do
  payload="$(curl -fsS --max-time 10 "${health_url}" || true)"
  if [[ -n "${payload}" ]]; then
    last_payload="${payload}"
    status="$(echo "${payload}" | jq -r '.status // ""')"
    db_status="$(echo "${payload}" | jq -r '.checks.database.status // ""')"
    aws_status="$(echo "${payload}" | jq -r '.checks.aws.status // ""')"
    if [[ "${status}" == "ok" && "${db_status}" == "ok" && "${aws_status}" != "error" ]]; then
      echo "Health check passed on attempt ${attempt}/${max_attempts}."
      break
    fi
    echo "Health check not ready (attempt ${attempt}/${max_attempts}): status=${status}, database=${db_status}, aws=${aws_status}"
  else
    echo "Health check request failed (attempt ${attempt}/${max_attempts})."
  fi

  if [[ "${attempt}" -eq "${max_attempts}" ]]; then
    echo "::error::Health check did not reach a healthy state within ${max_attempts} attempts." >&2
    if [[ -n "${last_payload}" ]]; then
      echo "Last /healthz payload:"
      echo "${last_payload}" | jq .
    fi
    exit 1
  fi

  sleep "${sleep_seconds}"
  attempt=$((attempt + 1))
done

auth_code="$(curl -sS -o /dev/null -w "%{http_code}" "${auth_probe_url}")"
if [[ "${auth_code}" != "401" ]]; then
  echo "::error::Expected unauthenticated GET ${auth_probe_url} to return 401, got ${auth_code}." >&2
  exit 1
fi

echo "Auth sanity check passed (unauthenticated request returned 401)."
echo "Smoke checks passed."
