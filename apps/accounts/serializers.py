from __future__ import annotations

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import (
    DepositTransaction,
    OneToOneInquiry,
    PointTransaction,
    RecentViewedProduct,
    User,
    UserCoupon,
    WishlistItem,
)


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


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user

        old_password = attrs["old_password"]
        new_password = attrs["new_password"]
        new_password_confirm = attrs["new_password_confirm"]

        if not user.check_password(old_password):
            raise serializers.ValidationError({"old_password": "현재 비밀번호가 일치하지 않습니다."})

        if new_password != new_password_confirm:
            raise serializers.ValidationError({"new_password_confirm": "새 비밀번호 확인이 일치하지 않습니다."})

        validate_password(new_password, user=user)
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class PointTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PointTransaction
        fields = ("id", "tx_type", "amount", "balance_after", "description", "created_at")


class DepositTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DepositTransaction
        fields = ("id", "tx_type", "amount", "balance_after", "description", "created_at")


class UserCouponSerializer(serializers.ModelSerializer):
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = UserCoupon
        fields = (
            "id",
            "name",
            "code",
            "discount_amount",
            "min_order_amount",
            "expires_at",
            "is_used",
            "used_at",
            "is_expired",
            "created_at",
        )

    def get_is_expired(self, obj: UserCoupon) -> bool:
        return obj.is_expired


class WishlistCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()


class RecentViewedCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()


class OneToOneInquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = OneToOneInquiry
        fields = ("id", "title", "content", "status", "answer", "answered_at", "created_at", "updated_at")
        read_only_fields = ("id", "status", "answer", "answered_at", "created_at", "updated_at")


class OneToOneInquiryReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = OneToOneInquiry
        fields = ("id", "title", "content", "status", "answer", "answered_at", "created_at", "updated_at")


class WishlistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = WishlistItem
        fields = ("id", "product_id", "created_at")


class RecentViewedProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecentViewedProduct
        fields = ("id", "product_id", "viewed_at", "created_at")
