#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

echo "[storage-check] ensure db/redis are up (for consistent app startup)"
compose up -d --no-build db redis

echo "[storage-check] run django object storage smoke test"
compose run --rm --no-deps app_blue python manage.py check_object_storage

echo "[storage-check] completed"

