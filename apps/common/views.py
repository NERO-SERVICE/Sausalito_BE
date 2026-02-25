from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.core.cache import caches
from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.views import APIView

from .response import error_response, success_response


def healthz(_request):
    database_ok = True
    cache_ok = True

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except OperationalError:
        database_ok = False

    if getattr(settings, "USE_REDIS_CACHE", False):
        try:
            cache = caches["default"]
            cache.set("healthz:cache", "ok", timeout=5)
            cache_ok = cache.get("healthz:cache") == "ok"
        except Exception:
            cache_ok = False

    checks = {
        "database": "ok" if database_ok else "error",
        "cache": "ok" if cache_ok else "error",
    }

    status_code = 200 if all(v == "ok" for v in checks.values()) else 503
    return JsonResponse(
        {
            "status": "ok" if status_code == 200 else "degraded",
            "timestamp": timezone.now().isoformat(),
            "checks": checks,
        },
        status=status_code,
    )


class PresignedUploadRequestSerializer(serializers.Serializer):
    file_name = serializers.CharField(max_length=255)
    content_type = serializers.CharField(max_length=100)

    def validate_file_name(self, value: str) -> str:
        safe_name = Path(value).name.strip()
        if safe_name in {"", ".", ".."}:
            raise serializers.ValidationError("유효한 파일 이름이 필요합니다.")
        return safe_name


class PresignedUploadAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if not getattr(settings, "USE_S3_MEDIA", False):
            return error_response(
                code="OBJECT_STORAGE_DISABLED",
                message="현재 환경에서 object storage가 비활성화되어 있습니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PresignedUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_name = serializer.validated_data["file_name"]
        content_type = serializer.validated_data["content_type"].strip().lower()
        allowed_prefixes = getattr(settings, "PRESIGNED_ALLOWED_CONTENT_PREFIXES", ["image/"])
        if not any(content_type.startswith(prefix) for prefix in allowed_prefixes):
            return error_response(
                code="UNSUPPORTED_CONTENT_TYPE",
                message="허용되지 않은 파일 형식입니다.",
                details={"allowed_prefixes": allowed_prefixes},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        media_prefix = str(getattr(settings, "AWS_S3_MEDIA_PREFIX", "media")).strip("/")
        upload_prefix = str(getattr(settings, "PRESIGNED_UPLOAD_PREFIX", "uploads")).strip("/")
        object_key = "/".join(
            [
                part
                for part in [
                    media_prefix,
                    upload_prefix,
                    str(request.user.id),
                    f"{uuid.uuid4().hex}_{file_name}",
                ]
                if part
            ]
        )

        expires_in = int(getattr(settings, "PRESIGNED_UPLOAD_EXPIRES_IN", 300))
        max_bytes = int(getattr(settings, "PRESIGNED_UPLOAD_MAX_BYTES", 10 * 1024 * 1024))

        try:
            import boto3

            client_kwargs = {"service_name": "s3"}
            if getattr(settings, "AWS_S3_REGION_NAME", ""):
                client_kwargs["region_name"] = settings.AWS_S3_REGION_NAME
            if getattr(settings, "AWS_S3_ENDPOINT_URL", ""):
                client_kwargs["endpoint_url"] = settings.AWS_S3_ENDPOINT_URL
            if getattr(settings, "AWS_ACCESS_KEY_ID", ""):
                client_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            if getattr(settings, "AWS_SECRET_ACCESS_KEY", ""):
                client_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

            s3_client = boto3.client(**client_kwargs)
            presigned = s3_client.generate_presigned_post(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=object_key,
                Fields={"Content-Type": content_type},
                Conditions=[
                    {"Content-Type": content_type},
                    ["content-length-range", 1, max_bytes],
                ],
                ExpiresIn=expires_in,
            )
        except Exception as exc:
            return error_response(
                code="PRESIGNED_UPLOAD_FAILED",
                message="Presigned 업로드 URL 생성에 실패했습니다.",
                details={"reason": str(exc)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        relative_key = object_key
        if media_prefix and object_key.startswith(f"{media_prefix}/"):
            relative_key = object_key[len(media_prefix) + 1 :]

        media_url = str(settings.MEDIA_URL).rstrip("/")
        file_url = f"{media_url}/{relative_key}" if media_url else relative_key

        return success_response(
            data={
                "upload": presigned,
                "object_key": object_key,
                "file_url": file_url,
                "expires_in": expires_in,
                "max_bytes": max_bytes,
            },
            message="Presigned upload URL generated.",
            status_code=status.HTTP_201_CREATED,
        )
