from __future__ import annotations

import logging
import uuid

import requests
from django.conf import settings
from rest_framework import serializers

from .models import User

logger = logging.getLogger(__name__)


class KakaoOAuthClient:
    token_url = "https://kauth.kakao.com/oauth/token"
    profile_url = "https://kapi.kakao.com/v2/user/me"

    def fetch_profile(self, code: str, redirect_uri: str | None = None) -> dict:
        if not settings.KAKAO_REST_API_KEY:
            raise serializers.ValidationError("카카오 OAuth 설정이 비어 있습니다.")

        effective_redirect_uri = redirect_uri or settings.KAKAO_REDIRECT_URI
        payload = {
            "grant_type": "authorization_code",
            "client_id": settings.KAKAO_REST_API_KEY,
            "redirect_uri": effective_redirect_uri,
            "code": code,
        }
        if settings.KAKAO_CLIENT_SECRET:
            payload["client_secret"] = settings.KAKAO_CLIENT_SECRET

        token_response = requests.post(self.token_url, data=payload, timeout=10)
        if token_response.status_code >= 400:
            logger.warning("kakao token exchange failed: %s", token_response.text)
            raise serializers.ValidationError("카카오 토큰 교환에 실패했습니다.")

        access_token = token_response.json().get("access_token")
        if not access_token:
            raise serializers.ValidationError("카카오 액세스 토큰이 없습니다.")

        profile_response = requests.get(
            self.profile_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if profile_response.status_code >= 400:
            logger.warning("kakao profile fetch failed: %s", profile_response.text)
            raise serializers.ValidationError("카카오 사용자 정보 조회에 실패했습니다.")

        return profile_response.json()

    def get_or_create_user(self, code: str, redirect_uri: str | None = None) -> User:
        profile = self.fetch_profile(code=code, redirect_uri=redirect_uri)
        kakao_sub = str(profile.get("id") or "")
        if not kakao_sub:
            raise serializers.ValidationError("카카오 사용자 식별값을 찾을 수 없습니다.")

        account = profile.get("kakao_account", {}) or {}
        email = account.get("email") or f"kakao_{kakao_sub}@sausalito.local"
        nickname = (account.get("profile") or {}).get("nickname") or "카카오회원"

        user = User.objects.filter(kakao_sub=kakao_sub).first() or User.objects.filter(email=email).first()
        if user:
            if not user.kakao_sub:
                user.kakao_sub = kakao_sub
            if not user.name:
                user.name = nickname
            user.save(update_fields=["kakao_sub", "name", "updated_at"])
            return user

        username = f"kakao_{uuid.uuid4().hex[:12]}"
        user = User.objects.create_user(
            email=email,
            password=uuid.uuid4().hex,
            username=username,
            name=nickname,
            kakao_sub=kakao_sub,
        )
        return user
