#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

SMOKE_BASE_URL="${SMOKE_BASE_URL:-http://localhost:8000}"
SMOKE_OIDC_ISSUER="${SMOKE_OIDC_ISSUER:-http://localhost:8080}"
SMOKE_OIDC_AUDIENCE="${SMOKE_OIDC_AUDIENCE:-sparkpilot-api}"
SMOKE_OIDC_CLIENT_ID="${SMOKE_OIDC_CLIENT_ID:-sparkpilot-cli}"
SMOKE_OIDC_CLIENT_SECRET="${SMOKE_OIDC_CLIENT_SECRET:-sparkpilot-cli-secret}"
SMOKE_OIDC_TOKEN_ENDPOINT="${SMOKE_OIDC_TOKEN_ENDPOINT:-http://localhost:8080/oauth/token}"
SMOKE_BOOTSTRAP_SECRET="${SMOKE_BOOTSTRAP_SECRET:-sparkpilot-local-bootstrap-secret}"
SMOKE_CUSTOMER_ROLE_ARN="${SMOKE_CUSTOMER_ROLE_ARN:-arn:aws:iam::123456789012:role/SparkPilotCustomerRole}"
SMOKE_EKS_CLUSTER_ARN="${SMOKE_EKS_CLUSTER_ARN:-arn:aws:eks:us-east-1:123456789012:cluster/local-smoke}"
SMOKE_EKS_NAMESPACE="${SMOKE_EKS_NAMESPACE:-sparkpilot-smoke}"
SMOKE_ARTIFACT_URI="${SMOKE_ARTIFACT_URI:-s3://sparkpilot-smoke/job.py}"
SMOKE_ENTRYPOINT="${SMOKE_ENTRYPOINT:-main}"
SMOKE_COMPOSE_BUILD="${SMOKE_COMPOSE_BUILD:-false}"
SMOKE_ARTIFACT_DIR="${SMOKE_ARTIFACT_DIR:-output/smoke/local-stack-$(date -u +%Y%m%d-%H%M%S)}"

SMOKE_STACK_STARTUP_ATTEMPTS="${SMOKE_STACK_STARTUP_ATTEMPTS:-3}"
SMOKE_STACK_RETRY_DELAY_SECONDS="${SMOKE_STACK_RETRY_DELAY_SECONDS:-5}"
SMOKE_STACK_WAIT_TIMEOUT_SECONDS="${SMOKE_STACK_WAIT_TIMEOUT_SECONDS:-300}"
SMOKE_STACK_WAIT_POLL_SECONDS="${SMOKE_STACK_WAIT_POLL_SECONDS:-5}"

SMOKE_FLOW_ATTEMPTS="${SMOKE_FLOW_ATTEMPTS:-2}"
SMOKE_FLOW_RETRY_DELAY_SECONDS="${SMOKE_FLOW_RETRY_DELAY_SECONDS:-10}"
SMOKE_FLOW_TIMEOUT_SECONDS="${SMOKE_FLOW_TIMEOUT_SECONDS:-420}"

SMOKE_PRESERVE_STACK_ON_FAILURE="${SMOKE_PRESERVE_STACK_ON_FAILURE:-false}"

mkdir -p "${SMOKE_ARTIFACT_DIR}"

smoke_started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
smoke_started_epoch="$(date +%s)"
smoke_status="failed"
smoke_classification="infra_startup"
smoke_stage="stack_startup"
smoke_error="smoke flow did not complete"
smoke_attempts_used="0"
smoke_summary_path="${SMOKE_ARTIFACT_DIR}/live_byoc_lite_summary.json"
local_summary_path="${SMOKE_ARTIFACT_DIR}/local_stack_summary.json"

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

if ! command -v docker >/dev/null 2>&1; then
  echo "::error::docker is required but was not found in PATH." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "::error::docker compose is required but unavailable." >&2
  exit 1
fi

python_cmd=()

select_python() {
  local -a candidate=("$@")
  if "${candidate[@]}" -c "import httpx" >/dev/null 2>&1; then
    python_cmd=("${candidate[@]}")
    return 0
  fi
  return 1
}

if [[ -n "${SMOKE_PYTHON_BIN:-}" ]]; then
  # shellcheck disable=SC2206
  python_cmd=(${SMOKE_PYTHON_BIN})
  if ! "${python_cmd[@]}" -c "import httpx" >/dev/null 2>&1; then
    echo "::error::SMOKE_PYTHON_BIN is set but cannot import required module 'httpx'." >&2
    exit 1
  fi
