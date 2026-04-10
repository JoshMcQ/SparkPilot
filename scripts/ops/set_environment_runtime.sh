#!/usr/bin/env bash
set -euo pipefail

normalize_bool() {
  local raw="${1:-}"
  raw="$(echo "${raw}" | tr '[:upper:]' '[:lower:]' | xargs)"
  case "${raw}" in
    true|1|yes|y|on) echo "true" ;;
    false|0|no|n|off|"") echo "false" ;;
    *)
      echo "ERROR: invalid boolean value '${1}'" >&2
      exit 1
      ;;
  esac
}

SPARKPILOT_ENVIRONMENT="$(echo "${SPARKPILOT_ENVIRONMENT:-staging}" | xargs)"
AWS_REGION="$(echo "${AWS_REGION:-us-east-1}" | xargs)"
ACTION="$(echo "${ACTION:-down}" | tr '[:upper:]' '[:lower:]' | xargs)"

case "${ACTION}" in
  up|down) ;;
  *)
    echo "ERROR: ACTION must be 'up' or 'down'" >&2
    exit 1
    ;;
esac

if [[ "${ACTION}" == "up" ]]; then
  API_DESIRED_COUNT="${API_DESIRED_COUNT:-1}"
  UI_DESIRED_COUNT="${UI_DESIRED_COUNT:-1}"
  WORKER_DESIRED_COUNT="${WORKER_DESIRED_COUNT:-1}"
else
  API_DESIRED_COUNT="${API_DESIRED_COUNT:-0}"
  UI_DESIRED_COUNT="${UI_DESIRED_COUNT:-0}"
  WORKER_DESIRED_COUNT="${WORKER_DESIRED_COUNT:-0}"
fi

MANAGE_RDS="$(normalize_bool "${MANAGE_RDS:-true}")"
WAIT_FOR_DB_AVAILABLE="$(normalize_bool "${WAIT_FOR_DB_AVAILABLE:-false}")"
DRY_RUN="$(normalize_bool "${DRY_RUN:-false}")"

ECS_CLUSTER_NAME_OVERRIDE="$(echo "${ECS_CLUSTER_NAME_OVERRIDE:-${ECS_CLUSTER_NAME:-}}" | xargs)"
RDS_INSTANCE_IDENTIFIER="$(echo "${RDS_INSTANCE_IDENTIFIER:-sparkpilot-${SPARKPILOT_ENVIRONMENT}-postgres}" | xargs)"

run_cmd() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    printf 'DRY_RUN:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

resolve_ecs_cluster_name() {
  local -a candidates=()
  local candidate=""
  local status=""

  if [[ -n "${ECS_CLUSTER_NAME_OVERRIDE}" ]]; then
    candidates=("${ECS_CLUSTER_NAME_OVERRIDE}")
  else
    candidates=(
      "sparkpilot-${SPARKPILOT_ENVIRONMENT}-ecs"
      "sparkpilot-${SPARKPILOT_ENVIRONMENT}-control-plane"
    )
  fi

  for candidate in "${candidates[@]}"; do
    status="$(aws ecs describe-clusters \
      --clusters "${candidate}" \
      --region "${AWS_REGION}" \
      --query 'clusters[0].status' \
      --output text 2>/dev/null || true)"
    if [[ -n "${status}" && "${status}" != "None" ]]; then
      echo "${candidate}"
      return 0
    fi
  done

  echo ""
  return 1
}

service_target_count() {
  local service_name="${1}"
  if [[ "${service_name}" == *"-api" ]]; then
    echo "${API_DESIRED_COUNT}"
    return
  fi
  if [[ "${service_name}" == *"-ui" ]]; then
    echo "${UI_DESIRED_COUNT}"
    return
  fi
  echo "${WORKER_DESIRED_COUNT}"
}

ECS_CLUSTER_NAME="$(resolve_ecs_cluster_name || true)"

echo "Environment: ${SPARKPILOT_ENVIRONMENT}"
echo "Region: ${AWS_REGION}"
echo "Action: ${ACTION}"
if [[ -n "${ECS_CLUSTER_NAME}" ]]; then
  echo "ECS cluster target: ${ECS_CLUSTER_NAME}"
else
  echo "INFO: ECS cluster not found for environment '${SPARKPILOT_ENVIRONMENT}'."
fi
echo "Desired counts (api/ui/workers): ${API_DESIRED_COUNT}/${UI_DESIRED_COUNT}/${WORKER_DESIRED_COUNT}"
echo "RDS target: ${RDS_INSTANCE_IDENTIFIER}"
echo "Manage RDS: ${MANAGE_RDS}, Wait for DB available: ${WAIT_FOR_DB_AVAILABLE}, Dry run: ${DRY_RUN}"

