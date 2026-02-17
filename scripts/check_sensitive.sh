#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

echo "[security] checking tracked env files..."
tracked_env_files="$(git ls-files | rg '^\.env($|\.)' | rg -v '\.example$' || true)"
if [ -n "$tracked_env_files" ]; then
  echo "[security][ERROR] .env files are tracked by git. Keep only *.example files tracked."
  printf '%s\n' "$tracked_env_files"
  exit 1
fi

echo "[security] checking tracked files for common secret patterns..."
if git ls-files | xargs rg -n \
  -e 'AKIA[0-9A-Z]{16}' \
  -e 'BEGIN [A-Z ]*PRIVATE KEY' \
  -e 'ghp_[A-Za-z0-9]{20,}' \
  -e 'xox[baprs]-[A-Za-z0-9-]+' \
  -e 'sk_live_[A-Za-z0-9]+' \
  -e 'AIza[0-9A-Za-z\-_]{35}' \
  >/tmp/sausalito_sensitive_scan.out 2>/dev/null; then
  echo "[security][ERROR] possible secret detected:"
  cat /tmp/sausalito_sensitive_scan.out
  exit 1
fi

echo "[security] OK - no obvious tracked secrets detected."
