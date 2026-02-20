from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import BrandStorySection

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


class AdminBrandPageManagementTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.super_admin = User.objects.create_user(
            email="super-admin@test.local",
            password="pass1234",
            is_staff=True,
            is_superuser=True,
            admin_role=User.AdminRole.SUPER_ADMIN,
            name="슈퍼관리자",
        )
        self.ops_admin = User.objects.create_user(
            email="ops-admin@test.local",
            password="pass1234",
            is_staff=True,
            admin_role=User.AdminRole.OPS,
            name="운영관리자",
        )

    def test_super_admin_can_manage_brand_page_and_sections(self):
        self.client.force_authenticate(user=self.super_admin)

        update_response = self.client.patch(
            "/api/v1/admin/brand/page",
            {
                "hero_eyebrow": "BRAND",
                "hero_title": "브랜드 소개",
                "hero_description": "브랜드 소개 본문",
            },
            format="json",
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data["data"]["hero_title"], "브랜드 소개")

        create_response = self.client.post(
            "/api/v1/admin/brand/sections",
            {
                "eyebrow": "01",
                "title": "첫 구획",
                "description": "첫 설명",
                "sort_order": "1",
                "is_active": "true",
                "image_alt": "첫 구획 이미지",
                "image": SimpleUploadedFile("brand-1.gif", ONE_BY_ONE_GIF, content_type="image/gif"),
            },
        )
        self.assertEqual(create_response.status_code, 201)
        section_id = create_response.data["data"]["id"]
        self.assertTrue(BrandStorySection.objects.filter(id=section_id).exists())

        list_response = self.client.get("/api/v1/admin/brand/sections")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data["data"]), 1)

    def test_ops_admin_cannot_access_brand_page_management(self):
        self.client.force_authenticate(user=self.ops_admin)

        response = self.client.get("/api/v1/admin/brand/page")
        self.assertEqual(response.status_code, 403)
