from __future__ import annotations

import re

from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import (
    BrandPageSetting,
    BrandStorySection,
    HomeBanner,
    Product,
    ProductBadge,
    ProductImage,
    ProductOption,
)
from apps.catalog.serializers import has_valid_image_file as has_valid_catalog_image_file
from apps.orders.models import Order, ReturnRequest
from apps.payments.models import PaymentTransaction
from apps.reviews.models import Review, ReviewReport
from apps.reviews.serializers import has_valid_image_file

from .admin_security import get_admin_permissions
from .models import OneToOneInquiry, SupportFaq, SupportNotice, User, UserCoupon

PRODUCT_PACKAGE_MONTHS = (1, 2, 3, 6)
PRODUCT_PACKAGE_NAME_MAP = {
    1: "1개월분",
    2: "2개월분 (1+1)",
    3: "3개월분 (2+1)",
    6: "6개월분 (4+2)",
}
PRODUCT_PACKAGE_BENEFIT_MAP = {
    1: "제품 상세선택",
    2: "1+1",
    3: "2+1",
    6: "4+2",
}
PRODUCT_PACKAGE_DISCOUNT_RATE_MAP = {
    1: 0,
    2: 8,
    3: 14,
    6: 20,
}
PRODUCT_PACKAGE_MONTH_PATTERN = re.compile(r"(\d+)\s*개월")


def extract_package_duration_months(name: str) -> int | None:
    match = PRODUCT_PACKAGE_MONTH_PATTERN.search(str(name or ""))
    if not match:
        return None
    try:
        month = int(match.group(1))
    except (TypeError, ValueError):
        return None
    return month if month in PRODUCT_PACKAGE_MONTHS else None


def build_default_package_price(base_price: int, duration_months: int) -> int:
    safe_base_price = max(int(base_price or 0), 0)
    discount_rate = int(PRODUCT_PACKAGE_DISCOUNT_RATE_MAP.get(duration_months, 0))
    return int(round((safe_base_price * duration_months) * (100 - discount_rate) / 100))


def build_default_package_option(*, duration_months: int, base_price: int, base_stock: int) -> dict:
    return {
        "id": None,
        "duration_months": duration_months,
        "name": PRODUCT_PACKAGE_NAME_MAP[duration_months],
        "benefit_label": PRODUCT_PACKAGE_BENEFIT_MAP[duration_months],
        "price": build_default_package_price(base_price, duration_months),
        "stock": max(int(base_stock or 0), 0),
        "is_active": True,
    }


def build_product_package_options(options, *, base_price: int, base_stock: int) -> list[dict]:
    selected_by_month: dict[int, ProductOption] = {}
    for option in options:
        duration_months = (
            int(option.duration_months)
            if option.duration_months in PRODUCT_PACKAGE_MONTHS
            else extract_package_duration_months(option.name)
        )
        if duration_months in PRODUCT_PACKAGE_MONTHS and duration_months not in selected_by_month:
            selected_by_month[duration_months] = option

    rows: list[dict] = []
    for duration_months in PRODUCT_PACKAGE_MONTHS:
        option = selected_by_month.get(duration_months)
        if option:
            rows.append(
                {
                    "id": option.id,
                    "duration_months": duration_months,
                    "name": option.name,
                    "benefit_label": option.benefit_label or PRODUCT_PACKAGE_BENEFIT_MAP[duration_months],
                    "price": int(option.price or 0),
                    "stock": int(option.stock or 0),
                    "is_active": bool(option.is_active),
                }
            )
        else:
            rows.append(
                build_default_package_option(
                    duration_months=duration_months,
                    base_price=base_price,
                    base_stock=base_stock,
                )
            )
    return rows


class AdminOrderSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", default="", read_only=True)
    user_name = serializers.CharField(source="user.name", default="", read_only=True)
    item_count = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()
    return_request_count = serializers.SerializerMethodField()
    has_open_return = serializers.SerializerMethodField()
    latest_payment_provider = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "order_no",
            "user_email",
            "user_name",
            "status",
            "payment_status",
            "payment_method",
            "latest_payment_provider",
            "shipping_status",
            "product_order_status",
            "subtotal_amount",
            "shipping_fee",
            "discount_amount",
            "total_amount",
            "recipient",
            "phone",
            "postal_code",
            "road_address",
            "jibun_address",
            "detail_address",
            "courier_name",
            "tracking_no",
            "invoice_issued_at",
            "shipped_at",
            "delivered_at",
            "created_at",
            "item_count",
            "items",
            "return_request_count",
            "has_open_return",
        )

    def get_item_count(self, obj: Order) -> int:
        return obj.items.count()

    def get_items(self, obj: Order) -> list[dict]:
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get("items")
        items = prefetched if prefetched is not None else obj.items.all()
        rows: list[dict] = []
        for item in items:
            rows.append(
                {
                    "id": int(item.id),
                    "product_id_snapshot": int(item.product_id_snapshot or 0),
                    "product_name_snapshot": item.product_name_snapshot or "",
                    "option_name_snapshot": item.option_name_snapshot or "",
                    "unit_price": int(item.unit_price or 0),
                    "quantity": int(item.quantity or 0),
                    "line_total": int(item.line_total or 0),
                }
            )
        return rows

    def get_return_request_count(self, obj: Order) -> int:
        return obj.return_requests.count()

    def get_has_open_return(self, obj: Order) -> bool:
        return obj.return_requests.exclude(status__in=[ReturnRequest.Status.CLOSED, ReturnRequest.Status.REJECTED]).exists()

    def _get_latest_payment_provider(self, obj: Order) -> str:
        transactions = getattr(obj, "_prefetched_objects_cache", {}).get("payment_transactions")
        if transactions is None:
            tx = obj.payment_transactions.order_by("-created_at").first()
            return tx.provider if tx else ""
        if not transactions:
            return ""
        latest = max(transactions, key=lambda tx: tx.created_at.timestamp() if tx.created_at else 0)
        return latest.provider or ""

    def _get_latest_bank_transfer(self, obj: Order):
        transfers = getattr(obj, "_prefetched_objects_cache", {}).get("bank_transfer_requests")
        if transfers is None:
            return obj.bank_transfer_requests.order_by("-created_at").first()
        if not transfers:
            return None
        return max(transfers, key=lambda transfer: transfer.created_at.timestamp() if transfer.created_at else 0)

    def get_latest_payment_provider(self, obj: Order) -> str:
        return self._get_latest_payment_provider(obj)

    def get_payment_method(self, obj: Order) -> str:
        latest_transfer = self._get_latest_bank_transfer(obj)
        if latest_transfer:
            return "BANK_TRANSFER"

        provider = self._get_latest_payment_provider(obj)
        if provider == PaymentTransaction.Provider.BANK_TRANSFER:
            return "BANK_TRANSFER"
        if provider:
            return "BANK_TRANSFER"
        if obj.payment_status in {
            Order.PaymentStatus.READY,
            Order.PaymentStatus.APPROVED,
            Order.PaymentStatus.CANCELED,
            Order.PaymentStatus.FAILED,
        }:
            return "BANK_TRANSFER"
        return ""


class AdminOrderUpdateSerializer(serializers.Serializer):
    recipient = serializers.CharField(max_length=100, required=False)
    phone = serializers.CharField(max_length=20, required=False)
    postal_code = serializers.CharField(max_length=10, required=False)
    road_address = serializers.CharField(max_length=255, required=False)
    jibun_address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    detail_address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=Order.Status.choices, required=False)
    payment_status = serializers.ChoiceField(choices=Order.PaymentStatus.choices, required=False)
    shipping_status = serializers.ChoiceField(choices=Order.ShippingStatus.choices, required=False)
    product_order_status = serializers.ChoiceField(choices=Order.ProductOrderStatus.choices, required=False)
    courier_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    tracking_no = serializers.CharField(max_length=100, required=False, allow_blank=True)
    issue_invoice = serializers.BooleanField(required=False, default=False)
    mark_delivered = serializers.BooleanField(required=False, default=False)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)

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
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate(self, attrs):
        assigned_admin_id = attrs.get("assigned_admin_id")
        if assigned_admin_id is not None:
            if assigned_admin_id == 0:
                attrs["assigned_admin_id"] = None
            elif not User.objects.filter(id=assigned_admin_id, is_staff=True, is_active=True).exists():
                raise serializers.ValidationError({"assigned_admin_id": "유효한 관리자 계정이 아닙니다."})

        effective_attrs = {k: v for k, v in attrs.items() if k != "idempotency_key"}
        if not effective_attrs:
            raise serializers.ValidationError("변경할 필드를 하나 이상 전달해주세요.")

        return attrs


class AdminSupportNoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportNotice
        fields = ("id", "title", "content", "is_pinned", "is_active", "published_at", "created_at", "updated_at")


class AdminSupportNoticeUpsertSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    content = serializers.CharField(required=False)
    is_pinned = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)
    published_at = serializers.DateTimeField(required=False)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)


class AdminSupportFaqSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportFaq
        fields = ("id", "category", "question", "answer", "sort_order", "is_active", "created_at", "updated_at")


class AdminSupportFaqUpsertSerializer(serializers.Serializer):
    category = serializers.CharField(max_length=60, required=False)
    question = serializers.CharField(max_length=255, required=False)
    answer = serializers.CharField(required=False)
    sort_order = serializers.IntegerField(required=False, min_value=0)
    is_active = serializers.BooleanField(required=False)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)


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
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)


class AdminReturnRequestUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ReturnRequest.Status.choices, required=False)
    approved_amount = serializers.IntegerField(min_value=0, required=False)
    rejected_reason = serializers.CharField(required=False, allow_blank=True)
    pickup_courier_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    pickup_tracking_no = serializers.CharField(max_length=100, required=False, allow_blank=True)
    admin_note = serializers.CharField(required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate(self, attrs):
        effective_attrs = {k: v for k, v in attrs.items() if k != "idempotency_key"}
        if not effective_attrs:
            raise serializers.ValidationError("변경할 필드를 하나 이상 전달해주세요.")
        return attrs


class AdminReviewSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    images = serializers.SerializerMethodField()
    admin_replied_by_name = serializers.CharField(source="admin_replied_by.name", default="", read_only=True)
    report_total_count = serializers.SerializerMethodField()
    report_pending_count = serializers.SerializerMethodField()
    report_status = serializers.SerializerMethodField()
    last_reported_at = serializers.SerializerMethodField()
    latest_report_reason = serializers.SerializerMethodField()
    latest_report_detail = serializers.SerializerMethodField()

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
            "is_best",
            "helpful_count",
            "admin_reply",
            "admin_replied_at",
            "admin_replied_by_name",
            "report_total_count",
            "report_pending_count",
            "report_status",
            "last_reported_at",
            "latest_report_reason",
            "latest_report_detail",
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

    def _get_report_total_count(self, obj: Review) -> int:
        value = getattr(obj, "report_total_count", None)
        if value is not None:
            return int(value or 0)
        return obj.reports.count()

    def _get_report_pending_count(self, obj: Review) -> int:
        value = getattr(obj, "report_pending_count", None)
        if value is not None:
            return int(value or 0)
        return obj.reports.filter(status=ReviewReport.Status.PENDING).count()

    def _get_last_reported_at(self, obj: Review):
        value = getattr(obj, "last_reported_at", None)
        if value is not None:
            return value
        latest = obj.reports.order_by("-created_at").values_list("created_at", flat=True).first()
        return latest

    def _get_latest_report_row(self, obj: Review):
        prefetched = getattr(obj, "_cached_latest_report", None)
        if prefetched is not None:
            return prefetched
        latest = obj.reports.order_by("-created_at").first()
        setattr(obj, "_cached_latest_report", latest)
        return latest

    def get_report_total_count(self, obj: Review) -> int:
        return self._get_report_total_count(obj)

    def get_report_pending_count(self, obj: Review) -> int:
        return self._get_report_pending_count(obj)

    def get_report_status(self, obj: Review) -> str:
        pending_count = self._get_report_pending_count(obj)
        if pending_count > 0:
            return ReviewReport.Status.PENDING
        if self._get_report_total_count(obj) > 0:
            return "HANDLED"
        return "NONE"

    def get_last_reported_at(self, obj: Review):
        value = self._get_last_reported_at(obj)
        if not value:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    def get_latest_report_reason(self, obj: Review) -> str:
        latest = self._get_latest_report_row(obj)
        return latest.reason if latest else ""

    def get_latest_report_detail(self, obj: Review) -> str:
        latest = self._get_latest_report_row(obj)
        return latest.detail if latest else ""


class AdminReviewVisibilitySerializer(serializers.Serializer):
    visible = serializers.BooleanField()
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)


