from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User


class UserWithdrawAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="withdraw-user@test.local",
            password="pass1234",
            name="탈퇴회원",
            phone="01033334444",
        )
        self.client.force_authenticate(user=self.user)

    def test_withdraw_requires_valid_password(self):
        response = self.client.post(
            "/api/v1/users/me/withdraw",
            {"password": "wrong-password"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_withdraw_deactivates_and_anonymizes_user(self):
        response = self.client.post(
            "/api/v1/users/me/withdraw",
            {"password": "pass1234", "reason": "서비스 미이용"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.user.has_usable_password())
        self.assertTrue(self.user.email.endswith("@withdrawn.local"))
        self.assertEqual(self.user.name, "")
        self.assertEqual(self.user.phone, "")
        self.assertEqual(self.user.kakao_sub, None)
