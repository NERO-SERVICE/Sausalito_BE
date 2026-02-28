#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SYSTEMD_DIR="/etc/systemd/system"

if [ "$(id -u)" -ne 0 ]; then
  echo "[systemd][ERROR] run as root. Example: sudo ./scripts/systemd/install_runtime_automation.sh"
  exit 1
fi

install_unit() {
  local filename="$1"
  install -m 0644 "${ROOT_DIR}/scripts/systemd/${filename}" "${SYSTEMD_DIR}/${filename}"
}

echo "[systemd] installing runtime automation units..."
install_unit "sausalito-certbot-renew.service"
install_unit "sausalito-certbot-renew.timer"
install_unit "sausalito-disk-guard.service"
install_unit "sausalito-disk-guard.timer"
install_unit "sausalito-runtime-guard.service"
install_unit "sausalito-runtime-guard.timer"
install_unit "sausalito-backup.service"
install_unit "sausalito-backup.timer"

systemctl daemon-reload

echo "[systemd] enabling timers..."
systemctl enable --now sausalito-certbot-renew.timer
systemctl enable --now sausalito-disk-guard.timer
systemctl enable --now sausalito-runtime-guard.timer
systemctl enable --now sausalito-backup.timer

echo "[systemd] active timers:"
systemctl list-timers --all | grep -E "sausalito-(certbot-renew|disk-guard|runtime-guard|backup)" || true

echo "[systemd] completed."
