#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env.prod}"
CERT_NAME="${LETSENCRYPT_CERT_NAME:-sausalito}"

if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

: "${LETSENCRYPT_EMAIL:?LETSENCRYPT_EMAIL is required.}"
: "${LETSENCRYPT_DOMAINS:?LETSENCRYPT_DOMAINS is required (comma-separated).}"

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

domain_args=()
IFS=',' read -ra domains <<<"${LETSENCRYPT_DOMAINS}"
for raw_domain in "${domains[@]}"; do
  domain="$(echo "${raw_domain}" | xargs)"
  if [ -n "${domain}" ]; then
    domain_args+=("-d" "${domain}")
  fi
done

if [ "${#domain_args[@]}" -eq 0 ]; then
  echo "[ssl][ERROR] no valid domains parsed from LETSENCRYPT_DOMAINS."
  exit 1
fi

echo "[ssl] Starting stack in HTTP mode for ACME challenge..."
compose up -d --no-build db redis app_blue app_green nginx

extra_args=()
if [ "${LETSENCRYPT_STAGING:-false}" = "true" ]; then
  extra_args+=("--staging")
fi

echo "[ssl] Requesting/renewing Let's Encrypt certificate (${CERT_NAME})..."
compose --profile tls run --rm certbot certonly \
  --webroot \
  -w /var/www/certbot \
  --email "${LETSENCRYPT_EMAIL}" \
  --agree-tos \
  --no-eff-email \
  --rsa-key-size 4096 \
  --non-interactive \
  --cert-name "${CERT_NAME}" \
  "${extra_args[@]}" \
  "${domain_args[@]}"

"${ROOT_DIR}/scripts/ssl/enable_https_conf.sh"

echo "[ssl] Reloading nginx with HTTPS config..."
compose exec -T nginx nginx -s reload

echo "[ssl] Bootstrap completed. HTTPS is now enabled."