class AdminReviewManageSerializer(serializers.Serializer):
    is_best = serializers.BooleanField(required=False)
    answer = serializers.CharField(required=False, allow_blank=True)
    delete_answer = serializers.BooleanField(required=False, default=False)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate(self, attrs):
        has_best = "is_best" in attrs
        has_answer = "answer" in attrs
        delete_answer = bool(attrs.get("delete_answer", False))
        if not (has_best or has_answer or delete_answer):
            raise serializers.ValidationError("변경할 필드를 하나 이상 전달해주세요.")

        if has_answer:
            attrs["answer"] = attrs["answer"].strip()

        if delete_answer and has_answer and attrs.get("answer"):
            raise serializers.ValidationError({"answer": "답변 삭제 시 answer를 함께 보낼 수 없습니다."})

        return attrs


class AdminReviewReportManageSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=(("RESOLVE", "RESOLVE"), ("REJECT", "REJECT")))
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)


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


class AdminBrandPageSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandPageSetting
        fields = ("id", "hero_eyebrow", "hero_title", "hero_description", "updated_at")


class AdminBrandPageSettingUpdateSerializer(serializers.Serializer):
    hero_eyebrow = serializers.CharField(required=False, allow_blank=True, max_length=120)
    hero_title = serializers.CharField(required=False, allow_blank=False, max_length=255)
    hero_description = serializers.CharField(required=False, allow_blank=True)


class AdminBrandStorySectionSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = BrandStorySection
        fields = (
            "id",
            "eyebrow",
            "title",
            "description",
            "image_alt",
            "sort_order",
            "is_active",
            "image_url",
            "created_at",
            "updated_at",
        )

    def get_image_url(self, obj: BrandStorySection) -> str:
        if not has_valid_catalog_image_file(obj.image):
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url


