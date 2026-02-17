from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import HomeBanner, Product, ProductBadge, ProductImage
from apps.catalog.serializers import has_valid_image_file as has_valid_catalog_image_file
from apps.orders.models import Order, ReturnRequest, SettlementRecord
from apps.reviews.models import Review
from apps.reviews.serializers import has_valid_image_file

from .models import OneToOneInquiry, User, UserCoupon


class AdminOrderSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", default="", read_only=True)
    user_name = serializers.CharField(source="user.name", default="", read_only=True)
    item_count = serializers.SerializerMethodField()
    return_request_count = serializers.SerializerMethodField()
    has_open_return = serializers.SerializerMethodField()
    settlement_status = serializers.SerializerMethodField()

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
            "postal_code",
            "road_address",
            "detail_address",
            "courier_name",
            "tracking_no",
            "invoice_issued_at",
            "shipped_at",
            "delivered_at",
            "created_at",
            "item_count",
            "return_request_count",
            "has_open_return",
            "settlement_status",
        )

    def get_item_count(self, obj: Order) -> int:
        return obj.items.count()

    def get_return_request_count(self, obj: Order) -> int:
        return obj.return_requests.count()

    def get_has_open_return(self, obj: Order) -> bool:
        return obj.return_requests.exclude(status__in=[ReturnRequest.Status.CLOSED, ReturnRequest.Status.REJECTED]).exists()

    def get_settlement_status(self, obj: Order) -> str:
        if not hasattr(obj, "settlement_record") or not obj.settlement_record:
            return ""
        return obj.settlement_record.status


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
    assigned_admin_id = serializers.IntegerField(source="assigned_admin.id", read_only=True)
    assigned_admin_email = serializers.CharField(source="assigned_admin.email", default="", read_only=True)
    is_sla_overdue = serializers.SerializerMethodField()

    class Meta:
        model = OneToOneInquiry
        fields = (
            "id",
            "user_email",
            "user_name",
            "title",
            "content",
            "category",
            "priority",
            "status",
            "channel",
            "assigned_admin_id",
            "assigned_admin_email",
            "internal_note",
            "answer",
            "first_response_at",
            "answered_at",
            "resolved_at",
            "sla_due_at",
            "is_sla_overdue",
            "created_at",
            "updated_at",
        )

    def get_is_sla_overdue(self, obj: OneToOneInquiry) -> bool:
        if not obj.sla_due_at:
            return False
        if obj.status in {OneToOneInquiry.Status.ANSWERED, OneToOneInquiry.Status.CLOSED}:
            return False
        return timezone.now() > obj.sla_due_at


class AdminInquiryAnswerSerializer(serializers.Serializer):
    answer = serializers.CharField(required=False, allow_blank=True)
    delete_answer = serializers.BooleanField(required=False, default=False)
    status = serializers.ChoiceField(choices=OneToOneInquiry.Status.choices, required=False)
    category = serializers.ChoiceField(choices=OneToOneInquiry.Category.choices, required=False)
    priority = serializers.ChoiceField(choices=OneToOneInquiry.Priority.choices, required=False)
    assigned_admin_id = serializers.IntegerField(required=False, allow_null=True)
    internal_note = serializers.CharField(required=False, allow_blank=True)
    sla_due_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        assigned_admin_id = attrs.get("assigned_admin_id")
        if assigned_admin_id is not None:
            if assigned_admin_id == 0:
                attrs["assigned_admin_id"] = None
            elif not User.objects.filter(id=assigned_admin_id, is_staff=True, is_active=True).exists():
                raise serializers.ValidationError({"assigned_admin_id": "유효한 관리자 계정이 아닙니다."})

        if not attrs:
            raise serializers.ValidationError("변경할 필드를 하나 이상 전달해주세요.")

        return attrs


class AdminReturnRequestSerializer(serializers.ModelSerializer):
    order_no = serializers.CharField(source="order.order_no", read_only=True)
    user_email = serializers.CharField(source="user.email", default="", read_only=True)

    class Meta:
        model = ReturnRequest
        fields = (
            "id",
            "order_no",
            "user_email",
            "status",
            "reason_title",
            "reason_detail",
            "requested_amount",
            "approved_amount",
            "rejected_reason",
            "pickup_courier_name",
            "pickup_tracking_no",
            "admin_note",
            "requested_at",
            "approved_at",
            "received_at",
            "refunded_at",
            "closed_at",
            "updated_at",
        )


class AdminReturnRequestCreateSerializer(serializers.Serializer):
    order_no = serializers.CharField()
    reason_title = serializers.CharField(max_length=200)
    reason_detail = serializers.CharField(required=False, allow_blank=True)
    requested_amount = serializers.IntegerField(min_value=0, required=False)


class AdminReturnRequestUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ReturnRequest.Status.choices, required=False)
    approved_amount = serializers.IntegerField(min_value=0, required=False)
    rejected_reason = serializers.CharField(required=False, allow_blank=True)
    pickup_courier_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    pickup_tracking_no = serializers.CharField(max_length=100, required=False, allow_blank=True)
    admin_note = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("변경할 필드를 하나 이상 전달해주세요.")
        return attrs


class AdminSettlementSerializer(serializers.ModelSerializer):
    order_no = serializers.CharField(source="order.order_no", read_only=True)
    order_created_at = serializers.DateTimeField(source="order.created_at", read_only=True)
    order_payment_status = serializers.CharField(source="order.payment_status", read_only=True)
    order_shipping_status = serializers.CharField(source="order.shipping_status", read_only=True)
    user_email = serializers.CharField(source="order.user.email", default="", read_only=True)

    class Meta:
        model = SettlementRecord
        fields = (
            "id",
            "order_no",
            "user_email",
            "status",
            "gross_amount",
            "discount_amount",
            "shipping_fee",
            "pg_fee",
            "platform_fee",
            "return_deduction",
            "settlement_amount",
            "expected_payout_date",
            "paid_at",
            "memo",
            "order_created_at",
            "order_payment_status",
            "order_shipping_status",
            "created_at",
            "updated_at",
        )


class AdminSettlementUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=SettlementRecord.Status.choices, required=False)
    pg_fee = serializers.IntegerField(required=False)
    platform_fee = serializers.IntegerField(required=False)
    return_deduction = serializers.IntegerField(required=False)
    expected_payout_date = serializers.DateField(required=False, allow_null=True)
    mark_paid = serializers.BooleanField(required=False, default=False)
    memo = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("변경할 필드를 하나 이상 전달해주세요.")
        return attrs


class AdminSettlementGenerateSerializer(serializers.Serializer):
    only_paid_orders = serializers.BooleanField(required=False, default=True)


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


class AdminHomeBannerSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = HomeBanner
        fields = (
            "id",
            "subtitle",
            "title",
            "description",
            "cta_text",
            "link_url",
            "sort_order",
            "is_active",
            "image_url",
        )

    def get_image_url(self, obj: HomeBanner) -> str:
        if not has_valid_catalog_image_file(obj.image):
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url


class AdminBannerUpsertSerializer(serializers.Serializer):
    subtitle = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(max_length=255, required=False, allow_blank=False)
    description = serializers.CharField(required=False, allow_blank=True)
    cta_text = serializers.CharField(required=False, allow_blank=True)
    link_url = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.IntegerField(required=False, min_value=0)
    is_active = serializers.BooleanField(required=False)


class AdminProductManageSerializer(serializers.ModelSerializer):
    thumbnail_url = serializers.SerializerMethodField()
    badge_types = serializers.SerializerMethodField()
    category_name = serializers.CharField(source="category.name", read_only=True, default="")

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "one_line",
            "description",
            "price",
            "original_price",
            "stock",
            "is_active",
            "category_name",
            "badge_types",
            "thumbnail_url",
            "created_at",
            "updated_at",
        )

    def get_badge_types(self, obj: Product) -> list[str]:
        return [row.badge_type for row in obj.badges.all()]

    def get_thumbnail_url(self, obj: Product) -> str:
        thumbnail = next(
            (row for row in obj.images.all() if row.is_thumbnail and has_valid_catalog_image_file(row.image)),
            None,
        )
        if not thumbnail:
            thumbnail = next((row for row in obj.images.all() if has_valid_catalog_image_file(row.image)), None)
        if not thumbnail:
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(thumbnail.image.url)
        return thumbnail.image.url


class AdminProductUpsertSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False, allow_blank=False)
    one_line = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    price = serializers.IntegerField(required=False, min_value=0)
    original_price = serializers.IntegerField(required=False, min_value=0)
    stock = serializers.IntegerField(required=False, min_value=0)
    is_active = serializers.BooleanField(required=False)
    badge_types = serializers.ListField(
        child=serializers.ChoiceField(choices=ProductBadge.BadgeType.choices),
        required=False,
        allow_empty=True,
    )


class AdminUserManageSerializer(serializers.ModelSerializer):
    order_count = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    inquiry_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "name",
            "phone",
            "is_active",
            "is_staff",
            "order_count",
            "review_count",
            "inquiry_count",
            "created_at",
            "last_login",
        )

    def get_order_count(self, obj: User) -> int:
        return int(getattr(obj, "order_count", 0))

    def get_review_count(self, obj: User) -> int:
        return int(getattr(obj, "review_count", 0))

    def get_inquiry_count(self, obj: User) -> int:
        return int(getattr(obj, "inquiry_count", 0))


class AdminUserUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    is_active = serializers.BooleanField(required=False)
    is_staff = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("변경할 필드를 하나 이상 전달해주세요.")
        return attrs
