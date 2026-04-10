#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PUBLIC_SITE_DIR="${ROOT_DIR}/public-site"
DIST_DIR="${ROOT_DIR}/public-site/dist"
APP_URL_RAW="${PUBLIC_SITE_APP_URL:-https://app.sparkpilot.cloud}"
APP_URL="${APP_URL_RAW%/}"
OUT_DIR="${PUBLIC_SITE_DIR}/out"

if [[ ! -f "${PUBLIC_SITE_DIR}/package.json" ]]; then
  echo "ERROR: public-site package.json not found: ${PUBLIC_SITE_DIR}/package.json" >&2
  exit 1
fi

pushd "${PUBLIC_SITE_DIR}" >/dev/null

npm ci
NEXT_PUBLIC_APP_URL="${APP_URL}" npm run build

popd >/dev/null

if [[ ! -d "${OUT_DIR}" ]]; then
  echo "ERROR: next export output not found: ${OUT_DIR}" >&2
  exit 1
fi

rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}"
cp -R "${OUT_DIR}/." "${DIST_DIR}/"

echo "Public site built: ${DIST_DIR}"
echo "App URL wired to: ${APP_URL}"
