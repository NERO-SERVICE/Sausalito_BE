#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

has_rg=false
if command -v rg >/dev/null 2>&1; then
  has_rg=true
fi

echo "[security] checking tracked env files..."
if [ "${has_rg}" = "true" ]; then
  tracked_env_files="$(git ls-files | rg '^\.env($|\.)' | rg -v '\.example$' || true)"
else
  tracked_env_files="$(git ls-files | grep -E '^\.env($|\.)' | grep -Ev '\.example$' || true)"
fi

if [ -n "$tracked_env_files" ]; then
  echo "[security][ERROR] .env files are tracked by git. Keep only *.example files tracked."
  printf '%s\n' "$tracked_env_files"
  exit 1
fi

echo "[security] checking tracked files for common secret patterns..."
if [ "${has_rg}" = "true" ]; then
  scanner_cmd=(xargs -0 rg -n
    -e 'AKIA[0-9A-Z]{16}'
    -e 'BEGIN [A-Z ]*PRIVATE KEY'
    -e 'ghp_[A-Za-z0-9]{20,}'
    -e 'xox[baprs]-[A-Za-z0-9-]+'
    -e 'sk_live_[A-Za-z0-9]+'
    -e 'AIza[0-9A-Za-z\-_]{35}'
    -e 'https?://[^/\s:@]+:[^/@\s]+@'
    -e 'KAKAO_REST_API_KEY\s*=\s*[0-9a-fA-F]{20,}'
    -e 'KAKAO_CLIENT_SECRET\s*=\s*[A-Za-z0-9]{16,}'
  )
else
  scanner_cmd=(xargs -0 grep -nE
    'AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]+|sk_live_[A-Za-z0-9]+|AIza[0-9A-Za-z\-_]{35}|https?://[^/[:space:]:@]+:[^/@[:space:]]+@|KAKAO_REST_API_KEY[[:space:]]*=[[:space:]]*[0-9a-fA-F]{20,}|KAKAO_CLIENT_SECRET[[:space:]]*=[[:space:]]*[A-Za-z0-9]{16,}'
  )
fi

if git ls-files -z | "${scanner_cmd[@]}" >/tmp/sausalito_sensitive_scan.out 2>/dev/null; then
  echo "[security][ERROR] possible secret detected:"
  cat /tmp/sausalito_sensitive_scan.out
  exit 1
fi

echo "[security] OK - no obvious tracked secrets detected."
