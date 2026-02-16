from __future__ import annotations

from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import User


class UserMeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "username", "name", "phone", "created_at")
        read_only_fields = ("id", "email", "username", "created_at")


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")
        user = authenticate(request=self.context.get("request"), email=email, password=password)
        if not user:
            raise serializers.ValidationError("이메일 또는 비밀번호가 올바르지 않습니다.")
        attrs["user"] = user
        return attrs


class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class KakaoCallbackSerializer(serializers.Serializer):
    code = serializers.CharField()
    redirect_uri = serializers.URLField(required=False, allow_blank=True)
    state = serializers.CharField(required=False, allow_blank=True)
