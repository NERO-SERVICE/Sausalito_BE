from __future__ import annotations

import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run object storage smoke test (save/read/delete) for media backend."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prefix",
            default="_smoke",
            help="Storage key prefix used for test object.",
        )

    def handle(self, *args, **options):
        if not getattr(settings, "USE_S3_MEDIA", False):
            raise CommandError("USE_S3_MEDIA=false (object storage is disabled).")

        prefix = str(options["prefix"]).strip("/") or "_smoke"
        object_name = f"{prefix}/{uuid.uuid4().hex}.txt"
        payload = ContentFile(b"sausalito-storage-smoke-test")

        self.stdout.write(
            f"[storage-check] backend={default_storage.__class__.__name__} "
            f"bucket={getattr(settings, 'AWS_STORAGE_BUCKET_NAME', '') or '(empty)'} "
            f"endpoint={getattr(settings, 'AWS_S3_ENDPOINT_URL', '') or '(empty)'}"
        )
        self.stdout.write(f"[storage-check] write object: {object_name}")

        try:
            saved_name = default_storage.save(object_name, payload)
            exists_after_write = default_storage.exists(saved_name)
            _ = default_storage.url(saved_name)
            default_storage.delete(saved_name)
            exists_after_delete = default_storage.exists(saved_name)
        except Exception as exc:
            error_detail = str(exc)
            operation = str(getattr(exc, "operation_name", ""))
            error_code = ""
            error_message = ""
            try:
                response = getattr(exc, "response", None) or {}
                metadata = response.get("ResponseMetadata", {})
                if not operation:
                    operation = str(metadata.get("RequestId", ""))
                error = response.get("Error", {})
                error_code = str(error.get("Code", ""))
                error_message = str(error.get("Message", ""))
            except Exception:
                pass

            hint = (
                "Verify that AWS_ACCESS_KEY_ID maps to the intended service account, "
                "HMAC key state is ACTIVE, and the service account has "
                "Storage Object Admin on the target bucket (without restrictive IAM conditions)."
            )
            raise CommandError(
                "Object storage smoke test failed. "
                "Check AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, bucket permission, "
                "and GCS HMAC key status.\n"
                f"Error code: {error_code or '(unknown)'}\n"
                f"Error message: {error_message or '(none)'}\n"
                f"Operation hint: {operation or '(unknown)'}\n"
                f"Original error: {error_detail}\n"
                f"Hint: {hint}"
            ) from exc

        if not exists_after_write:
            raise CommandError("Object write appears to have failed (object not found after save).")
        if exists_after_delete:
            raise CommandError("Object delete appears to have failed (object still exists).")

        self.stdout.write(self.style.SUCCESS("[storage-check] OK"))
