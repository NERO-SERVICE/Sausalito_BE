#!/usr/bin/env bash
set -euo pipefail

PRUNE_UNTIL="${PRUNE_UNTIL:-168h}" # default: keep last 7 days

echo "[disk] Before prune:"
docker system df || true

echo "[disk] Pruning stopped containers/images/networks older than ${PRUNE_UNTIL}..."
docker system prune -af --filter "until=${PRUNE_UNTIL}"

echo "[disk] Pruning build cache older than ${PRUNE_UNTIL}..."
docker builder prune -af --filter "until=${PRUNE_UNTIL}"

echo "[disk] After prune:"
docker system df || true
