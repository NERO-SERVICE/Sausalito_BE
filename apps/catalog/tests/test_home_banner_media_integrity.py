from __future__ import annotations

from pathlib import Path
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.catalog.models import HomeBanner, Product, ProductDetailImage, ProductDetailMeta, ProductImage


class HomeBannerMediaIntegrityTest(TestCase):
    def setUp(self):
        super().setUp()
        self._temp_dir = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._temp_dir.name)
        self._override.enable()

    def tearDown(self):
        self._override.disable()
        self._temp_dir.cleanup()
        super().tearDown()

    @staticmethod
    def _upload(filename: str) -> SimpleUploadedFile:
        return SimpleUploadedFile(filename, b"fake-image-content", content_type="image/png")

    def test_replacing_home_banner_image_deletes_old_file(self):
        banner = HomeBanner.objects.create(
            title="배너1",
            image=self._upload("first.png"),
            is_active=True,
        )
        old_relative_name = banner.image.name
        old_absolute_path = Path(banner.image.path)
        self.assertTrue(old_absolute_path.exists())

        with self.captureOnCommitCallbacks(execute=True):
            banner.image = self._upload("second.png")
            banner.save(update_fields=["image"])

        self.assertNotEqual(old_relative_name, banner.image.name)
        self.assertFalse((Path(self._temp_dir.name) / old_relative_name).exists())
        self.assertTrue(Path(banner.image.path).exists())

    def test_deleting_home_banner_deletes_attached_file(self):
        banner = HomeBanner.objects.create(
            title="배너2",
            image=self._upload("third.png"),
            is_active=True,
        )
        absolute_path = Path(banner.image.path)
        self.assertTrue(absolute_path.exists())

        with self.captureOnCommitCallbacks(execute=True):
            banner.delete()

        self.assertFalse(absolute_path.exists())

    def test_deleting_product_image_row_deletes_attached_file(self):
        product = Product.objects.create(
            name="이미지 테스트 상품",
            price=10000,
            original_price=12000,
            is_active=True,
        )
        image_row = ProductImage.objects.create(
            product=product,
            image=self._upload("product_row_delete.png"),
            sort_order=0,
            is_thumbnail=True,
        )
        absolute_path = Path(image_row.image.path)
        self.assertTrue(absolute_path.exists())

        with self.captureOnCommitCallbacks(execute=True):
            image_row.delete()

        self.assertFalse(absolute_path.exists())

    def test_deleting_product_cascade_deletes_related_detail_images(self):
        product = Product.objects.create(
            name="상세이미지 테스트 상품",
            price=15000,
            original_price=17000,
            is_active=True,
        )
        meta = ProductDetailMeta.objects.create(product=product)
        detail_image = ProductDetailImage.objects.create(
            detail_meta=meta,
            image=self._upload("product_detail_cascade.png"),
            sort_order=0,
        )
        absolute_path = Path(detail_image.image.path)
        self.assertTrue(absolute_path.exists())

        with self.captureOnCommitCallbacks(execute=True):
            product.delete()

        self.assertFalse(absolute_path.exists())
