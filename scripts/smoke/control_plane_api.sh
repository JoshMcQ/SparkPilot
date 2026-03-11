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

echo "Running control-plane smoke checks against ${api_base_url}"

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
