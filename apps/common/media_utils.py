from __future__ import annotations

from urllib.parse import urljoin
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.storage import FileSystemStorage


def has_file_reference(field_file) -> bool:
    if not field_file:
        return False
    return bool(getattr(field_file, "name", ""))


def is_absolute_media_reference(value: str) -> bool:
    candidate = str(value or "").strip()
    return candidate.startswith(("http://", "https://", "data:"))


def normalize_media_file_name(value: str) -> str:
    source = str(value or "").strip().replace("\\", "/")
    if not source:
        return ""
    if is_absolute_media_reference(source):
        return source

    parsed_source = urlparse(source)
    if parsed_source.scheme and parsed_source.netloc:
        return source
    source = parsed_source.path or source

    media_url = str(getattr(settings, "MEDIA_URL", "/media/") or "/media/")
    media_path = urlparse(media_url).path or media_url
    media_prefix = media_path.strip("/")
    source = source.lstrip("/")
    if media_prefix and source.startswith(f"{media_prefix}/"):
        source = source[len(media_prefix) + 1 :]
    if source.startswith("media/"):
        source = source[len("media/") :]
    return source.lstrip("/")


def resolve_existing_storage_name(field_file) -> str:
    if not has_file_reference(field_file):
        return ""

    name = str(getattr(field_file, "name", "") or "").strip()
    if not name:
        return ""
    if is_absolute_media_reference(name):
        return name

    storage = getattr(field_file, "storage", None)
    if not isinstance(storage, FileSystemStorage):
        return normalize_media_file_name(name)

    normalized_name = normalize_media_file_name(name)
    candidates = []
    for candidate in (name, name.lstrip("/"), normalized_name):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        try:
            if storage.exists(candidate):
                return candidate
        except Exception:
            continue
    return normalized_name


def has_accessible_file_reference(field_file) -> bool:
    if not has_file_reference(field_file):
        return False

    name = str(getattr(field_file, "name", "") or "").strip()
    if is_absolute_media_reference(name):
        return True

    storage = getattr(field_file, "storage", None)
    if isinstance(storage, FileSystemStorage):
        resolved = resolve_existing_storage_name(field_file)
        return bool(resolved and not is_absolute_media_reference(resolved))

    return True


def _get_relative_media_url(name: str) -> str:
    media_url = str(getattr(settings, "MEDIA_URL", "/media/") or "/media/")
    parsed = urlparse(media_url)
    if parsed.scheme and parsed.netloc:
        base = media_url.rstrip("/") + "/"
        return urljoin(base, name.lstrip("/"))

    path = parsed.path or "/media/"
    if not path.startswith("/"):
        path = f"/{path}"
    base = path.rstrip("/") + "/"
    return urljoin(base, name.lstrip("/"))


def _resolve_forwarded_origin(request) -> str:
    if not request:
        return ""
    forwarded_host = str(request.META.get("HTTP_X_FORWARDED_HOST", "") or "").split(",")[0].strip()
    if not forwarded_host:
        return ""
    forwarded_proto = str(request.META.get("HTTP_X_FORWARDED_PROTO", "") or "").split(",")[0].strip().lower()
    if forwarded_proto not in {"http", "https"}:
        forwarded_proto = "https" if request.is_secure() else "http"
    return f"{forwarded_proto}://{forwarded_host}"


def build_public_file_url(field_file, *, request=None) -> str:
    if not has_file_reference(field_file):
        return ""

    name = str(getattr(field_file, "name", "") or "").strip()
    if is_absolute_media_reference(name):
        return name

    storage = getattr(field_file, "storage", None)
    raw_url = ""

    if isinstance(storage, FileSystemStorage):
        resolved_name = resolve_existing_storage_name(field_file)
        if not resolved_name:
            return ""
        if is_absolute_media_reference(resolved_name):
            return resolved_name
        raw_url = _get_relative_media_url(resolved_name)

    try:
        if not raw_url:
            raw_url = str(field_file.url or "")
    except Exception:
        raw_url = ""

    if not raw_url:
        normalized_name = normalize_media_file_name(name)
        if not normalized_name:
            return ""
        if is_absolute_media_reference(normalized_name):
            return normalized_name
        raw_url = _get_relative_media_url(normalized_name)

    if not raw_url:
        return ""

    if raw_url.startswith(("http://", "https://", "data:")):
        return raw_url

    public_origin = str(getattr(settings, "PUBLIC_BACKEND_ORIGIN", "") or "").strip().rstrip("/")
    if public_origin:
        return urljoin(f"{public_origin}/", raw_url.lstrip("/"))

    forwarded_origin = _resolve_forwarded_origin(request)
    if forwarded_origin:
        return urljoin(f"{forwarded_origin}/", raw_url.lstrip("/"))

    return raw_url
