#!/usr/bin/env bash
#
# ECS scale-down is safe with SPARKPILOT_ENVIRONMENT=prod when SCALE_ECS=true and STOP_RDS=false:
# avoids task/Fargate hours without stopping production RDS from CI (.github/workflows/ci-cd.yml).
#
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

SPARKPILOT_ENVIRONMENT="$(echo "${SPARKPILOT_ENVIRONMENT:-dev}" | xargs)"
AWS_REGION="$(echo "${AWS_REGION:-us-east-1}" | xargs)"
ECS_CLUSTER_NAME_OVERRIDE="$(echo "${ECS_CLUSTER_NAME:-}" | xargs)"
RDS_INSTANCE_IDENTIFIER="$(echo "${RDS_INSTANCE_IDENTIFIER:-sparkpilot-${SPARKPILOT_ENVIRONMENT}-postgres}" | xargs)"

SCALE_ECS="$(normalize_bool "${SCALE_ECS:-true}")"
STOP_RDS="$(normalize_bool "${STOP_RDS:-true}")"
DRY_RUN="$(normalize_bool "${DRY_RUN:-false}")"

run_cmd() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "DRY_RUN: $*"
  else
    eval "$*"
  fi
}

resolve_ecs_cluster_name() {
  local -a candidates=()
  local candidate=""
  local status=""

  if [[ -n "${ECS_CLUSTER_NAME_OVERRIDE}" ]]; then
    candidates=("${ECS_CLUSTER_NAME_OVERRIDE}")
  else
    # Support both historical and current naming patterns.
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

ECS_CLUSTER_NAME="$(resolve_ecs_cluster_name || true)"

echo "Environment: ${SPARKPILOT_ENVIRONMENT}"
echo "Region: ${AWS_REGION}"
if [[ -n "${ECS_CLUSTER_NAME}" ]]; then
  echo "ECS cluster target: ${ECS_CLUSTER_NAME}"
else
  if [[ -n "${ECS_CLUSTER_NAME_OVERRIDE}" ]]; then
    echo "ECS cluster target: ${ECS_CLUSTER_NAME_OVERRIDE} (not found)"
  else
    echo "ECS cluster target: sparkpilot-${SPARKPILOT_ENVIRONMENT}-ecs|sparkpilot-${SPARKPILOT_ENVIRONMENT}-control-plane (not found)"
  fi
fi
echo "RDS target: ${RDS_INSTANCE_IDENTIFIER}"
echo "Scale ECS: ${SCALE_ECS}, Stop RDS: ${STOP_RDS}, Dry run: ${DRY_RUN}"

if [[ "${SCALE_ECS}" == "true" ]]; then
  if [[ -z "${ECS_CLUSTER_NAME}" ]]; then
    if [[ -n "${ECS_CLUSTER_NAME_OVERRIDE}" ]]; then
      echo "INFO: ECS cluster not found: ${ECS_CLUSTER_NAME_OVERRIDE}"
    else
      echo "INFO: ECS cluster not found for environment '${SPARKPILOT_ENVIRONMENT}'"
    fi
  else
    services="$(aws ecs list-services \
      --cluster "${ECS_CLUSTER_NAME}" \
      --region "${AWS_REGION}" \
      --query 'serviceArns' \
      --output text 2>/dev/null || true)"

    if [[ -z "${services}" || "${services}" == "None" ]]; then
      echo "INFO: no ECS services found in ${ECS_CLUSTER_NAME}"
    else
      for service_arn in ${services}; do
        service_name="${service_arn##*/}"
        desired_count="$(aws ecs describe-services \
          --cluster "${ECS_CLUSTER_NAME}" \
          --services "${service_name}" \
          --region "${AWS_REGION}" \
          --query 'services[0].desiredCount' \
          --output text 2>/dev/null || echo 0)"

        if [[ "${desired_count}" != "0" ]]; then
          echo "Scaling ECS service to 0: ${service_name} (was ${desired_count})"
          run_cmd "aws ecs update-service --cluster '${ECS_CLUSTER_NAME}' --service '${service_name}' --desired-count 0 --region '${AWS_REGION}' >/dev/null"
        else
          echo "ECS service already at 0: ${service_name}"
        fi
      done
    fi
  fi
fi

if [[ "${STOP_RDS}" == "true" ]]; then
  db_status="$(aws rds describe-db-instances \
    --db-instance-identifier "${RDS_INSTANCE_IDENTIFIER}" \
    --region "${AWS_REGION}" \
    --query 'DBInstances[0].DBInstanceStatus' \
    --output text 2>/dev/null || true)"

  case "${db_status}" in
    available)
      echo "Stopping RDS instance: ${RDS_INSTANCE_IDENTIFIER}"
      run_cmd "aws rds stop-db-instance --db-instance-identifier '${RDS_INSTANCE_IDENTIFIER}' --region '${AWS_REGION}' >/dev/null"
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
fi

echo "Non-prod scale-down routine completed."
