#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE_PATH="${ROOT_DIR}/nginx/conf.d/10-https.conf.template"
TARGET_PATH="${ROOT_DIR}/nginx/conf.d/10-https.conf"

if [ ! -f "${TEMPLATE_PATH}" ]; then
  echo "[ssl][ERROR] HTTPS nginx template not found: ${TEMPLATE_PATH}"
  exit 1
fi

cp "${TEMPLATE_PATH}" "${TARGET_PATH}"
echo "[ssl] HTTPS nginx config enabled: ${TARGET_PATH}"
