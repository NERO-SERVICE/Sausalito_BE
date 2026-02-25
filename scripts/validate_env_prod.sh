#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=".env.prod"
TEMPLATE_MODE="false"
FAIL_ON_LOCALHOST="false"

usage() {
  cat <<'USAGE'
Usage: ./scripts/validate_env_prod.sh [--file PATH] [--template] [--fail-on-localhost]

Options:
  --file PATH           Validate this env file (default: .env.prod)
  --template            Structure-only mode (allows placeholder values)
  --fail-on-localhost   Fail if localhost/127.0.0.1 is present in CORS/CSRF/ALLOWED_HOSTS
USAGE
}

while (($# > 0)); do
  case "$1" in
    --file)
      shift
      ENV_FILE="${1:-}"
      if [ -z "${ENV_FILE}" ]; then
        echo "[env-check][ERROR] --file requires a path."
        exit 1
      fi
      ;;
    --template)
      TEMPLATE_MODE="true"
      ;;
    --fail-on-localhost)
      FAIL_ON_LOCALHOST="true"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[env-check][ERROR] Unknown option: $1"
      usage
      exit 1
      ;;
  esac
  shift || true
done

if [ ! -f "${ENV_FILE}" ]; then
  echo "[env-check][ERROR] file not found: ${ENV_FILE}"
  exit 1
fi

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "${s}"
}

get_value() {
  local key="$1"
  local line value

  line="$(grep -E "^[[:space:]]*${key}=" "${ENV_FILE}" | tail -n1 || true)"
  if [ -z "${line}" ]; then
    return 1
  fi

  value="${line#*=}"
  value="$(trim "${value}")"

  case "${value}" in
    \"*\")
      value="${value#\"}"
      value="${value%\"}"
      ;;
    \'*\')
      value="${value#\'}"
      value="${value%\'}"
      ;;
  esac

  printf '%s' "${value}"
}

lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

required_keys=(
  DJANGO_SECRET_KEY
  DJANGO_ALLOWED_HOSTS
  PUBLIC_BACKEND_ORIGIN
  DB_ENGINE
  DB_HOST
  DB_PORT
  DB_NAME
  DB_USER
  DB_PASSWORD
  POSTGRES_DB
  POSTGRES_USER
  POSTGRES_PASSWORD
  USE_REDIS_CACHE
  REDIS_CACHE_URL
  REDIS_SESSION_URL
  CORS_ALLOWED_ORIGINS
  CSRF_TRUSTED_ORIGINS
  USE_S3_MEDIA
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_STORAGE_BUCKET_NAME
  AWS_S3_ENDPOINT_URL
  LETSENCRYPT_EMAIL
  LETSENCRYPT_DOMAINS
)

missing=()
for key in "${required_keys[@]}"; do
  val="$(get_value "${key}" || true)"
  if [ -z "${val}" ]; then
    missing+=("${key}")
  fi
done

if ((${#missing[@]} > 0)); then
  echo "[env-check][ERROR] missing required keys in ${ENV_FILE}:"
  printf '  - %s\n' "${missing[@]}"
  exit 1
fi

if [ "$(lower "$(get_value DB_ENGINE)")" != "postgresql" ]; then
  echo "[env-check][ERROR] DB_ENGINE must be 'postgresql' in production env."
  exit 1
fi

if [ "$(lower "$(get_value USE_REDIS_CACHE)")" != "true" ]; then
  echo "[env-check][ERROR] USE_REDIS_CACHE must be true."
  exit 1
fi

if [ "$(lower "$(get_value USE_S3_MEDIA)")" != "true" ]; then
  echo "[env-check][ERROR] USE_S3_MEDIA must be true."
  exit 1
fi

if [[ "$(get_value PUBLIC_BACKEND_ORIGIN)" != https://* ]]; then
  echo "[env-check][ERROR] PUBLIC_BACKEND_ORIGIN must start with https://"
  exit 1
fi

if [ "${TEMPLATE_MODE}" != "true" ]; then
  placeholder_failures=()
  placeholder_keys=(
    DJANGO_SECRET_KEY
    DB_PASSWORD
    POSTGRES_PASSWORD
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_STORAGE_BUCKET_NAME
    KAKAO_REST_API_KEY
    KAKAO_CLIENT_SECRET
  )

  for key in "${placeholder_keys[@]}"; do
    val="$(get_value "${key}" || true)"
    if [ -z "${val}" ]; then
      continue
    fi
    if [[ "${val}" == replace-with-* ]] || [[ "${val}" == *yourdomain* ]] || [[ "${val}" == *your-bucket* ]]; then
      placeholder_failures+=("${key}")
    fi
  done

  if ((${#placeholder_failures[@]} > 0)); then
    echo "[env-check][ERROR] placeholder values remain in ${ENV_FILE}:"
    printf '  - %s\n' "${placeholder_failures[@]}"
    exit 1
  fi
fi

kakao_rest="$(get_value KAKAO_REST_API_KEY || true)"
kakao_secret="$(get_value KAKAO_CLIENT_SECRET || true)"
kakao_redirect="$(get_value KAKAO_REDIRECT_URI || true)"

if [ -n "${kakao_rest}" ] || [ -n "${kakao_secret}" ] || [ -n "${kakao_redirect}" ]; then
  kakao_missing=()
  for key in KAKAO_REST_API_KEY KAKAO_CLIENT_SECRET KAKAO_REDIRECT_URI KAKAO_ALLOWED_REDIRECT_URIS; do
    val="$(get_value "${key}" || true)"
    if [ -z "${val}" ]; then
      kakao_missing+=("${key}")
    fi
  done
  if ((${#kakao_missing[@]} > 0)); then
    echo "[env-check][ERROR] Kakao config is partial. Fill all Kakao keys:"
    printf '  - %s\n' "${kakao_missing[@]}"
    exit 1
  fi
fi

localhost_pattern='localhost|127\.0\.0\.1'
localhost_hits=()
for key in DJANGO_ALLOWED_HOSTS CORS_ALLOWED_ORIGINS CSRF_TRUSTED_ORIGINS; do
  val="$(get_value "${key}" || true)"
  if printf '%s' "${val}" | grep -Eq "${localhost_pattern}"; then
    localhost_hits+=("${key}")
  fi
done

if ((${#localhost_hits[@]} > 0)); then
  if [ "${FAIL_ON_LOCALHOST}" = "true" ]; then
    echo "[env-check][ERROR] localhost entries found:"
    printf '  - %s\n' "${localhost_hits[@]}"
    echo "Set FE production domains only, then rerun."
    exit 1
  fi
  echo "[env-check][WARN] localhost entries currently included:"
  printf '  - %s\n' "${localhost_hits[@]}"
  echo "[env-check][WARN] allowed for pre-deploy local verification."
fi

echo "[env-check] OK: ${ENV_FILE}"
