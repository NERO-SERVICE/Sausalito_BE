#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

export IMAGE_TAG

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

health_check() {
  local retries=30
  local wait_seconds=3
  local i
  local status_code

  for ((i = 1; i <= retries; i += 1)); do
    status_code="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1/healthz" || true)"
    if [ "${status_code}" = "200" ]; then
      return 0
    fi
    echo "[deploy] health check attempt ${i}/${retries}: status=${status_code}"
    sleep "${wait_seconds}"
  done

  echo "[deploy][ERROR] health check failed after ${retries} retries."
  return 1
}

echo "[deploy] Pull latest images (tag: ${IMAGE_TAG})"
compose pull db redis app_blue app_green nginx

echo "[deploy] Verify backend image exists locally"
if ! docker image inspect "${BACKEND_IMAGE:-ghcr.io/nero-service/sausalito-be}:${IMAGE_TAG}" >/dev/null 2>&1; then
  echo "[deploy][ERROR] backend image not found after pull: ${BACKEND_IMAGE:-ghcr.io/nero-service/sausalito-be}:${IMAGE_TAG}"
  echo "[deploy][ERROR] Check GHCR login and image tag."
  exit 1
fi

echo "[deploy] Ensure database and redis are up"
compose up -d --no-build db redis

echo "[deploy] Run migrations"
compose run --rm --no-deps app_blue python manage.py migrate --noinput

echo "[deploy] Collect static files"
compose run --rm --no-deps app_blue python manage.py collectstatic --noinput

echo "[deploy] Start app pools and nginx"
compose up -d --no-build nginx app_blue app_green
compose exec -T nginx nginx -s reload
health_check

echo "[deploy] Deployment completed successfully."
