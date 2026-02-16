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


SECRET_KEY = env("DJANGO_SECRET_KEY", "unsafe-local-secret-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

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

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
)

FREE_SHIPPING_THRESHOLD = int(env("FREE_SHIPPING_THRESHOLD", "30000"))
DEFAULT_SHIPPING_FEE = int(env("DEFAULT_SHIPPING_FEE", "3000"))
MAX_REVIEW_IMAGES = int(env("MAX_REVIEW_IMAGES", "3"))
MAX_REVIEW_IMAGE_SIZE_MB = int(env("MAX_REVIEW_IMAGE_SIZE_MB", "10"))

KAKAO_REST_API_KEY = env("KAKAO_REST_API_KEY", "")
KAKAO_CLIENT_SECRET = env("KAKAO_CLIENT_SECRET", "")
KAKAO_REDIRECT_URI = env("KAKAO_REDIRECT_URI", "")
KAKAO_ALLOWED_REDIRECT_URIS = env_list("KAKAO_ALLOWED_REDIRECT_URIS", "")

NAVERPAY_MERCHANT_ID = env("NAVERPAY_MERCHANT_ID", "")
NAVERPAY_API_SECRET = env("NAVERPAY_API_SECRET", "")
NAVERPAY_WEBHOOK_SECRET = env("NAVERPAY_WEBHOOK_SECRET", "")

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
