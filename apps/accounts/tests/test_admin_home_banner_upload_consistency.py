from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User

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


class AdminHomeBannerUploadConsistencyTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.super_admin = User.objects.create_user(
            email="super-admin-banner@test.local",
            password="pass1234",
            is_staff=True,
            is_superuser=True,
            admin_role=User.AdminRole.SUPER_ADMIN,
            name="슈퍼관리자",
        )
        self.client.force_authenticate(user=self.super_admin)

    def test_admin_banner_upload_is_visible_in_public_home_banner_api(self):
        create_response = self.client.post(
            "/api/v1/admin/banners/home/manage",
            {
                "title": "관리자 업로드 배너",
                "subtitle": "admin",
                "description": "admin",
                "cta_text": "보러가기",
                "link_url": "/",
                "sort_order": "0",
                "is_active": "true",
                "image": SimpleUploadedFile("admin-upload.gif", ONE_BY_ONE_GIF, content_type="image/gif"),
            },
        )
        self.assertEqual(create_response.status_code, 201)
        banner_id = create_response.data["data"]["id"]
        image_url = create_response.data["data"]["image_url"]
        self.assertTrue(image_url)

        public_response = self.client.get("/api/v1/banners/home")
        self.assertEqual(public_response.status_code, 200)
        public_rows = public_response.data["data"]
        row = next((item for item in public_rows if item["id"] == banner_id), None)
        self.assertIsNotNone(row)
        self.assertTrue(row["image"])
