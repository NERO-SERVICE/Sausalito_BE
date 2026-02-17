from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Address, User


class AuthSignupAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_creates_user_and_default_address(self):
        response = self.client.post(
            "/api/v1/auth/register",
            {
                "email": "new-user@test.local",
                "password": "newpass1234!",
                "password_confirm": "newpass1234!",
                "name": "신규회원",
                "phone": "01011112222",
                "recipient": "신규회원",
                "recipient_phone": "01011112222",
                "postal_code": "04524",
                "road_address": "서울특별시 중구 세종대로 110",
                "detail_address": "101호",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data.get("success"))
        self.assertIn("tokens", response.data.get("data", {}))
        self.assertIn("user", response.data.get("data", {}))

        user = User.objects.get(email="new-user@test.local")
        self.assertTrue(user.check_password("newpass1234!"))
        self.assertEqual(user.name, "신규회원")
        self.assertEqual(user.phone, "01011112222")

        address = Address.objects.get(user=user, is_default=True)
        self.assertEqual(address.recipient, "신규회원")
        self.assertEqual(address.phone, "01011112222")
        self.assertEqual(address.postal_code, "04524")

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(
            email="dup-user@test.local",
            password="pass1234!",
        )
        response = self.client.post(
            "/api/v1/auth/register",
            {
                "email": "dup-user@test.local",
                "password": "newpass1234!",
                "password_confirm": "newpass1234!",
                "name": "중복회원",
                "phone": "01000000000",
                "recipient": "중복회원",
                "postal_code": "12345",
                "road_address": "서울시 테스트로 1",
                "detail_address": "",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data.get("success"))

    @override_settings(
        KAKAO_REST_API_KEY="kakao-rest-key-test",
        KAKAO_REDIRECT_URI="http://127.0.0.1:5173/pages/kakao-callback.html",
        KAKAO_ALLOWED_REDIRECT_URIS=["http://127.0.0.1:5173/pages/kakao-callback.html"],
    )
    def test_kakao_authorize_url(self):
        response = self.client.get(
            "/api/v1/auth/kakao/authorize-url",
            {
                "redirect_uri": "http://127.0.0.1:5173/pages/kakao-callback.html",
                "state": "signup-state-123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get("success"))
        data = response.data.get("data", {})
        authorize_url = data.get("authorize_url", "")
        self.assertIn("https://kauth.kakao.com/oauth/authorize?", authorize_url)
        self.assertIn("client_id=kakao-rest-key-test", authorize_url)
        self.assertIn("response_type=code", authorize_url)
        self.assertIn("state=signup-state-123", authorize_url)

        parsed = urlparse(authorize_url)
        query = parse_qs(parsed.query)
        self.assertEqual(query.get("scope", [""])[0], "profile_nickname")
        self.assertNotIn("account_email", query.get("scope", [""])[0])

    @override_settings(
        KAKAO_REST_API_KEY="kakao-rest-key-test",
        KAKAO_REDIRECT_URI="http://127.0.0.1:5173/pages/kakao-callback.html",
        KAKAO_ALLOWED_REDIRECT_URIS=["http://127.0.0.1:5173/pages/kakao-callback.html"],
        KAKAO_INCLUDE_EMAIL_SCOPE=True,
    )
    def test_kakao_authorize_url_includes_email_scope_when_enabled(self):
        response = self.client.get(
            "/api/v1/auth/kakao/authorize-url",
            {
                "redirect_uri": "http://127.0.0.1:5173/pages/kakao-callback.html",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.data.get("data", {})
        authorize_url = data.get("authorize_url", "")
        parsed = urlparse(authorize_url)
        query = parse_qs(parsed.query)
        self.assertEqual(query.get("scope", [""])[0], "profile_nickname,account_email")

    @override_settings(
        KAKAO_REST_API_KEY="kakao-rest-key-test",
        KAKAO_REDIRECT_URI="http://127.0.0.1:5173/pages/kakao-callback.html",
        KAKAO_ALLOWED_REDIRECT_URIS=["http://127.0.0.1:5173/pages/kakao-callback.html"],
    )
    def test_kakao_authorize_url_rejects_invalid_redirect(self):
        response = self.client.get(
            "/api/v1/auth/kakao/authorize-url",
            {
                "redirect_uri": "http://malicious.local/callback",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data.get("success"))
        self.assertEqual(response.data.get("error", {}).get("code"), "INVALID_REDIRECT_URI")
