from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(BASE_DIR / ".env")
_load_env_file(BASE_DIR / ".env.local")
# `.env.prod`는 로컬 개발 시 실수로 운영 리소스(DB/Object Storage)를
# 참조하지 않도록 기본적으로 자동 로드하지 않습니다.
# 필요 시 LOAD_ENV_PROD=true를 명시해 opt-in 하세요.
if str(os.environ.get("LOAD_ENV_PROD", "")).lower() in {"1", "true", "yes", "y", "on"}:
    _load_env_file(BASE_DIR / ".env.prod")


def env(key: str, default: Any = None) -> Any:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    raw = env(key)
    if raw is None:
        return default
    return str(raw).lower() in {"1", "true", "yes", "y", "on"}


def env_list(key: str, default: str = "") -> list[str]:
    raw = env(key, default)
    if not raw:
        return []
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def env_int(key: str, default: int) -> int:
    raw = env(key)
    if raw is None:
        return default
    return int(raw)


SECRET_KEY = env("DJANGO_SECRET_KEY", "unsafe-local-secret-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
PUBLIC_BACKEND_ORIGIN = env("PUBLIC_BACKEND_ORIGIN", "").strip().rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "apps.common",
    "apps.accounts",
    "apps.catalog",
    "apps.reviews",
    "apps.cart",
    "apps.orders",
    "apps.payments",
]

USE_S3_MEDIA = env_bool("USE_S3_MEDIA", False)
if USE_S3_MEDIA:
    INSTALLED_APPS.append("storages")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if env("DB_ENGINE", "sqlite3") == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "sausalito"),
            "USER": env("DB_USER", "sausalito"),
            "PASSWORD": env("DB_PASSWORD", "sausalito"),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

USE_REDIS_CACHE = env_bool("USE_REDIS_CACHE", False)
CACHE_DEFAULT_TTL = env_int("CACHE_DEFAULT_TTL", 300)
REDIS_CACHE_URL = env("REDIS_CACHE_URL", "redis://redis:6379/1")
REDIS_SESSION_URL = env("REDIS_SESSION_URL", "redis://redis:6379/2")

if USE_REDIS_CACHE:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_CACHE_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": False,
            },
            "TIMEOUT": CACHE_DEFAULT_TTL,
        },
        "session": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_SESSION_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": False,
            },
            "TIMEOUT": env_int("SESSION_CACHE_TTL", 60 * 60 * 24 * 14),
        },
    }
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "session"
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "sausalito-local-cache",
            "TIMEOUT": CACHE_DEFAULT_TTL,
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

if USE_S3_MEDIA:
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", "")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", "")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", "")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", "")
    AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", "")
    AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", "auto")
    AWS_QUERYSTRING_AUTH = env_bool("AWS_QUERYSTRING_AUTH", False)
    AWS_S3_MEDIA_PREFIX = env("AWS_S3_MEDIA_PREFIX", "media").strip("/")
    AWS_S3_MEDIA_CACHE_CONTROL = env(
        "AWS_S3_MEDIA_CACHE_CONTROL", "public, max-age=31536000, immutable"
    ).strip()
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False

    _media_domain = AWS_S3_CUSTOM_DOMAIN
    if _media_domain:
        MEDIA_URL = f"https://{_media_domain.rstrip('/')}/{AWS_S3_MEDIA_PREFIX}/"
    elif AWS_S3_ENDPOINT_URL:
        MEDIA_URL = (
            f"{AWS_S3_ENDPOINT_URL.rstrip('/')}/{AWS_STORAGE_BUCKET_NAME}/{AWS_S3_MEDIA_PREFIX}/"
        )
    elif AWS_S3_REGION_NAME and AWS_STORAGE_BUCKET_NAME:
        MEDIA_URL = (
            f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"
            f"{AWS_S3_MEDIA_PREFIX}/"
        )

    _s3_object_parameters = {}
    if AWS_S3_MEDIA_CACHE_CONTROL:
        _s3_object_parameters["CacheControl"] = AWS_S3_MEDIA_CACHE_CONTROL

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "location": AWS_S3_MEDIA_PREFIX,
                "object_parameters": _s3_object_parameters,
            },
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.AllowAny",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 12,
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Sausalito API",
    "DESCRIPTION": "Sausalito 쇼핑몰 백엔드 API",
    "VERSION": "1.0.0",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

