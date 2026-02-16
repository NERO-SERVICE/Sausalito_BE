from __future__ import annotations

from django.conf import settings
from django.contrib.auth import login as django_login
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.response import error_response, success_response

from .serializers import (
    KakaoCallbackSerializer,
    LoginSerializer,
    LogoutSerializer,
    TokenRefreshRequestSerializer,
    UserMeSerializer,
)
from .services import KakaoOAuthClient


def issue_tokens_for_user(user) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        django_login(request, user)
        return success_response(
            {
                "user": UserMeSerializer(user).data,
                "tokens": issue_tokens_for_user(user),
            },
            message="로그인되었습니다.",
        )


class KakaoCallbackAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = KakaoCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        redirect_uri = serializer.validated_data.get("redirect_uri")

        allowed_redirect_uris = settings.KAKAO_ALLOWED_REDIRECT_URIS
        if allowed_redirect_uris and redirect_uri and redirect_uri not in allowed_redirect_uris:
            return error_response(
                code="INVALID_REDIRECT_URI",
                message="허용되지 않은 redirect_uri 입니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        user = KakaoOAuthClient().get_or_create_user(
            code=serializer.validated_data["code"],
            redirect_uri=redirect_uri,
        )

        return success_response(
            {
                "user": UserMeSerializer(user).data,
                "tokens": issue_tokens_for_user(user),
            },
            message="카카오 로그인이 완료되었습니다.",
        )


class RefreshAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        request_serializer = TokenRefreshRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        serializer = TokenRefreshSerializer(data=request_serializer.validated_data)
        serializer.is_valid(raise_exception=True)
        return success_response(serializer.validated_data, message="토큰이 갱신되었습니다.")


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data["refresh"]
        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError as exc:
            raise AuthenticationFailed("유효하지 않은 리프레시 토큰입니다.") from exc

        return success_response(message="로그아웃되었습니다.")


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        serializer = UserMeSerializer(request.user)
        return success_response(serializer.data)

    def patch(self, request, *args, **kwargs):
        serializer = UserMeSerializer(instance=request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(serializer.data, message="회원 정보가 업데이트되었습니다.")


class HealthCheckAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return Response({"ok": True})
