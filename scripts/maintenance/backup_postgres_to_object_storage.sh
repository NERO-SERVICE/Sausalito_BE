#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env.prod}"

if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

: "${POSTGRES_DB:?POSTGRES_DB is required.}"
: "${POSTGRES_USER:?POSTGRES_USER is required.}"
: "${BACKUP_S3_URI:?BACKUP_S3_URI is required. Example: s3://my-bucket/sausalito-backups}"

if ! command -v aws >/dev/null 2>&1; then
  echo "[backup][ERROR] aws CLI is required on the host."
  exit 1
fi

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

timestamp="$(date +%Y%m%d_%H%M%S)"
target_uri="${BACKUP_S3_URI%/}/postgres_${POSTGRES_DB}_${timestamp}.sql.gz"

echo "[backup] streaming pg_dump directly to object storage: ${target_uri}"
compose exec -T db pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
  | gzip -9 \
  | aws s3 cp - "${target_uri}"

echo "[backup] completed successfully (no local backup file persisted)."