class AdminBrandStorySectionUpsertSerializer(serializers.Serializer):
    eyebrow = serializers.CharField(required=False, allow_blank=True, max_length=120)
    title = serializers.CharField(required=False, allow_blank=False, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    image_alt = serializers.CharField(required=False, allow_blank=True, max_length=255)
    sort_order = serializers.IntegerField(required=False, min_value=0)
    is_active = serializers.BooleanField(required=False)


class AdminProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ("id", "image_url", "is_thumbnail", "sort_order")

    def get_image_url(self, obj: ProductImage) -> str:
        if not has_valid_catalog_image_file(obj.image):
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url


class AdminProductPackageOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    duration_months = serializers.ChoiceField(choices=PRODUCT_PACKAGE_MONTHS)
    name = serializers.CharField(max_length=255)
    benefit_label = serializers.CharField(max_length=40, allow_blank=True, required=False)
    price = serializers.IntegerField(min_value=0)
    stock = serializers.IntegerField(min_value=0, required=False, default=0)
    is_active = serializers.BooleanField(required=False, default=True)


class AdminProductManageSerializer(serializers.ModelSerializer):
    thumbnail_url = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    badge_types = serializers.SerializerMethodField()
    package_options = serializers.SerializerMethodField()
    category_id = serializers.IntegerField(source="category.id", read_only=True, allow_null=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default="")

    class Meta:
        model = Product
        fields = (
            "id",
            "category_id",
            "sku",
            "name",
            "one_line",
            "description",
            "intake",
            "target",
            "manufacturer",
            "origin_country",
            "tax_status",
            "delivery_fee",
            "free_shipping_amount",
            "search_keywords",
            "release_date",
            "display_start_at",
            "display_end_at",
            "price",
            "original_price",
            "stock",
            "is_active",
            "category_name",
            "badge_types",
            "package_options",
            "thumbnail_url",
            "images",
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

    def get_images(self, obj: Product) -> list[dict]:
        rows = [row for row in obj.images.all() if has_valid_catalog_image_file(row.image)]
        return AdminProductImageSerializer(rows, many=True, context=self.context).data

    def get_package_options(self, obj: Product) -> list[dict]:
        return build_product_package_options(
            obj.options.all(),
            base_price=int(obj.price or 0),
            base_stock=int(obj.stock or 0),
        )


class AdminProductUpsertSerializer(serializers.Serializer):
    category_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    sku = serializers.CharField(max_length=80, required=False, allow_blank=True)
    name = serializers.CharField(max_length=255, required=False, allow_blank=False)
    one_line = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    intake = serializers.CharField(required=False, allow_blank=True)
    target = serializers.CharField(required=False, allow_blank=True)
    manufacturer = serializers.CharField(max_length=120, required=False, allow_blank=True)
    origin_country = serializers.CharField(max_length=120, required=False, allow_blank=True)
    tax_status = serializers.ChoiceField(choices=Product.TaxStatus.choices, required=False)
    delivery_fee = serializers.IntegerField(required=False, min_value=0)
    free_shipping_amount = serializers.IntegerField(required=False, min_value=0)
    search_keywords = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        allow_empty=True,
    )
    release_date = serializers.DateField(required=False, allow_null=True)
    display_start_at = serializers.DateTimeField(required=False, allow_null=True)
    display_end_at = serializers.DateTimeField(required=False, allow_null=True)
    price = serializers.IntegerField(required=False, min_value=0)
    original_price = serializers.IntegerField(required=False, min_value=0)
    stock = serializers.IntegerField(required=False, min_value=0)
    is_active = serializers.BooleanField(required=False)
    badge_types = serializers.ListField(
        child=serializers.ChoiceField(choices=ProductBadge.BadgeType.choices),
        required=False,
        allow_empty=True,
    )
    delete_image_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )
    thumbnail_image_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    package_options = AdminProductPackageOptionSerializer(many=True, required=False)

    def validate(self, attrs):
        display_start_at = attrs.get("display_start_at")
        display_end_at = attrs.get("display_end_at")
        if display_start_at and display_end_at and display_end_at < display_start_at:
            raise serializers.ValidationError(
                {"display_end_at": "노출 종료일시는 노출 시작일시보다 빠를 수 없습니다."}
            )

        package_options = attrs.get("package_options")
        if package_options is not None:
            duration_months_set = {int(row["duration_months"]) for row in package_options}
            required_set = set(PRODUCT_PACKAGE_MONTHS)
            if len(package_options) != len(PRODUCT_PACKAGE_MONTHS) or duration_months_set != required_set:
                raise serializers.ValidationError(
                    {"package_options": "상품구성은 1개월분/2개월분/3개월분/6개월분 4개를 모두 입력해야 합니다."}
                )
        return attrs


class AdminUserManageSerializer(serializers.ModelSerializer):
    order_count = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    inquiry_count = serializers.SerializerMethodField()
    admin_role = serializers.CharField(read_only=True)
    admin_permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "name",
            "phone",
            "is_active",
            "is_staff",
            "admin_role",
            "admin_permissions",
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

    def get_admin_permissions(self, obj: User) -> list[str]:
        if not obj.is_staff:
            return []
        return sorted(get_admin_permissions(obj))


class AdminUserUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    is_active = serializers.BooleanField(required=False)
    is_staff = serializers.BooleanField(required=False)
    admin_role = serializers.ChoiceField(choices=User.AdminRole.choices, required=False)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate(self, attrs):
        effective_attrs = {k: v for k, v in attrs.items() if k != "idempotency_key"}
        if not effective_attrs:
            raise serializers.ValidationError("변경할 필드를 하나 이상 전달해주세요.")
        return attrs


class AdminAuditLogSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    occurred_at = serializers.DateTimeField()
    actor_admin_id = serializers.IntegerField(allow_null=True)
    actor_admin_email = serializers.CharField()
    actor_role = serializers.CharField(allow_blank=True)
    action = serializers.CharField()
    target_type = serializers.CharField(allow_blank=True)
    target_id = serializers.CharField(allow_blank=True)
    request_id = serializers.CharField(allow_blank=True)
    idempotency_key = serializers.CharField(allow_blank=True)
    ip = serializers.CharField(allow_blank=True)
    user_agent = serializers.CharField(allow_blank=True)
    before_json = serializers.JSONField()
    after_json = serializers.JSONField()
    metadata_json = serializers.JSONField()
    result = serializers.CharField()
    error_code = serializers.CharField(allow_blank=True)
