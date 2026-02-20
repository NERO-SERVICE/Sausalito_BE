from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User


class UserMeProfileUpdateAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="profile-user@test.local",
            password="pass1234!",
            name="기존이름",
            phone="01011112222",
            sms_marketing_opt_in=False,
            email_marketing_opt_in=False,
        )
        self.client.force_authenticate(user=self.user)

    def test_patch_updates_profile_and_marketing_flags(self):
        response = self.client.patch(
            "/api/v1/users/me",
            {
                "name": "변경이름",
                "phone": "01000001111",
                "sms_marketing_opt_in": True,
                "email_marketing_opt_in": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get("success"))

        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "변경이름")
        self.assertEqual(self.user.phone, "01000001111")
        self.assertTrue(self.user.sms_marketing_opt_in)
        self.assertTrue(self.user.email_marketing_opt_in)

    def test_patch_updates_email(self):
        response = self.client.patch(
            "/api/v1/users/me",
            {
                "email": "updated-email@test.local",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get("success"))

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "updated-email@test.local")

    def test_patch_rejects_duplicate_email(self):
        User.objects.create_user(
            email="duplicate-email@test.local",
            password="pass1234!",
            name="다른회원",
            phone="01099998888",
        )

        response = self.client.patch(
            "/api/v1/users/me",
            {
                "email": "duplicate-email@test.local",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
