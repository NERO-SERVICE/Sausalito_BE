#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

: "${DJANGO_SETTINGS_MODULE:=config.settings.prod}"
: "${WAIT_FOR_DB:=true}"
: "${WAIT_FOR_REDIS:=true}"
: "${DJANGO_MIGRATE_ON_START:=false}"
: "${DJANGO_COLLECTSTATIC_ON_START:=false}"

export DJANGO_SETTINGS_MODULE

if [ "${WAIT_FOR_DB}" = "true" ]; then
  python - <<'PY'
import os
import time

import psycopg

host = os.getenv("DB_HOST", "db")
port = int(os.getenv("DB_PORT", "5432"))
name = os.getenv("DB_NAME", "sausalito")
user = os.getenv("DB_USER", "sausalito")
password = os.getenv("DB_PASSWORD", "")

deadline = time.time() + 60
while True:
    try:
        with psycopg.connect(
            host=host,
            port=port,
            dbname=name,
            user=user,
            password=password,
            connect_timeout=3,
        ):
            break
    except Exception:
        if time.time() > deadline:
            raise
        time.sleep(2)
PY
fi

if [ "${WAIT_FOR_REDIS}" = "true" ] && [ "${USE_REDIS_CACHE:-false}" = "true" ]; then
  python - <<'PY'
import os
import time

import redis

redis_url = os.getenv("REDIS_CACHE_URL") or os.getenv("REDIS_URL") or "redis://redis:6379/1"
deadline = time.time() + 60

while True:
    try:
        client = redis.Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3)
        client.ping()
        break
    except Exception:
        if time.time() > deadline:
            raise
        time.sleep(2)
PY
fi

if [ "${DJANGO_MIGRATE_ON_START}" = "true" ]; then
  python manage.py migrate --noinput
fi

if [ "${DJANGO_COLLECTSTATIC_ON_START}" = "true" ]; then
  python manage.py collectstatic --noinput
fi

exec gunicorn config.wsgi:application --config /app/gunicorn.conf.py
