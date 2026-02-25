#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MOUNT_POINT="${DISK_GUARD_MOUNT_POINT:-/}"
THRESHOLD_PERCENT="${DISK_GUARD_THRESHOLD_PERCENT:-80}"

usage_percent="$(
  df -P "${MOUNT_POINT}" | awk 'NR==2 {gsub(/%/, "", $5); print $5}'
)"

echo "[disk] mount=${MOUNT_POINT} usage=${usage_percent}% threshold=${THRESHOLD_PERCENT}%"

if [ "${usage_percent}" -ge "${THRESHOLD_PERCENT}" ]; then
  echo "[disk] threshold exceeded. running docker prune..."
  "${ROOT_DIR}/scripts/maintenance/prune_docker.sh"
else
  echo "[disk] usage is healthy. prune skipped."
fi