manage_rds_runtime() {
  if [[ "${MANAGE_RDS}" != "true" ]]; then
    return
  fi

  db_status="$(aws rds describe-db-instances \
    --db-instance-identifier "${RDS_INSTANCE_IDENTIFIER}" \
    --region "${AWS_REGION}" \
    --query 'DBInstances[0].DBInstanceStatus' \
    --output text 2>/dev/null || true)"

  if [[ "${ACTION}" == "down" ]]; then
    case "${db_status}" in
      available)
        echo "Stopping RDS instance: ${RDS_INSTANCE_IDENTIFIER}"
        run_cmd aws rds stop-db-instance \
          --db-instance-identifier "${RDS_INSTANCE_IDENTIFIER}" \
          --region "${AWS_REGION}" \
          >/dev/null
        ;;
      stopped)
        echo "RDS already stopped: ${RDS_INSTANCE_IDENTIFIER}"
        ;;
      ""|None)
        echo "INFO: RDS instance not found: ${RDS_INSTANCE_IDENTIFIER}"
        ;;
      *)
        echo "INFO: RDS instance ${RDS_INSTANCE_IDENTIFIER} in status '${db_status}' - no stop action taken."
        ;;
    esac
  else
    case "${db_status}" in
      stopped)
        echo "Starting RDS instance: ${RDS_INSTANCE_IDENTIFIER}"
        run_cmd aws rds start-db-instance \
          --db-instance-identifier "${RDS_INSTANCE_IDENTIFIER}" \
          --region "${AWS_REGION}" \
          >/dev/null
        if [[ "${WAIT_FOR_DB_AVAILABLE}" == "true" ]]; then
          if [[ "${DRY_RUN}" == "true" ]]; then
            echo "DRY_RUN: aws rds wait db-instance-available --db-instance-identifier '${RDS_INSTANCE_IDENTIFIER}' --region '${AWS_REGION}'"
          else
            echo "Waiting for RDS to become available..."
            aws rds wait db-instance-available --db-instance-identifier "${RDS_INSTANCE_IDENTIFIER}" --region "${AWS_REGION}"
          fi
        fi
        ;;
      available)
        echo "RDS already available: ${RDS_INSTANCE_IDENTIFIER}"
        ;;
      ""|None)
        echo "INFO: RDS instance not found: ${RDS_INSTANCE_IDENTIFIER}"
        ;;
      *)
        echo "INFO: RDS instance ${RDS_INSTANCE_IDENTIFIER} in status '${db_status}' - no start action taken."
        ;;
    esac
  fi
}

scale_ecs_services() {
  if [[ -z "${ECS_CLUSTER_NAME}" ]]; then
    return
  fi

  services="$(aws ecs list-services \
    --cluster "${ECS_CLUSTER_NAME}" \
    --region "${AWS_REGION}" \
    --query 'serviceArns' \
    --output text 2>/dev/null || true)"

  if [[ -z "${services}" || "${services}" == "None" ]]; then
    echo "INFO: no ECS services found in ${ECS_CLUSTER_NAME}"
    return
  fi

  for service_arn in ${services}; do
    service_name="${service_arn##*/}"
    desired_target="$(service_target_count "${service_name}")"
    current_desired="$(aws ecs describe-services \
      --cluster "${ECS_CLUSTER_NAME}" \
      --services "${service_name}" \
      --region "${AWS_REGION}" \
      --query 'services[0].desiredCount' \
      --output text 2>/dev/null || echo "-1")"

    if [[ "${current_desired}" != "${desired_target}" ]]; then
      echo "Updating ECS service ${service_name}: ${current_desired} -> ${desired_target}"
      run_cmd aws ecs update-service \
        --cluster "${ECS_CLUSTER_NAME}" \
        --service "${service_name}" \
        --desired-count "${desired_target}" \
        --region "${AWS_REGION}" \
        >/dev/null
    else
      echo "ECS service already at desired count: ${service_name}=${desired_target}"
    fi
  done
}

# Bring database up before scaling services on ACTION=up.
if [[ "${ACTION}" == "up" ]]; then
  manage_rds_runtime
fi

scale_ecs_services

# Scale services down before stopping database on ACTION=down.
if [[ "${ACTION}" == "down" ]]; then
  manage_rds_runtime
fi

echo "Environment runtime toggle completed."
