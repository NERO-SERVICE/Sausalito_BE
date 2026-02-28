#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
HEALTH_URL="${RUNTIME_GUARD_HEALTH_URL:-http://127.0.0.1/healthz}"
HEALTH_TIMEOUT="${RUNTIME_GUARD_HEALTH_TIMEOUT:-5}"
RECOVERY_WAIT_SECONDS="${RUNTIME_GUARD_RECOVERY_WAIT_SECONDS:-8}"

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

health_check() {
  curl -fsS --max-time "${HEALTH_TIMEOUT}" "${HEALTH_URL}" >/dev/null
}

echo "[runtime-guard] checking stack health: ${HEALTH_URL}"
if health_check; then
  echo "[runtime-guard] healthy"
  exit 0
fi

echo "[runtime-guard][WARN] health check failed. attempting self-heal..."
compose up -d --no-build db redis app_blue app_green nginx
sleep "${RECOVERY_WAIT_SECONDS}"

if health_check; then
  echo "[runtime-guard] recovered"
  exit 0
fi

echo "[runtime-guard][ERROR] recovery failed; manual check required."
exit 1
