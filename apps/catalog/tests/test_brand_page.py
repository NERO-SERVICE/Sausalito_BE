from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.catalog.models import BrandPageSetting, BrandStorySection

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


class BrandPageAPIViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_brand_page_returns_server_managed_hero_and_active_sections(self):
        BrandPageSetting.objects.create(
            hero_eyebrow="BRAND STORY",
            hero_title="브랜드 소개 타이틀",
            hero_description="브랜드 소개 본문",
        )
        BrandStorySection.objects.create(
            eyebrow="02",
            title="두 번째 구획",
            description="두 번째 설명",
            sort_order=2,
            is_active=True,
            image=SimpleUploadedFile("brand-2.gif", ONE_BY_ONE_GIF, content_type="image/gif"),
        )
        BrandStorySection.objects.create(
            eyebrow="01",
            title="첫 번째 구획",
            description="첫 번째 설명",
            sort_order=1,
            is_active=True,
            image=SimpleUploadedFile("brand-1.gif", ONE_BY_ONE_GIF, content_type="image/gif"),
        )
        BrandStorySection.objects.create(
            eyebrow="03",
            title="비활성 구획",
            description="노출되지 않아야 함",
            sort_order=3,
            is_active=False,
            image=SimpleUploadedFile("brand-3.gif", ONE_BY_ONE_GIF, content_type="image/gif"),
        )

        response = self.client.get("/api/v1/brand/page")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["hero"]["hero_title"], "브랜드 소개 타이틀")

        sections = data["sections"]
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0]["title"], "첫 번째 구획")
        self.assertEqual(sections[1]["title"], "두 번째 구획")
        self.assertTrue(str(sections[0]["image"]).endswith(".gif"))
