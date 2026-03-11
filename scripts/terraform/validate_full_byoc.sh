#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BYOC_ROOT="$ROOT/infra/terraform/full-byoc"

DIRS=(
  "$BYOC_ROOT"
  "$BYOC_ROOT/network"
  "$BYOC_ROOT/eks"
  "$BYOC_ROOT/emr"
)

if [[ -n "${TERRAFORM_BIN:-}" ]]; then
  TERRAFORM="$TERRAFORM_BIN"
elif command -v terraform >/dev/null 2>&1; then
  TERRAFORM="terraform"
elif [[ -x "$ROOT/tools/terraform/1.7.5/terraform.exe" ]]; then
  TERRAFORM="$ROOT/tools/terraform/1.7.5/terraform.exe"
else
  echo "Terraform binary not found. Set TERRAFORM_BIN or install terraform in PATH."
  exit 1
fi

FAILED=0

echo "=== Terraform fmt check ==="
pushd "$BYOC_ROOT" > /dev/null
if "$TERRAFORM" fmt -check -recursive .; then
  echo "PASS: fmt check"
else
  echo "FAIL: fmt check"
  FAILED=1
fi
popd > /dev/null

for DIR in "${DIRS[@]}"; do
  echo ""
  echo "=== $DIR ==="
  pushd "$DIR" > /dev/null
  if "$TERRAFORM" init -backend=false -input=false -no-color && "$TERRAFORM" validate -no-color; then
    echo "PASS: $DIR"
  else
    echo "FAIL: $DIR"
    FAILED=1
  fi
  popd > /dev/null
done

echo ""
if [ $FAILED -eq 1 ]; then
  echo "=== VALIDATION FAILED ==="
  exit 1
else
  echo "=== VALIDATION PASSED ==="
  exit 0
fi
