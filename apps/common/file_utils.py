from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def validate_image_file(value) -> None:
    suffix = Path(value.name or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        raise ValidationError(f"지원하지 않는 이미지 형식입니다. 허용: {allowed}")

    max_size_mb = getattr(settings, "MAX_UPLOAD_IMAGE_SIZE_MB", 10)
    max_size = max_size_mb * 1024 * 1024
    if getattr(value, "size", 0) > max_size:
        raise ValidationError(f"이미지 파일은 {max_size_mb}MB 이하만 업로드 가능합니다.")


def _generate_upload_path(prefix: str, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        suffix = ".jpg"

    now = timezone.localtime()
    return f"{prefix}/{now:%Y/%m/%d}/{uuid.uuid4().hex}{suffix}"


def product_image_upload_to(instance, filename: str) -> str:
    return _generate_upload_path("products", filename)


def product_detail_image_upload_to(instance, filename: str) -> str:
    return _generate_upload_path("product-details", filename)


def banner_image_upload_to(instance, filename: str) -> str:
    return _generate_upload_path("banners", filename)


def review_image_upload_to(instance, filename: str) -> str:
    return _generate_upload_path("reviews", filename)
