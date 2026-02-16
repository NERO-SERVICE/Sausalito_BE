from __future__ import annotations

from django.core.files.images import get_image_dimensions
from django.core.management.base import BaseCommand

from apps.catalog.models import HomeBanner, ProductDetailImage, ProductImage
from apps.reviews.models import ReviewImage


def is_tiny_image(field_file) -> bool:
    if not field_file or not getattr(field_file, "name", ""):
        return False
    try:
        width, height = get_image_dimensions(field_file)
    except Exception:
        return False
    if width is None or height is None:
        return False
    return width <= 1 and height <= 1


class Command(BaseCommand):
    help = "Remove legacy tiny dummy images (1x1) from DB and media files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="삭제하지 않고 대상만 출력합니다.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        counts = {
            "product_images_removed": 0,
            "product_detail_images_removed": 0,
            "review_images_removed": 0,
            "home_banners_cleared": 0,
        }

        for row in ProductImage.objects.exclude(image__isnull=True).exclude(image="").order_by("id"):
            if not is_tiny_image(row.image):
                continue
            counts["product_images_removed"] += 1
            self.stdout.write(f"[ProductImage] id={row.id} {row.image.name}")
            if dry_run:
                continue
            row.image.delete(save=False)
            row.delete()

        for row in ProductDetailImage.objects.exclude(image__isnull=True).exclude(image="").order_by("id"):
            if not is_tiny_image(row.image):
                continue
            counts["product_detail_images_removed"] += 1
            self.stdout.write(f"[ProductDetailImage] id={row.id} {row.image.name}")
            if dry_run:
                continue
            row.image.delete(save=False)
            row.delete()

        for row in ReviewImage.objects.exclude(image__isnull=True).exclude(image="").order_by("id"):
            if not is_tiny_image(row.image):
                continue
            counts["review_images_removed"] += 1
            self.stdout.write(f"[ReviewImage] id={row.id} {row.image.name}")
            if dry_run:
                continue
            row.image.delete(save=False)
            row.delete()

        for banner in HomeBanner.objects.exclude(image__isnull=True).exclude(image="").order_by("id"):
            if not is_tiny_image(banner.image):
                continue
            counts["home_banners_cleared"] += 1
            self.stdout.write(f"[HomeBanner] id={banner.id} {banner.image.name}")
            if dry_run:
                continue
            banner.image.delete(save=False)
            banner.image = None
            banner.save(update_fields=["image"])

        self.stdout.write(self.style.SUCCESS("정리 완료"))
        for key, value in counts.items():
            self.stdout.write(f"- {key}: {value}")
