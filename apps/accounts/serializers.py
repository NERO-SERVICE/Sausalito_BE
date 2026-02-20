from __future__ import annotations

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from .admin_security import get_admin_permissions, get_admin_role
from .models import (
    Address,
    DepositTransaction,
    OneToOneInquiry,
    PointTransaction,
    RecentViewedProduct,
    User,
    UserCoupon,
    WishlistItem,
)


class UserMeSerializer(serializers.ModelSerializer):
    isStaff = serializers.BooleanField(source="is_staff", read_only=True)
    adminRole = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "name",
            "phone",
            "sms_marketing_opt_in",
            "email_marketing_opt_in",
            "is_staff",
            "isStaff",
            "admin_role",
            "adminRole",
            "permissions",
            "created_at",
        )
        read_only_fields = (
            "id",
            "username",
            "is_staff",
            "isStaff",
            "admin_role",
            "adminRole",
            "permissions",
            "created_at",
        )

    def validate_email(self, value):
        email = str(value).strip().lower()
        qs = User.objects.filter(email__iexact=email)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("이미 사용 중인 이메일입니다.")
        return email

    def get_adminRole(self, obj: User) -> str:
        return get_admin_role(obj)

    def get_permissions(self, obj: User) -> list[str]:
        return sorted(get_admin_permissions(obj))


class DefaultAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = (
            "id",
            "recipient",
            "phone",
            "postal_code",
            "road_address",
            "detail_address",
            "is_default",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DefaultAddressUpdateSerializer(serializers.Serializer):
    recipient = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=20)
    postal_code = serializers.CharField(max_length=10)
    road_address = serializers.CharField(max_length=255)
    detail_address = serializers.CharField(required=False, allow_blank=True, max_length=255)


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


class KakaoAuthorizeUrlSerializer(serializers.Serializer):
    redirect_uri = serializers.URLField(required=False, allow_blank=True)
    state = serializers.CharField(required=False, allow_blank=True, max_length=255)


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)
    name = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=20)
    recipient = serializers.CharField(max_length=100)
    recipient_phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    postal_code = serializers.CharField(max_length=10)
    road_address = serializers.CharField(max_length=255)
    detail_address = serializers.CharField(required=False, allow_blank=True, max_length=255)
    terms_agree = serializers.BooleanField()
    privacy_collect_agree = serializers.BooleanField()
    age_over_14_agree = serializers.BooleanField()
    health_functional_food_notice_agree = serializers.BooleanField()
    sms_marketing_agree = serializers.BooleanField(required=False, default=False)
    email_marketing_agree = serializers.BooleanField(required=False, default=False)

    def validate_email(self, value):
        email = str(value).strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("이미 사용 중인 이메일입니다.")
        return email

    def validate(self, attrs):
        password = attrs["password"]
        password_confirm = attrs["password_confirm"]
        if password != password_confirm:
            raise serializers.ValidationError({"password_confirm": "비밀번호 확인이 일치하지 않습니다."})
        validate_password(password)

        required_consents = {
            "terms_agree": "이용약관",
            "privacy_collect_agree": "개인정보 수집 및 이용",
            "age_over_14_agree": "만 14세 이상 확인",
            "health_functional_food_notice_agree": "건강기능식품 구매/섭취 안내",
        }
        for field, label in required_consents.items():
            if not attrs.get(field):
                raise serializers.ValidationError({field: f"{label} 동의가 필요합니다."})
        return attrs

    def create(self, validated_data):
        data = dict(validated_data)
        data.pop("password_confirm", None)
        recipient_phone = data.pop("recipient_phone", "").strip() or data["phone"]
        detail_address = data.pop("detail_address", "").strip()
        password = data.pop("password")
        terms_agree = bool(data.pop("terms_agree"))
        privacy_collect_agree = bool(data.pop("privacy_collect_agree"))
        age_over_14_agree = bool(data.pop("age_over_14_agree"))
        health_functional_food_notice_agree = bool(data.pop("health_functional_food_notice_agree"))
        sms_marketing_agree = bool(data.pop("sms_marketing_agree", False))
        email_marketing_agree = bool(data.pop("email_marketing_agree", False))
        now = timezone.now()

        user = User.objects.create_user(
            email=data["email"],
            password=password,
            name=data["name"],
            phone=data["phone"],
            terms_agreed_at=now if terms_agree else None,
            privacy_collect_agreed_at=now if privacy_collect_agree else None,
            age_over_14_agreed_at=now if age_over_14_agree else None,
            health_functional_food_notice_agreed_at=now if health_functional_food_notice_agree else None,
            sms_marketing_opt_in=sms_marketing_agree,
            sms_marketing_opt_in_at=now if sms_marketing_agree else None,
            email_marketing_opt_in=email_marketing_agree,
            email_marketing_opt_in_at=now if email_marketing_agree else None,
        )
        Address.objects.create(
            user=user,
            recipient=data["recipient"],
            phone=recipient_phone,
            postal_code=data["postal_code"],
            road_address=data["road_address"],
            detail_address=detail_address,
            is_default=True,
        )
        return user


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


class UserWithdrawSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user
        password = attrs.get("password", "")
        if not user.check_password(password):
            raise serializers.ValidationError({"password": "비밀번호가 일치하지 않습니다."})
        return attrs


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
