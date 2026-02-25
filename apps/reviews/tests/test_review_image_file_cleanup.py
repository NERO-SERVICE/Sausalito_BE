from __future__ import annotations

from pathlib import Path
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.catalog.models import Product
from apps.reviews.models import Review, ReviewImage

User = get_user_model()


class ReviewImageFileCleanupTest(TestCase):
    def setUp(self):
        super().setUp()
        self._temp_dir = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._temp_dir.name)
        self._override.enable()

        self.user = User.objects.create_user(email="cleanup-review@test.local", password="pass1234")
        self.product = Product.objects.create(
            name="리뷰 이미지 정리 상품",
            price=10000,
            original_price=12000,
            is_active=True,
        )

    def tearDown(self):
        self._override.disable()
        self._temp_dir.cleanup()
        super().tearDown()

    @staticmethod
    def _upload(filename: str) -> SimpleUploadedFile:
        return SimpleUploadedFile(filename, b"fake-image-content", content_type="image/png")

    def _create_review(self) -> Review:
        return Review.objects.create(
            product=self.product,
            user=self.user,
            score=5,
            content="좋아요",
            status=Review.Status.VISIBLE,
        )

    def test_deleting_review_image_row_deletes_file(self):
        review = self._create_review()
        image_row = ReviewImage.objects.create(review=review, image=self._upload("review_row_delete.png"), sort_order=0)
        absolute_path = Path(image_row.image.path)
        self.assertTrue(absolute_path.exists())

        with self.captureOnCommitCallbacks(execute=True):
            image_row.delete()

        self.assertFalse(absolute_path.exists())

    def test_deleting_review_cascade_deletes_related_review_images(self):
        review = self._create_review()
        image_row = ReviewImage.objects.create(review=review, image=self._upload("review_cascade.png"), sort_order=0)
        absolute_path = Path(image_row.image.path)
        self.assertTrue(absolute_path.exists())

        with self.captureOnCommitCallbacks(execute=True):
            review.delete()

        self.assertFalse(absolute_path.exists())
