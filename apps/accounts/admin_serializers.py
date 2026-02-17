from __future__ import annotations

from rest_framework import serializers

from apps.orders.models import Order
from apps.reviews.models import Review
from apps.reviews.serializers import has_valid_image_file

from .models import OneToOneInquiry, UserCoupon


class AdminOrderSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", default="", read_only=True)
    user_name = serializers.CharField(source="user.name", default="", read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "order_no",
            "user_email",
            "user_name",
            "status",
            "payment_status",
            "shipping_status",
            "subtotal_amount",
            "shipping_fee",
            "discount_amount",
            "total_amount",
            "recipient",
            "phone",
            "courier_name",
            "tracking_no",
            "invoice_issued_at",
            "shipped_at",
            "delivered_at",
            "created_at",
            "item_count",
        )

    def get_item_count(self, obj: Order) -> int:
        return obj.items.count()


class AdminOrderUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices, required=False)
    payment_status = serializers.ChoiceField(choices=Order.PaymentStatus.choices, required=False)
    shipping_status = serializers.ChoiceField(choices=Order.ShippingStatus.choices, required=False)
    courier_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    tracking_no = serializers.CharField(max_length=100, required=False, allow_blank=True)
    issue_invoice = serializers.BooleanField(required=False, default=False)
    mark_delivered = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        order: Order = self.context["order"]
        issue_invoice = attrs.get("issue_invoice", False)
        next_courier = attrs.get("courier_name", order.courier_name)
        next_tracking = attrs.get("tracking_no", order.tracking_no)

        if issue_invoice and (not next_courier or not next_tracking):
            raise serializers.ValidationError(
                {
                    "tracking_no": "송장 발급 시 택배사와 송장번호가 필요합니다.",
                }
            )

        return attrs


class AdminInquirySerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.name", read_only=True)

    class Meta:
        model = OneToOneInquiry
        fields = (
            "id",
            "user_email",
            "user_name",
            "title",
            "content",
            "status",
            "answer",
            "answered_at",
            "created_at",
            "updated_at",
        )


class AdminInquiryAnswerSerializer(serializers.Serializer):
    answer = serializers.CharField()
    status = serializers.ChoiceField(choices=OneToOneInquiry.Status.choices, required=False)


class AdminReviewSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    images = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = (
            "id",
            "product_id",
            "product_name",
            "user_email",
            "user_name",
            "score",
            "title",
            "content",
            "status",
            "helpful_count",
            "created_at",
            "images",
        )

    def get_images(self, obj: Review) -> list[str]:
        request = self.context.get("request")
        rows = []
        for image in obj.images.all():
            if not has_valid_image_file(image.image):
                continue
            if request:
                rows.append(request.build_absolute_uri(image.image.url))
            else:
                rows.append(image.image.url)
        return rows


class AdminReviewVisibilitySerializer(serializers.Serializer):
    visible = serializers.BooleanField()


class AdminCouponSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = UserCoupon
        fields = (
            "id",
            "user_email",
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


class AdminCouponIssueSerializer(serializers.Serializer):
    TARGET_ALL = "ALL"
    TARGET_EMAIL = "EMAIL"

    target = serializers.ChoiceField(choices=((TARGET_ALL, TARGET_ALL), (TARGET_EMAIL, TARGET_EMAIL)))
    email = serializers.EmailField(required=False)
    name = serializers.CharField(max_length=150)
    code = serializers.CharField(max_length=64)
    discount_amount = serializers.IntegerField(min_value=0)
    min_order_amount = serializers.IntegerField(min_value=0, required=False, default=0)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["target"] == self.TARGET_EMAIL and not attrs.get("email"):
            raise serializers.ValidationError({"email": "특정 회원 발급 시 이메일이 필요합니다."})
        return attrs
