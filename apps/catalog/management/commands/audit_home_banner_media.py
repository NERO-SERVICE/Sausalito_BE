from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.common.media_utils import normalize_media_file_name, resolve_existing_storage_name
from apps.catalog.models import HomeBanner


class Command(BaseCommand):
    help = "Audit/clean HomeBanner media integrity (dangling DB refs + orphan files)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete-orphans",
            action="store_true",
            help="Delete files under MEDIA_ROOT/banners not referenced by HomeBanner rows.",
        )
        parser.add_argument(
            "--deactivate-dangling",
            action="store_true",
            help="Deactivate rows whose image path does not exist in current storage.",
        )
        parser.add_argument(
            "--clear-dangling-image",
            action="store_true",
            help="Clear image field for dangling rows (implies --deactivate-dangling).",
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        banner_root = media_root / "banners"
        if not banner_root.exists():
            self.stdout.write(self.style.WARNING(f"banner directory not found: {banner_root}"))
            return

        rows = list(HomeBanner.objects.order_by("id"))
        referenced_names = {
            normalize_media_file_name(row.image.name)
            for row in rows
            if getattr(row, "image", None) and getattr(row.image, "name", "")
        }

        dangling_rows: list[HomeBanner] = []
        for row in rows:
            image = getattr(row, "image", None)
            name = getattr(image, "name", "") if image else ""
            if not name:
                continue
            resolved = resolve_existing_storage_name(image)
            exists = bool(resolved and not str(resolved).startswith(("http://", "https://", "data:")))
            if not exists:
                dangling_rows.append(row)

        disk_files = [path for path in banner_root.rglob("*") if path.is_file()]
        disk_names = {
            str(path.relative_to(media_root)).replace("\\", "/")
            for path in disk_files
        }
        orphan_names = sorted(disk_names - referenced_names)

        self.stdout.write(self.style.SUCCESS("HomeBanner media audit"))
        self.stdout.write(f"- total rows: {len(rows)}")
        self.stdout.write(f"- referenced images: {len(referenced_names)}")
        self.stdout.write(f"- dangling rows: {len(dangling_rows)}")
        self.stdout.write(f"- orphan files: {len(orphan_names)}")

        if dangling_rows:
            self.stdout.write(self.style.WARNING("Dangling rows:"))
            for row in dangling_rows:
                self.stdout.write(f"  id={row.id} title={row.title} image={row.image.name}")

        if orphan_names:
            self.stdout.write(self.style.WARNING("Orphan files:"))
            for name in orphan_names[:100]:
                self.stdout.write(f"  {name}")
            if len(orphan_names) > 100:
                self.stdout.write(f"  ... and {len(orphan_names) - 100} more")

        if options["deactivate_dangling"] or options["clear_dangling_image"]:
            updated = 0
            clear_image = bool(options["clear_dangling_image"])
            for row in dangling_rows:
                fields = []
                if row.is_active:
                    row.is_active = False
                    fields.append("is_active")
                if clear_image and row.image:
                    row.image = None
                    fields.append("image")
                if fields:
                    row.save(update_fields=fields)
                    updated += 1
            self.stdout.write(self.style.SUCCESS(f"Updated dangling rows: {updated}"))

        if options["delete_orphans"]:
            deleted = 0
            for name in orphan_names:
                target = media_root / name
                if target.exists() and target.is_file():
                    target.unlink()
                    deleted += 1
            self.stdout.write(self.style.SUCCESS(f"Deleted orphan files: {deleted}"))
