#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "[predeploy] 1) secret scan"
./scripts/check_sensitive.sh

echo "[predeploy] 2) env validation"
./scripts/validate_env_prod.sh --file .env.prod

echo "[predeploy] 3) compose validation"
docker compose config > /tmp/sausalito_be.predeploy.compose.yaml

echo "[predeploy] 4) script syntax validation"
bash -n scripts/deploy_backend.sh
bash -n scripts/ssl/bootstrap_letsencrypt.sh
bash -n scripts/ssl/renew_letsencrypt.sh
bash -n scripts/ssl/enable_https_conf.sh
bash -n scripts/maintenance/prune_docker.sh
bash -n scripts/maintenance/cleanup_docker.sh
bash -n scripts/maintenance/disk_guard.sh
bash -n scripts/maintenance/backup_postgres_to_object_storage.sh
bash -n scripts/validate_env_prod.sh
bash -n scripts/check_object_storage.sh

if [ "${RUN_OBJECT_STORAGE_SMOKE_TEST:-false}" = "true" ]; then
  echo "[predeploy] 5) object storage smoke test"
  ./scripts/check_object_storage.sh
fi

echo "[predeploy] OK"
