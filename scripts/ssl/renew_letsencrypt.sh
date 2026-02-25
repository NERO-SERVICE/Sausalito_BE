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

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

echo "[ssl] Running certbot renew..."
compose --profile tls run --rm certbot renew --webroot -w /var/www/certbot --quiet

"${ROOT_DIR}/scripts/ssl/enable_https_conf.sh"

echo "[ssl] Reloading nginx to apply renewed certificates..."
compose exec -T nginx nginx -s reload

echo "[ssl] Renewal completed."