else
  if command -v python3 >/dev/null 2>&1; then
    select_python python3 || true
  fi
  if [[ ${#python_cmd[@]} -eq 0 ]] && command -v python >/dev/null 2>&1; then
    select_python python || true
  fi
  if [[ ${#python_cmd[@]} -eq 0 ]] && command -v py >/dev/null 2>&1; then
    select_python py -3 || true
  fi
  if [[ ${#python_cmd[@]} -eq 0 ]]; then
    echo "::error::No suitable Python interpreter found with 'httpx' installed. Set SMOKE_PYTHON_BIN explicitly." >&2
    exit 1
  fi
fi

retry_fixed() {
  local attempts="$1"
  local delay_seconds="$2"
  shift 2

  local i=1
  while true; do
    if "$@"; then
      return 0
    fi
    if [[ "${i}" -ge "${attempts}" ]]; then
      return 1
    fi
    log "Command failed (attempt ${i}/${attempts}). Retrying in ${delay_seconds}s..."
    sleep "${delay_seconds}"
    i=$((i + 1))
  done
}

service_container_id() {
  local service="$1"
  docker compose ps -q "${service}" 2>/dev/null | head -n 1
}

service_status() {
  local service="$1"
  local container_id
  container_id="$(service_container_id "${service}")"
  if [[ -z "${container_id}" ]]; then
    echo "missing"
    return 0
  fi
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_id}" 2>/dev/null || echo "unknown"
}

check_http_health() {
  local url="$1"
  "${python_cmd[@]}" - "${url}" <<'PY' >/dev/null
import sys
import urllib.request

url = sys.argv[1]
with urllib.request.urlopen(url, timeout=5) as response:
    if response.status >= 400:
        raise RuntimeError(f"{url} returned status {response.status}")
PY
}

wait_for_stack_ready() {
  local deadline=$((SECONDS + SMOKE_STACK_WAIT_TIMEOUT_SECONDS))
  local -a must_be_healthy=(postgres sparkpilot-oidc sparkpilot-api)
  local -a must_be_running=(sparkpilot-provisioner sparkpilot-scheduler sparkpilot-reconciler)

  while ((SECONDS < deadline)); do
    local all_ready="true"
    local status_report=()

    local service status
    for service in "${must_be_healthy[@]}"; do
      status="$(service_status "${service}")"
      status_report+=("${service}=${status}")
      if [[ "${status}" != "healthy" ]]; then
        all_ready="false"
      fi
    done

    for service in "${must_be_running[@]}"; do
      status="$(service_status "${service}")"
      status_report+=("${service}=${status}")
      if [[ "${status}" != "running" && "${status}" != "healthy" ]]; then
        all_ready="false"
      fi
    done

    log "Service readiness: ${status_report[*]}"

    if [[ "${all_ready}" == "true" ]]; then
      if check_http_health "${SMOKE_BASE_URL%/}/healthz" && check_http_health "${SMOKE_OIDC_ISSUER%/}/healthz"; then
        return 0
      fi
      log "HTTP health checks not ready yet: api=${SMOKE_BASE_URL%/}/healthz oidc=${SMOKE_OIDC_ISSUER%/}/healthz"
    fi

    sleep "${SMOKE_STACK_WAIT_POLL_SECONDS}"
  done

  return 1
}

read_smoke_summary_field() {
  local file_path="$1"
  local field="$2"
  local default_value="$3"
  if [[ ! -f "${file_path}" ]]; then
    printf '%s' "${default_value}"
    return 0
  fi
  "${python_cmd[@]}" - "${file_path}" "${field}" "${default_value}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
field = sys.argv[2]
default = sys.argv[3]
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print(default)
    raise SystemExit(0)
value = payload.get(field, default)
if value is None:
    print(default)
else:
    print(str(value))
PY
}

capture_compose_diagnostics() {
  docker compose ps -a >"${SMOKE_ARTIFACT_DIR}/docker_compose_ps.txt" 2>&1 || true
  docker compose config --services >"${SMOKE_ARTIFACT_DIR}/docker_compose_services.txt" 2>&1 || true
  docker compose logs --no-color --timestamps >"${SMOKE_ARTIFACT_DIR}/docker_compose_logs.txt" 2>&1 || true

  local service container_id
  for service in postgres sparkpilot-oidc sparkpilot-api sparkpilot-provisioner sparkpilot-scheduler sparkpilot-reconciler; do
    container_id="$(service_container_id "${service}")"
    if [[ -n "${container_id}" ]]; then
      docker inspect "${container_id}" >"${SMOKE_ARTIFACT_DIR}/inspect_${service}.json" 2>&1 || true
      docker logs --timestamps "${container_id}" >"${SMOKE_ARTIFACT_DIR}/logs_${service}.txt" 2>&1 || true
    fi
  done
}

write_local_summary() {
  local completed_at duration_seconds
  completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  duration_seconds="$(( $(date +%s) - smoke_started_epoch ))"

  (
    export SMOKE_STARTED_AT="${smoke_started_at}"
    export SMOKE_COMPLETED_AT="${completed_at}"
    export SMOKE_DURATION_SECONDS="${duration_seconds}"
    export SMOKE_STATUS="${smoke_status}"
    export SMOKE_CLASSIFICATION="${smoke_classification}"
    export SMOKE_STAGE="${smoke_stage}"
    export SMOKE_ERROR="${smoke_error}"
    export SMOKE_ATTEMPTS_USED="${smoke_attempts_used}"
    export SMOKE_STACK_STARTUP_ATTEMPTS="${SMOKE_STACK_STARTUP_ATTEMPTS}"
    export SMOKE_STACK_WAIT_TIMEOUT_SECONDS="${SMOKE_STACK_WAIT_TIMEOUT_SECONDS}"
    export SMOKE_FLOW_ATTEMPTS="${SMOKE_FLOW_ATTEMPTS}"
    export SMOKE_FLOW_TIMEOUT_SECONDS="${SMOKE_FLOW_TIMEOUT_SECONDS}"
    export SMOKE_ARTIFACT_DIR="${SMOKE_ARTIFACT_DIR}"
    "${python_cmd[@]}" - "${local_summary_path}" "${smoke_summary_path}" "${SMOKE_ARTIFACT_DIR}" <<'PY'
import json
import os
import pathlib
import sys

destination = pathlib.Path(sys.argv[1])
smoke_summary_path = pathlib.Path(sys.argv[2])
artifact_dir = sys.argv[3]
smoke_summary = None
if smoke_summary_path.exists():
    try:
        smoke_summary = json.loads(smoke_summary_path.read_text(encoding="utf-8"))
    except Exception:
        smoke_summary = None

payload = {
    "summary_version": 1,
    "started_at": os.environ.get("SMOKE_STARTED_AT", ""),
    "completed_at": os.environ.get("SMOKE_COMPLETED_AT", ""),
    "duration_seconds": int(os.environ.get("SMOKE_DURATION_SECONDS", "0") or "0"),
    "status": os.environ.get("SMOKE_STATUS", "failed"),
    "classification": os.environ.get("SMOKE_CLASSIFICATION", "unknown"),
    "stage": os.environ.get("SMOKE_STAGE", "unknown"),
    "error": os.environ.get("SMOKE_ERROR", ""),
    "attempts_used": int(os.environ.get("SMOKE_ATTEMPTS_USED", "0") or "0"),
    "policy": {
        "stack_startup_attempts": int(os.environ.get("SMOKE_STACK_STARTUP_ATTEMPTS", "0") or "0"),
        "stack_wait_timeout_seconds": int(os.environ.get("SMOKE_STACK_WAIT_TIMEOUT_SECONDS", "0") or "0"),
        "flow_attempts": int(os.environ.get("SMOKE_FLOW_ATTEMPTS", "0") or "0"),
        "flow_timeout_seconds": int(os.environ.get("SMOKE_FLOW_TIMEOUT_SECONDS", "0") or "0"),
    },
    "artifact_dir": artifact_dir,
    "flow_summary_path": str(smoke_summary_path),
    "flow_summary": smoke_summary,
}
destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
  )
}

cleanup() {
  capture_compose_diagnostics
  write_local_summary

  if [[ "${SMOKE_PRESERVE_STACK_ON_FAILURE,,}" == "true" && "${smoke_status}" != "passed" ]]; then
    log "Preserving compose stack for debugging because SMOKE_PRESERVE_STACK_ON_FAILURE=true."
    return
  fi

  docker compose down -v >"${SMOKE_ARTIFACT_DIR}/docker_compose_down.txt" 2>&1 || true
}

trap cleanup EXIT

compose_cmd=(docker compose up -d)
if [[ "${SMOKE_COMPOSE_BUILD,,}" == "true" ]]; then
  compose_cmd+=(--build)
fi
compose_cmd+=(postgres sparkpilot-oidc sparkpilot-api sparkpilot-provisioner sparkpilot-scheduler sparkpilot-reconciler)

log "Starting local SparkPilot stack for E2E smoke..."
if ! retry_fixed "${SMOKE_STACK_STARTUP_ATTEMPTS}" "${SMOKE_STACK_RETRY_DELAY_SECONDS}" "${compose_cmd[@]}"; then
  smoke_status="failed"
  smoke_classification="infra_startup"
  smoke_stage="docker_compose_up"
  smoke_error="docker compose up failed after retry policy"
  echo "::error::${smoke_error}" >&2
  exit 1
fi

log "Waiting for container and HTTP health checks..."
if ! wait_for_stack_ready; then
  smoke_status="failed"
  smoke_classification="infra_startup"
  smoke_stage="stack_health_wait"
  smoke_error="stack health checks did not become ready within timeout"
  echo "::error::${smoke_error}" >&2
  exit 1
fi

smoke_status="failed"
smoke_classification="unknown"
smoke_stage="smoke_flow"
smoke_error="smoke flow failed"

for ((attempt=1; attempt<=SMOKE_FLOW_ATTEMPTS; attempt++)); do
  smoke_attempts_used="${attempt}"
  attempt_summary_path="${SMOKE_ARTIFACT_DIR}/live_byoc_lite_summary_attempt_${attempt}.json"
  log "Running app-level BYOC-Lite smoke flow (attempt ${attempt}/${SMOKE_FLOW_ATTEMPTS})..."

  smoke_cmd=(
    "${python_cmd[@]}" scripts/smoke/live_byoc_lite.py
    --base-url "${SMOKE_BASE_URL}"
    --oidc-issuer "${SMOKE_OIDC_ISSUER}"
    --oidc-audience "${SMOKE_OIDC_AUDIENCE}"
    --oidc-client-id "${SMOKE_OIDC_CLIENT_ID}"
    --oidc-client-secret "${SMOKE_OIDC_CLIENT_SECRET}"
    --oidc-token-endpoint "${SMOKE_OIDC_TOKEN_ENDPOINT}"
    --bootstrap-secret "${SMOKE_BOOTSTRAP_SECRET}"
    --customer-role-arn "${SMOKE_CUSTOMER_ROLE_ARN}"
    --eks-cluster-arn "${SMOKE_EKS_CLUSTER_ARN}"
    --eks-namespace "${SMOKE_EKS_NAMESPACE}"
    --artifact-uri "${SMOKE_ARTIFACT_URI}"
    --entrypoint "${SMOKE_ENTRYPOINT}"
    --timeout-seconds 180
    --wait-timeout-seconds 240
    --poll-seconds 2
    --summary-path "${attempt_summary_path}"
  )

  set +e
  if command -v timeout >/dev/null 2>&1; then
    timeout "${SMOKE_FLOW_TIMEOUT_SECONDS}s" "${smoke_cmd[@]}"
    run_rc=$?
  else
    "${smoke_cmd[@]}"
    run_rc=$?
  fi
  set -e

  if [[ "${run_rc}" -eq 0 ]]; then
    cp "${attempt_summary_path}" "${smoke_summary_path}" 2>/dev/null || true
    smoke_status="passed"
    smoke_classification="success"
    smoke_stage="completed"
    smoke_error=""
    log "Local stack smoke flow passed."
    exit 0
  fi

  smoke_classification="$(read_smoke_summary_field "${attempt_summary_path}" "classification" "unknown")"
  smoke_stage="$(read_smoke_summary_field "${attempt_summary_path}" "stage" "smoke_flow")"
  smoke_error="$(read_smoke_summary_field "${attempt_summary_path}" "error" "smoke flow failed")"
  cp "${attempt_summary_path}" "${smoke_summary_path}" 2>/dev/null || true

  if [[ "${run_rc}" -eq 124 ]]; then
    smoke_classification="run_state_timeout"
    smoke_stage="smoke_flow_timeout"
    smoke_error="smoke command exceeded SMOKE_FLOW_TIMEOUT_SECONDS=${SMOKE_FLOW_TIMEOUT_SECONDS}"
  fi

  log "Smoke attempt ${attempt} failed: classification=${smoke_classification} stage=${smoke_stage} error=${smoke_error}"
  if [[ "${attempt}" -lt "${SMOKE_FLOW_ATTEMPTS}" ]]; then
    log "Retrying smoke flow in ${SMOKE_FLOW_RETRY_DELAY_SECONDS}s..."
    sleep "${SMOKE_FLOW_RETRY_DELAY_SECONDS}"
  fi
done

echo "::error::Local stack smoke flow failed after ${SMOKE_FLOW_ATTEMPTS} attempts. classification=${smoke_classification} stage=${smoke_stage}" >&2
exit 1
