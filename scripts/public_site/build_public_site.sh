#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="${ROOT_DIR}/public-site/src"
DIST_DIR="${ROOT_DIR}/public-site/dist"
APP_URL="${PUBLIC_SITE_APP_URL:-https://app.sparkpilot.cloud}"

if [[ ! -d "${SRC_DIR}" ]]; then
  echo "ERROR: public-site source directory not found: ${SRC_DIR}" >&2
  exit 1
fi

rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}"
cp -R "${SRC_DIR}/." "${DIST_DIR}/"

while IFS= read -r -d '' html_file; do
  tmp_file="${html_file}.tmp"
  sed "s|__APP_URL__|${APP_URL}|g" "${html_file}" > "${tmp_file}"
  mv "${tmp_file}" "${html_file}"
done < <(find "${DIST_DIR}" -type f -name '*.html' -print0)

echo "Public site built: ${DIST_DIR}"
echo "App URL wired to: ${APP_URL}"
