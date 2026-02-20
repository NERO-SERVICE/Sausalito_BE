from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.common.file_utils import validate_image_file
from apps.catalog.models import HomeBanner

ONE_BY_ONE_GIF = (
    b"GIF89a"
    b"\x01\x00\x01\x00"
    b"\x80"
    b"\x00"
    b"\x00"
    b"\x00\x00\x00"
    b"\xff\xff\xff"
    b"!\xf9\x04\x01\x00\x00\x00\x00"
    b",\x00\x00\x00\x00\x01\x00\x01\x00\x00"
    b"\x02\x02D\x01\x00;"
)


class BannerGifSupportTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_validate_image_file_accepts_gif(self):
        image_file = SimpleUploadedFile("hero.gif", ONE_BY_ONE_GIF, content_type="image/gif")
        validate_image_file(image_file)

    def test_home_and_brand_banner_endpoints_expose_gif_images(self):
        HomeBanner.objects.create(
            title="GIF 배너",
            subtitle="움직이는 배너",
            description="GIF 테스트",
            cta_text="보러가기",
            sort_order=1,
            is_active=True,
            image=SimpleUploadedFile("home-banner.gif", ONE_BY_ONE_GIF, content_type="image/gif"),
        )
        HomeBanner.objects.create(
            title="보조 배너",
            subtitle="정적 배너",
            description="PNG 없이도 동작 확인",
            cta_text="더보기",
            sort_order=2,
            is_active=True,
            image=SimpleUploadedFile("sub-banner.gif", ONE_BY_ONE_GIF, content_type="image/gif"),
        )
        HomeBanner.objects.create(
            title="이미지 없는 배너",
            subtitle="fallback",
            description="브랜드 배너에서 제외",
            cta_text="N/A",
            sort_order=3,
            is_active=True,
        )

        home_response = self.client.get("/api/v1/banners/home")
        self.assertEqual(home_response.status_code, 200)
        home_rows = home_response.data["data"]
        self.assertGreaterEqual(len(home_rows), 2)
        self.assertTrue(any(str(row.get("image", "")).endswith(".gif") for row in home_rows))

        brand_response = self.client.get("/api/v1/banners/brand")
        self.assertEqual(brand_response.status_code, 200)
        brand_rows = brand_response.data["data"]
        self.assertLessEqual(len(brand_rows), 2)
        self.assertTrue(brand_rows)
        self.assertTrue(all(str(row.get("image", "")).endswith(".gif") for row in brand_rows))
