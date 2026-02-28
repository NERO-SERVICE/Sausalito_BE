from .base import *  # noqa: F403,F401
from django.core.exceptions import ImproperlyConfigured

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = env("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = env("CSRF_COOKIE_SAMESITE", "Lax")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"


def _derive_https_origins_from_allowed_hosts() -> list[str]:
    origins: list[str] = []
    for host in ALLOWED_HOSTS:
        safe_host = str(host or "").strip()
        if not safe_host or safe_host in {"*", "localhost", "127.0.0.1"}:
            continue
        if safe_host.startswith("."):
            safe_host = safe_host[1:]
        if not safe_host:
            continue
        origins.append(f"https://{safe_host}")
    return origins


if env_bool("AUTO_ADD_ALLOWED_HOSTS_TO_CSRF", True):
    merged = [*CSRF_TRUSTED_ORIGINS, *_derive_https_origins_from_allowed_hosts()]
    CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(merged))


def _ensure_secure_runtime() -> None:
    weak_secret_keys = {
        "",
        "unsafe-local-secret-key-change-me",
        "change-me-for-local",
        "replace-with-production-secret",
    }
    if SECRET_KEY in weak_secret_keys:
        raise ImproperlyConfigured(
            "Production SECRET_KEY is not configured. Set a strong DJANGO_SECRET_KEY."
        )

    weak_hosts = {"127.0.0.1", "localhost"}
    if not ALLOWED_HOSTS or all(host in weak_hosts for host in ALLOWED_HOSTS):
        raise ImproperlyConfigured(
            "Production ALLOWED_HOSTS is not configured. Set DJANGO_ALLOWED_HOSTS for real domains."
        )

    if not USE_REDIS_CACHE:
        raise ImproperlyConfigured(
            "Production must enable Redis cache/session. Set USE_REDIS_CACHE=true."
        )

    if not USE_S3_MEDIA:
        raise ImproperlyConfigured(
            "Production must use object storage for media. Set USE_S3_MEDIA=true."
        )

    if not AWS_STORAGE_BUCKET_NAME:
        raise ImproperlyConfigured(
            "Production object storage bucket is missing. Set AWS_STORAGE_BUCKET_NAME."
        )

    if not (AWS_S3_CUSTOM_DOMAIN or AWS_S3_ENDPOINT_URL or AWS_S3_REGION_NAME):
        raise ImproperlyConfigured(
            "Production object storage endpoint is ambiguous. "
            "Set AWS_S3_CUSTOM_DOMAIN or AWS_S3_ENDPOINT_URL or AWS_S3_REGION_NAME."
        )


_ensure_secure_runtime()
