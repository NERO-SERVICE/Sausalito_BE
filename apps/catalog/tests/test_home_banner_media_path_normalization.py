from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

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


class HomeBannerMediaPathNormalizationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_home_banner_api_handles_media_prefixed_db_name(self):
        banner = HomeBanner.objects.create(
            title="경로정규화 배너",
            subtitle="path normalize",
            description="path normalize",
            cta_text="go",
            link_url="/",
            sort_order=1,
            is_active=True,
            image=SimpleUploadedFile("prefixed.gif", ONE_BY_ONE_GIF, content_type="image/gif"),
        )

        actual_name = banner.image.name
        HomeBanner.objects.filter(pk=banner.pk).update(image=f"media/{actual_name}")

        response = self.client.get("/api/v1/banners/home")
        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        row = next((item for item in rows if item["id"] == banner.id), None)
        self.assertIsNotNone(row)
        self.assertIn(f"/media/{actual_name}", row["image"])
        self.assertNotIn("/media/media/", row["image"])

    def test_home_banner_api_accepts_external_image_url_in_db(self):
        external = "https://cdn.example.com/banners/external-banner.png"
        banner = HomeBanner.objects.create(
            title="외부URL 배너",
            subtitle="external",
            description="external",
            cta_text="go",
            link_url="/",
            sort_order=2,
            is_active=True,
        )
        HomeBanner.objects.filter(pk=banner.pk).update(image=external)

        response = self.client.get("/api/v1/banners/home")
        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        row = next((item for item in rows if item["id"] == banner.id), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["image"], external)
