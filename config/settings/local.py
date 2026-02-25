from .base import *  # noqa: F403,F401
from django.core.exceptions import ImproperlyConfigured
from urllib.parse import urlparse

DEBUG = True
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True

# 로컬 개발 기본값: 원격 DB/S3 접근 차단
# (필요 시 아래 opt-in 플래그로 명시 허용)
if env("DB_ENGINE", "sqlite3") == "postgresql":
    db_host = str(DATABASES["default"].get("HOST", "")).strip().lower()
    allow_remote_db = env_bool("ALLOW_REMOTE_DB_IN_LOCAL", False)
    if db_host not in {"", "127.0.0.1", "localhost", "db"} and not allow_remote_db:
        raise ImproperlyConfigured(
            "Local settings blocked remote DB host. "
            "Set ALLOW_REMOTE_DB_IN_LOCAL=true only when intentionally using remote DB."
        )

if USE_S3_MEDIA and not env_bool("ALLOW_S3_MEDIA_IN_LOCAL", False):
    raise ImproperlyConfigured(
        "Local settings blocked S3 media storage. "
        "Set ALLOW_S3_MEDIA_IN_LOCAL=true only when intentionally using remote object storage."
    )

if USE_REDIS_CACHE:
    parsed_redis = urlparse(REDIS_CACHE_URL)
    redis_host = (parsed_redis.hostname or "").strip().lower()
    allow_remote_redis = env_bool("ALLOW_REMOTE_REDIS_IN_LOCAL", False)
    if redis_host not in {"", "127.0.0.1", "localhost", "redis"} and not allow_remote_redis:
        raise ImproperlyConfigured(
            "Local settings blocked remote Redis host. "
            "Set ALLOW_REMOTE_REDIS_IN_LOCAL=true only when intentionally using remote Redis."
        )