LOCAL_FRONTEND_ORIGINS_DEFAULT = (
    "http://127.0.0.1:5173,"
    "http://localhost:5173,"
    "http://127.0.0.1:5174,"
    "http://localhost:5174,"
    "http://127.0.0.1:4173,"
    "http://localhost:4173,"
    "http://127.0.0.1:4174,"
    "http://localhost:4174"
)

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", LOCAL_FRONTEND_ORIGINS_DEFAULT)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", LOCAL_FRONTEND_ORIGINS_DEFAULT)
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 24 * 14)

FREE_SHIPPING_THRESHOLD = int(env("FREE_SHIPPING_THRESHOLD", "30000"))
DEFAULT_SHIPPING_FEE = int(env("DEFAULT_SHIPPING_FEE", "3000"))
MAX_REVIEW_IMAGES = int(env("MAX_REVIEW_IMAGES", "3"))
MAX_REVIEW_IMAGE_SIZE_MB = int(env("MAX_REVIEW_IMAGE_SIZE_MB", "10"))
MAX_UPLOAD_IMAGE_SIZE_MB = int(env("MAX_UPLOAD_IMAGE_SIZE_MB", "10"))
MAX_MULTIPART_BODY_MB = int(env("MAX_MULTIPART_BODY_MB", "50"))
PRESIGNED_UPLOAD_EXPIRES_IN = env_int("PRESIGNED_UPLOAD_EXPIRES_IN", 300)
PRESIGNED_UPLOAD_MAX_BYTES = env_int("PRESIGNED_UPLOAD_MAX_BYTES", 10 * 1024 * 1024)
PRESIGNED_UPLOAD_PREFIX = env("PRESIGNED_UPLOAD_PREFIX", "uploads").strip("/")
PRESIGNED_ALLOWED_CONTENT_PREFIXES = env_list(
    "PRESIGNED_ALLOWED_CONTENT_PREFIXES", "image/"
)

STORE_BUSINESS_NAME = env("STORE_BUSINESS_NAME", "주식회사 네로")
STORE_CEO_NAME = env("STORE_CEO_NAME", "한동균, 박호연")
STORE_BUSINESS_NO = env("STORE_BUSINESS_NO", "123-45-67890")
STORE_ECOMMERCE_NO = env("STORE_ECOMMERCE_NO", "2026-서울마포-0001")
STORE_BUSINESS_ADDRESS = env("STORE_BUSINESS_ADDRESS", "서울특별시 중구 퇴계로36길 2")
STORE_SUPPORT_PHONE = env("STORE_SUPPORT_PHONE", "1588-1234")
STORE_SUPPORT_EMAIL = env("STORE_SUPPORT_EMAIL", "cs@nero.ai.kr")
STORE_SUPPORT_HOURS = env("STORE_SUPPORT_HOURS", "평일 10:00 - 18:00 / 점심 12:30 - 13:30")
STORE_RETURN_ADDRESS = env("STORE_RETURN_ADDRESS", "서울특별시 중구 퇴계로36길 2 물류센터")
STORE_RETURN_SHIPPING_FEE = int(env("STORE_RETURN_SHIPPING_FEE", "3000"))
STORE_EXCHANGE_SHIPPING_FEE = int(env("STORE_EXCHANGE_SHIPPING_FEE", "6000"))

# 리뷰 이미지 다중 업로드(최대 3장)를 안정적으로 처리하기 위한 요청 본문 허용치
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_MULTIPART_BODY_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_MULTIPART_BODY_MB * 1024 * 1024

KAKAO_REST_API_KEY = env("KAKAO_REST_API_KEY", "")
KAKAO_CLIENT_SECRET = env("KAKAO_CLIENT_SECRET", "")
KAKAO_REDIRECT_URI = env("KAKAO_REDIRECT_URI", "")
KAKAO_ALLOWED_REDIRECT_URIS = env_list("KAKAO_ALLOWED_REDIRECT_URIS", "")
KAKAO_INCLUDE_EMAIL_SCOPE = env_bool("KAKAO_INCLUDE_EMAIL_SCOPE", False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": env("LOG_LEVEL", "INFO"),
    },
}
