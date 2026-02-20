from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Address, User


class UserDefaultAddressAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="address-user@test.local",
            password="pass1234!",
            name="주소유저",
            phone="01012345678",
        )
        self.client.force_authenticate(user=self.user)

    def test_get_returns_default_address(self):
        Address.objects.create(
            user=self.user,
            recipient="기존 기본주소",
            phone="01012345678",
            postal_code="04524",
            road_address="서울특별시 중구 세종대로 110",
            detail_address="101호",
            is_default=True,
        )
        Address.objects.create(
            user=self.user,
            recipient="보조 주소",
            phone="01000000000",
            postal_code="03000",
            road_address="서울특별시 종로구 청와대로 1",
            detail_address="",
            is_default=False,
        )

        response = self.client.get("/api/v1/users/me/default-address")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get("success"))
        data = response.data.get("data", {})
        self.assertEqual(data.get("recipient"), "기존 기본주소")
        self.assertEqual(data.get("postal_code"), "04524")
        self.assertTrue(data.get("is_default"))

    def test_get_normalizes_legacy_data_without_default_flag(self):
        address = Address.objects.create(
            user=self.user,
            recipient="기본지정안됨",
            phone="01012345678",
            postal_code="04524",
            road_address="서울특별시 중구 세종대로 110",
            detail_address="101호",
            is_default=False,
        )

        response = self.client.get("/api/v1/users/me/default-address")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get("success"))

        address.refresh_from_db()
        self.assertTrue(address.is_default)
