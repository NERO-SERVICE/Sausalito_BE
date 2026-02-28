#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env.prod}"

if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [ -z "${BACKUP_S3_URI:-}" ]; then
  echo "[backup-guard] BACKUP_S3_URI not configured. backup skipped."
  exit 0
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "[backup-guard][WARN] aws CLI not installed. backup skipped."
  exit 0
fi

echo "[backup-guard] running postgres backup..."
"${ROOT_DIR}/scripts/maintenance/backup_postgres_to_object_storage.sh"
echo "[backup-guard] completed."
