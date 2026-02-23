from __future__ import annotations

import json
from datetime import date

from django.core.paginator import EmptyPage, Paginator
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from apps.catalog.models import (
    BrandPageSetting,
    BrandStorySection,
    Category,
    HomeBanner,
    Product,
    ProductBadge,
    ProductImage,
    ProductOption,
)
from apps.common.response import error_response, success_response
from apps.orders.models import Order, ReturnRequest
from apps.reviews.models import Review, ReviewReport
from apps.reviews.serializers import refresh_product_rating

from .admin_serializers import (
    AdminAuditLogSerializer,
    AdminBannerUpsertSerializer,
    AdminBrandPageSettingSerializer,
    AdminBrandPageSettingUpdateSerializer,
    AdminBrandStorySectionSerializer,
    AdminBrandStorySectionUpsertSerializer,
    AdminCouponIssueSerializer,
    AdminCouponSerializer,
    AdminHomeBannerSerializer,
    AdminInquiryAnswerSerializer,
    AdminInquirySerializer,
    AdminOrderSerializer,
    AdminOrderUpdateSerializer,
    AdminProductManageSerializer,
    AdminProductUpsertSerializer,
    AdminReturnRequestCreateSerializer,
    AdminReturnRequestSerializer,
    AdminReturnRequestUpdateSerializer,
    AdminReviewSerializer,
    AdminReviewManageSerializer,
    AdminReviewReportManageSerializer,
    AdminSupportFaqSerializer,
    AdminSupportFaqUpsertSerializer,
    AdminSupportNoticeSerializer,
    AdminSupportNoticeUpsertSerializer,
    AdminReviewVisibilitySerializer,
    AdminUserManageSerializer,
    AdminUserUpdateSerializer,
    PRODUCT_PACKAGE_BENEFIT_MAP,
    PRODUCT_PACKAGE_MONTHS,
    build_default_package_option,
    extract_package_duration_months,
)
from .admin_security import (
    AdminPermission,
    AdminRBACPermission,
    apply_masking_to_inquiries,
    apply_masking_to_orders,
    apply_masking_to_returns,
    apply_masking_to_users,
    build_request_hash,
    extract_idempotency_key,
    get_idempotent_replay_response,
    get_admin_role,
    has_admin_permission,
    has_full_pii_access,
    log_audit_event,
    require_admin_permission,
    save_idempotent_response,
)
from .models import AuditLog, OneToOneInquiry, SupportFaq, SupportNotice, User, UserCoupon

ORDER_STATUS_TRANSITIONS: dict[str, set[str]] = {
    Order.Status.PENDING: {Order.Status.PAID, Order.Status.FAILED, Order.Status.CANCELED},
    Order.Status.PAID: {Order.Status.CANCELED, Order.Status.PARTIAL_REFUNDED, Order.Status.REFUNDED},
    Order.Status.FAILED: {Order.Status.PENDING, Order.Status.CANCELED},
    Order.Status.CANCELED: set(),
    Order.Status.REFUNDED: set(),
    Order.Status.PARTIAL_REFUNDED: {Order.Status.REFUNDED},
}

PAYMENT_STATUS_TRANSITIONS: dict[str, set[str]] = {
    Order.PaymentStatus.UNPAID: {Order.PaymentStatus.READY, Order.PaymentStatus.APPROVED, Order.PaymentStatus.FAILED},
    Order.PaymentStatus.READY: {Order.PaymentStatus.APPROVED, Order.PaymentStatus.FAILED, Order.PaymentStatus.CANCELED},
    Order.PaymentStatus.APPROVED: {Order.PaymentStatus.CANCELED},
    Order.PaymentStatus.CANCELED: set(),
    Order.PaymentStatus.FAILED: {Order.PaymentStatus.READY, Order.PaymentStatus.CANCELED},
}

SHIPPING_STATUS_TRANSITIONS: dict[str, set[str]] = {
    Order.ShippingStatus.READY: {Order.ShippingStatus.PREPARING, Order.ShippingStatus.SHIPPED},
    Order.ShippingStatus.PREPARING: {Order.ShippingStatus.SHIPPED},
    Order.ShippingStatus.SHIPPED: {Order.ShippingStatus.DELIVERED},
    Order.ShippingStatus.DELIVERED: set(),
}

RETURN_STATUS_TRANSITIONS: dict[str, set[str]] = {
    ReturnRequest.Status.REQUESTED: {ReturnRequest.Status.APPROVED, ReturnRequest.Status.REJECTED, ReturnRequest.Status.CLOSED},
    ReturnRequest.Status.APPROVED: {
        ReturnRequest.Status.PICKUP_SCHEDULED,
        ReturnRequest.Status.REJECTED,
        ReturnRequest.Status.CLOSED,
    },
    ReturnRequest.Status.PICKUP_SCHEDULED: {
        ReturnRequest.Status.RECEIVED,
        ReturnRequest.Status.REJECTED,
        ReturnRequest.Status.CLOSED,
    },
    ReturnRequest.Status.RECEIVED: {ReturnRequest.Status.REFUNDING, ReturnRequest.Status.REJECTED, ReturnRequest.Status.CLOSED},
    ReturnRequest.Status.REFUNDING: {ReturnRequest.Status.REFUNDED, ReturnRequest.Status.REJECTED, ReturnRequest.Status.CLOSED},
    ReturnRequest.Status.REFUNDED: {ReturnRequest.Status.CLOSED},
    ReturnRequest.Status.REJECTED: {ReturnRequest.Status.CLOSED},
    ReturnRequest.Status.CLOSED: set(),
}

def _assert_transition(current: str, next_value: str, transition_map: dict[str, set[str]], field_name: str) -> None:
    if current == next_value:
        return
    allowed = transition_map.get(current, set())
    if next_value not in allowed:
        raise ValidationError({field_name: f"상태 전이가 허용되지 않습니다. ({current} -> {next_value})"})


def _derive_product_order_status(order: Order) -> str:
    if order.status == Order.Status.CANCELED and order.payment_status != Order.PaymentStatus.APPROVED:
        return Order.ProductOrderStatus.UNPAID_CANCELED
    if order.status == Order.Status.CANCELED:
        return Order.ProductOrderStatus.CANCELED

    has_return = order.return_requests.filter(
        status__in=[
            ReturnRequest.Status.REQUESTED,
            ReturnRequest.Status.APPROVED,
            ReturnRequest.Status.PICKUP_SCHEDULED,
            ReturnRequest.Status.RECEIVED,
            ReturnRequest.Status.REFUNDING,
            ReturnRequest.Status.REFUNDED,
            ReturnRequest.Status.CLOSED,
        ]
    ).exists()
    if has_return:
        return Order.ProductOrderStatus.RETURNED
    if order.shipping_status == Order.ShippingStatus.SHIPPED:
        return Order.ProductOrderStatus.SHIPPING
    if order.shipping_status == Order.ShippingStatus.DELIVERED:
        return Order.ProductOrderStatus.DELIVERED
    if order.payment_status == Order.PaymentStatus.APPROVED:
        return Order.ProductOrderStatus.PAYMENT_COMPLETED
    return Order.ProductOrderStatus.PAYMENT_PENDING


def _copy_for_audit(instance, fields: tuple[str, ...]) -> dict:
    return {field: getattr(instance, field, None) for field in fields}


def _copy_review_manage_audit(review: Review) -> dict:
    return {
        "is_best": bool(review.is_best),
        "admin_reply": review.admin_reply or "",
        "admin_replied_at": review.admin_replied_at.isoformat() if review.admin_replied_at else None,
        "admin_replied_by_id": review.admin_replied_by_id,
    }


def _log_pii_view_if_needed(request, *, target_type: str, target_id: str = "", metadata: dict | None = None) -> None:
    if has_full_pii_access(request.user):
        log_audit_event(
            request,
            action="PII_FULL_VIEW",
            target_type=target_type,
            target_id=target_id,
            metadata=metadata or {},
        )


def _normalize_badge_types(raw_value) -> list[str]:
    allowed = {choice for choice, _ in ProductBadge.BadgeType.choices}
    values: list[str] = []

    if raw_value is None:
        return values

    if isinstance(raw_value, str):
        values = [item.strip() for item in raw_value.split(",") if item.strip()]
    elif isinstance(raw_value, (list, tuple, set)):
        values = [str(item).strip() for item in raw_value if str(item).strip()]
    else:
        values = [str(raw_value).strip()]

    normalized = []
    for value in values:
        if value in allowed and value not in normalized:
            normalized.append(value)
    return normalized


def _normalize_keyword_values(raw_value) -> list[str]:
    values: list[str] = []

    if raw_value is None:
        return values

    if isinstance(raw_value, str):
        values = [item.strip() for item in raw_value.split(",") if item.strip()]
    elif isinstance(raw_value, (list, tuple, set)):
        for row in raw_value:
            row_value = str(row).strip()
            if not row_value:
                continue
            values.extend([item.strip() for item in row_value.split(",") if item.strip()])
    else:
        row_value = str(raw_value).strip()
        if row_value:
            values.extend([item.strip() for item in row_value.split(",") if item.strip()])

    normalized: list[str] = []
    for value in values:
        if value not in normalized:
            normalized.append(value)
    return normalized


def _normalize_integer_list(raw_value) -> list[int]:
    values: list[int] = []
    if raw_value is None:
        return values

    if isinstance(raw_value, str):
        rows = [item.strip() for item in raw_value.split(",") if item.strip()]
    elif isinstance(raw_value, (list, tuple, set)):
        rows = []
        for item in raw_value:
            item_value = str(item).strip()
            if not item_value:
                continue
            rows.extend([chunk.strip() for chunk in item_value.split(",") if chunk.strip()])
    else:
        rows = [str(raw_value).strip()]

    for row in rows:
        try:
            number = int(row)
        except (TypeError, ValueError):
            continue
        if number <= 0 or number in values:
            continue
        values.append(number)
    return values


def _parse_boolean(value, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}


def _parse_product_package_options(raw_value) -> list[dict] | None:
    if raw_value is None or raw_value == "":
        return None

    parsed = raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValidationError({"package_options_json": "상품구성 옵션 형식이 올바르지 않습니다."}) from exc

    if not isinstance(parsed, list):
        raise ValidationError({"package_options_json": "상품구성 옵션 형식이 올바르지 않습니다."})

    rows: list[dict] = []
    for row in parsed:
        if not isinstance(row, dict):
            raise ValidationError({"package_options_json": "상품구성 옵션 형식이 올바르지 않습니다."})

        duration_months = row.get("duration_months", row.get("durationMonths"))
        if duration_months in {None, ""}:
            raise ValidationError({"package_options_json": "상품구성 기간 정보가 필요합니다."})
        try:
            duration_months_number = int(duration_months)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"package_options_json": "상품구성 기간 정보가 올바르지 않습니다."}) from exc

        price = row.get("price", 0)
        stock = row.get("stock", 0)
        try:
            price_number = max(int(price or 0), 0)
            stock_number = max(int(stock or 0), 0)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"package_options_json": "상품구성 가격/재고 값이 올바르지 않습니다."}) from exc

        rows.append(
            {
                "duration_months": duration_months_number,
                "name": str(row.get("name", "")).strip(),
                "benefit_label": str(row.get("benefit_label", row.get("benefitLabel", ""))).strip(),
                "price": price_number,
                "stock": stock_number,
                "is_active": _parse_boolean(row.get("is_active", row.get("isActive", True)), default=True),
            }
        )

    return rows


def _month_start(base_date: date) -> date:
    return base_date.replace(day=1)


def _shift_month(base_month: date, delta: int) -> date:
    month_index = base_month.year * 12 + (base_month.month - 1) + delta
    year = month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _build_product_payload(data) -> dict:
    payload: dict = {}
    field_pairs = (
        ("category_id", "category_id"),
        ("sku", "sku"),
        ("name", "name"),
        ("one_line", "one_line"),
        ("description", "description"),
        ("intake", "intake"),
        ("target", "target"),
        ("manufacturer", "manufacturer"),
        ("origin_country", "origin_country"),
        ("tax_status", "tax_status"),
        ("delivery_fee", "delivery_fee"),
        ("free_shipping_amount", "free_shipping_amount"),
        ("search_keywords", "search_keywords"),
        ("release_date", "release_date"),
        ("display_start_at", "display_start_at"),
        ("display_end_at", "display_end_at"),
        ("price", "price"),
        ("original_price", "original_price"),
        ("stock", "stock"),
        ("is_active", "is_active"),
        ("thumbnail_image_id", "thumbnail_image_id"),
    )
    nullable_fields = {"category_id", "release_date", "display_start_at", "display_end_at", "thumbnail_image_id"}
    skip_empty_numeric_fields = {"price", "original_price", "stock", "delivery_fee", "free_shipping_amount"}

    for source_field, target_field in field_pairs:
        if hasattr(data, "__contains__"):
            if source_field not in data:
                continue
            value = data.get(source_field)
        else:
            value = data.get(source_field)
            if value is None:
                continue

        if value == "" and target_field in nullable_fields:
            payload[target_field] = None
            continue
        if value == "" and target_field in skip_empty_numeric_fields:
            continue
        payload[target_field] = value

    badge_raw = data.getlist("badge_types") if hasattr(data, "getlist") else data.get("badge_types")
    if isinstance(badge_raw, list) and len(badge_raw) == 1 and "," in str(badge_raw[0]):
        badge_raw = str(badge_raw[0])
    if badge_raw is not None and (not isinstance(badge_raw, list) or badge_raw):
        payload["badge_types"] = _normalize_badge_types(badge_raw)

    keyword_raw = data.getlist("search_keywords") if hasattr(data, "getlist") else data.get("search_keywords")
    if keyword_raw is not None and (not isinstance(keyword_raw, list) or keyword_raw):
        payload["search_keywords"] = _normalize_keyword_values(keyword_raw)

    delete_image_ids_raw = data.getlist("delete_image_ids") if hasattr(data, "getlist") else data.get("delete_image_ids")
    if delete_image_ids_raw is not None and (not isinstance(delete_image_ids_raw, list) or delete_image_ids_raw):
        payload["delete_image_ids"] = _normalize_integer_list(delete_image_ids_raw)

    package_options_json = data.get("package_options_json") if hasattr(data, "get") else None
    package_options_raw = package_options_json
    if package_options_raw is None or package_options_raw == "":
        package_options_raw = data.get("package_options") if hasattr(data, "get") else None
    package_options = _parse_product_package_options(package_options_raw)
    if package_options is not None:
        payload["package_options"] = package_options

    return payload


def _set_product_badges(product: Product, badge_types: list[str]) -> None:
    ProductBadge.objects.filter(product=product).delete()
    ProductBadge.objects.bulk_create(
        [ProductBadge(product=product, badge_type=badge_type) for badge_type in badge_types],
        ignore_conflicts=True,
    )


def _sync_product_images(
    product: Product,
    *,
    thumbnail_file=None,
    image_files: list | None = None,
    delete_image_ids: list[int] | None = None,
    thumbnail_image_id: int | None = None,
) -> None:
    if delete_image_ids:
        product.images.filter(id__in=delete_image_ids).delete()

    if thumbnail_file:
        current_thumbnail = product.images.filter(is_thumbnail=True).order_by("sort_order", "id").first()
        if current_thumbnail:
            current_thumbnail.image = thumbnail_file
            current_thumbnail.sort_order = 0
            current_thumbnail.is_thumbnail = True
            current_thumbnail.save(update_fields=["image", "sort_order", "is_thumbnail"])
        else:
            ProductImage.objects.create(product=product, image=thumbnail_file, is_thumbnail=True, sort_order=0)

    valid_image_files = [row for row in (image_files or []) if row]
    if valid_image_files:
        max_sort = int(product.images.aggregate(max_sort=Coalesce(Max("sort_order"), 0)).get("max_sort") or 0)
        ProductImage.objects.bulk_create(
            [
                ProductImage(
                    product=product,
                    image=image_file,
                    is_thumbnail=False,
                    sort_order=max_sort + index + 1,
                )
                for index, image_file in enumerate(valid_image_files)
            ]
        )

    if thumbnail_image_id is not None:
        target = product.images.filter(id=thumbnail_image_id).first()
        if target:
            product.images.exclude(id=target.id).filter(is_thumbnail=True).update(is_thumbnail=False)
            if not target.is_thumbnail:
                target.is_thumbnail = True
                target.save(update_fields=["is_thumbnail"])

    thumbnail_rows = list(product.images.filter(is_thumbnail=True).order_by("sort_order", "id"))
    if len(thumbnail_rows) > 1:
        keep_id = thumbnail_rows[0].id
        product.images.exclude(id=keep_id).filter(is_thumbnail=True).update(is_thumbnail=False)

    if not product.images.filter(is_thumbnail=True).exists():
        fallback = product.images.order_by("sort_order", "id").first()
        if fallback:
            fallback.is_thumbnail = True
            fallback.sort_order = 0
            fallback.save(update_fields=["is_thumbnail", "sort_order"])


def _sync_product_package_options(
    product: Product,
    *,
    package_options: list[dict] | None = None,
) -> None:
    defaults = [
        build_default_package_option(
            duration_months=duration_months,
            base_price=int(product.price or 0),
            base_stock=int(product.stock or 0),
        )
        for duration_months in PRODUCT_PACKAGE_MONTHS
    ]

    source_rows = package_options or defaults
    row_by_month: dict[int, dict] = {}
    for row in source_rows:
        try:
            duration_months = int(row.get("duration_months"))
        except (TypeError, ValueError):
            continue
        if duration_months not in PRODUCT_PACKAGE_MONTHS:
            continue
        if duration_months in row_by_month:
            continue
        row_by_month[duration_months] = row

    normalized_rows = [row_by_month.get(month) or defaults[idx] for idx, month in enumerate(PRODUCT_PACKAGE_MONTHS)]

    existing_options = list(product.options.all().order_by("id"))
    existing_by_month: dict[int, ProductOption] = {}
    extra_options: list[ProductOption] = []
    for option in existing_options:
        duration_months = (
            int(option.duration_months)
            if option.duration_months in PRODUCT_PACKAGE_MONTHS
            else extract_package_duration_months(option.name)
        )
        if duration_months in PRODUCT_PACKAGE_MONTHS and duration_months not in existing_by_month:
            existing_by_month[duration_months] = option
        else:
            extra_options.append(option)

    for row in normalized_rows:
        duration_months = int(row["duration_months"])
        default_name = build_default_package_option(
            duration_months=duration_months,
            base_price=int(product.price or 0),
            base_stock=int(product.stock or 0),
        )["name"]
        name = str(row.get("name") or "").strip() or default_name
        benefit_label = (
            str(row.get("benefit_label") or "").strip()
            or PRODUCT_PACKAGE_BENEFIT_MAP.get(duration_months, "")
        )
        price = max(int(row.get("price") or 0), 0)
        stock = max(int(row.get("stock") or 0), 0)
        is_active = bool(row.get("is_active", True))

        option = existing_by_month.get(duration_months)
        if option:
            updated_fields: list[str] = []
            if option.duration_months != duration_months:
                option.duration_months = duration_months
                updated_fields.append("duration_months")
            if option.name != name:
                option.name = name
                updated_fields.append("name")
            if option.benefit_label != benefit_label:
                option.benefit_label = benefit_label
                updated_fields.append("benefit_label")
            if option.price != price:
                option.price = price
                updated_fields.append("price")
            if option.stock != stock:
                option.stock = stock
                updated_fields.append("stock")
            if option.is_active != is_active:
                option.is_active = is_active
                updated_fields.append("is_active")
            if updated_fields:
                option.save(update_fields=updated_fields)
            continue

        ProductOption.objects.create(
            product=product,
            duration_months=duration_months,
            name=name,
            benefit_label=benefit_label,
            price=price,
            stock=stock,
            is_active=is_active,
        )

    for option in extra_options:
        updated_fields: list[str] = []
        if option.duration_months is not None:
            option.duration_months = None
            updated_fields.append("duration_months")
        if option.is_active:
            option.is_active = False
            updated_fields.append("is_active")
        if updated_fields:
            option.save(update_fields=updated_fields)


class AdminDashboardAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"GET": {AdminPermission.DASHBOARD_VIEW}}

    def get(self, request, *args, **kwargs):
        orders = Order.objects.all()
        open_return_statuses = [
            ReturnRequest.Status.REQUESTED,
            ReturnRequest.Status.APPROVED,
            ReturnRequest.Status.PICKUP_SCHEDULED,
            ReturnRequest.Status.RECEIVED,
            ReturnRequest.Status.REFUNDING,
        ]
        now = timezone.now()

        current_month = _month_start(timezone.localdate())
        month_keys: list[str] = []
        month_metrics: dict[str, dict] = {}
        month_count = 6
        for offset in range(month_count - 1, -1, -1):
            month_date = _shift_month(current_month, -offset)
            key = month_date.strftime("%Y-%m")
            month_keys.append(key)
            month_metrics[key] = {
                "month": key,
                "order_count": 0,
                "paid_order_count": 0,
                "order_amount": 0,
                "paid_amount": 0,
                "refund_amount": 0,
                "return_request_count": 0,
                "new_user_count": 0,
                "inquiry_count": 0,
            }

        def assign_monthly(rows, field_mappings: dict[str, str]):
            for row in rows:
                month_value = row.get("month")
                if not month_value:
                    continue
                month_date = month_value.date() if hasattr(month_value, "date") else month_value
                key = month_date.strftime("%Y-%m")
                if key not in month_metrics:
                    continue
                target = month_metrics[key]
                for source, target_key in field_mappings.items():
                    target[target_key] = int(row.get(source) or 0)

        assign_monthly(
            orders.annotate(month=TruncMonth("created_at")).values("month").annotate(
                order_count=Count("id"),
                paid_order_count=Count("id", filter=Q(payment_status=Order.PaymentStatus.APPROVED)),
                order_amount=Coalesce(Sum("total_amount"), 0),
                paid_amount=Coalesce(Sum("total_amount", filter=Q(payment_status=Order.PaymentStatus.APPROVED)), 0),
                refund_amount=Coalesce(
                    Sum(
                        "total_amount",
                        filter=Q(status__in=[Order.Status.REFUNDED, Order.Status.PARTIAL_REFUNDED]),
                    ),
                    0,
                ),
            ),
            {
                "order_count": "order_count",
                "paid_order_count": "paid_order_count",
                "order_amount": "order_amount",
                "paid_amount": "paid_amount",
                "refund_amount": "refund_amount",
            },
        )

        assign_monthly(
            ReturnRequest.objects.annotate(month=TruncMonth("requested_at")).values("month").annotate(
                return_request_count=Count("id")
            ),
            {"return_request_count": "return_request_count"},
        )

        assign_monthly(
            User.objects.filter(is_staff=False).annotate(month=TruncMonth("created_at")).values("month").annotate(
                new_user_count=Count("id")
            ),
            {"new_user_count": "new_user_count"},
        )

        assign_monthly(
            OneToOneInquiry.objects.annotate(month=TruncMonth("created_at")).values("month").annotate(
                inquiry_count=Count("id")
            ),
            {"inquiry_count": "inquiry_count"},
        )

        current_month_key = current_month.strftime("%Y-%m")
        current_month_metrics = month_metrics.get(current_month_key, {})

        shipping_pending_count = orders.filter(
            payment_status=Order.PaymentStatus.APPROVED,
            shipping_status__in=[Order.ShippingStatus.READY, Order.ShippingStatus.PREPARING],
        ).count()

        data = {
            "summary": {
                "current_month": current_month_key,
                "this_month_order_count": int(current_month_metrics.get("order_count", 0)),
                "this_month_paid_order_count": int(current_month_metrics.get("paid_order_count", 0)),
                "this_month_order_amount": int(current_month_metrics.get("order_amount", 0)),
                "this_month_paid_amount": int(current_month_metrics.get("paid_amount", 0)),
                "this_month_refund_amount": int(current_month_metrics.get("refund_amount", 0)),
                "this_month_new_user_count": int(current_month_metrics.get("new_user_count", 0)),
                "this_month_inquiry_count": int(current_month_metrics.get("inquiry_count", 0)),
                "shipping_pending_count": shipping_pending_count,
                "shipping_shipped_count": orders.filter(shipping_status=Order.ShippingStatus.SHIPPED).count(),
                "shipping_delivered_count": orders.filter(shipping_status=Order.ShippingStatus.DELIVERED).count(),
                "open_order_count": orders.filter(
                    payment_status=Order.PaymentStatus.APPROVED,
                    shipping_status__in=[
                        Order.ShippingStatus.READY,
                        Order.ShippingStatus.PREPARING,
                        Order.ShippingStatus.SHIPPED,
                    ],
                ).count(),
                "open_inquiry_count": OneToOneInquiry.objects.filter(status=OneToOneInquiry.Status.OPEN).count(),
                "overdue_inquiry_count": OneToOneInquiry.objects.filter(
                    status=OneToOneInquiry.Status.OPEN,
                    sla_due_at__isnull=False,
                    sla_due_at__lt=now,
                ).count(),
                "hidden_review_count": Review.objects.filter(status=Review.Status.HIDDEN).count(),
                "open_return_count": ReturnRequest.objects.filter(status__in=open_return_statuses).count(),
                "completed_return_count": ReturnRequest.objects.filter(status=ReturnRequest.Status.REFUNDED).count(),
            },
            "monthly_metrics": [month_metrics[key] for key in month_keys],
            "status_sectors": {
                "shipping": {
                    "ready": orders.filter(shipping_status=Order.ShippingStatus.READY).count(),
                    "preparing": orders.filter(shipping_status=Order.ShippingStatus.PREPARING).count(),
                    "shipped": orders.filter(shipping_status=Order.ShippingStatus.SHIPPED).count(),
                    "delivered": orders.filter(shipping_status=Order.ShippingStatus.DELIVERED).count(),
                },
                "returns": {
                    "requested": ReturnRequest.objects.filter(status=ReturnRequest.Status.REQUESTED).count(),
                    "approved": ReturnRequest.objects.filter(status=ReturnRequest.Status.APPROVED).count(),
                    "refunding": ReturnRequest.objects.filter(status=ReturnRequest.Status.REFUNDING).count(),
                    "refunded": ReturnRequest.objects.filter(status=ReturnRequest.Status.REFUNDED).count(),
                    "rejected": ReturnRequest.objects.filter(status=ReturnRequest.Status.REJECTED).count(),
                },
                "inquiries": {
                    "open": OneToOneInquiry.objects.filter(status=OneToOneInquiry.Status.OPEN).count(),
                    "answered": OneToOneInquiry.objects.filter(status=OneToOneInquiry.Status.ANSWERED).count(),
                    "closed": OneToOneInquiry.objects.filter(status=OneToOneInquiry.Status.CLOSED).count(),
                },
            },
        }
        return success_response(data)


class AdminOrderListAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"GET": {AdminPermission.ORDER_VIEW}}

    def get(self, request, *args, **kwargs):
        queryset = (
            Order.objects.select_related("user")
            .prefetch_related("items", "return_requests", "payment_transactions", "bank_transfer_requests")
            .order_by("-created_at")
        )

        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(order_no__icontains=q)
                | Q(recipient__icontains=q)
                | Q(phone__icontains=q)
                | Q(user__email__icontains=q)
                | Q(user__name__icontains=q)
                | Q(road_address__icontains=q)
                | Q(jibun_address__icontains=q)
                | Q(detail_address__icontains=q)
            )

        for field in ("status", "payment_status", "shipping_status"):
            value = request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})

        if request.query_params.get("has_open_return") == "true":
            queryset = queryset.filter(
                return_requests__status__in=[
                    ReturnRequest.Status.REQUESTED,
                    ReturnRequest.Status.APPROVED,
                    ReturnRequest.Status.PICKUP_SCHEDULED,
                    ReturnRequest.Status.RECEIVED,
                    ReturnRequest.Status.REFUNDING,
                ]
            ).distinct()

        limit = request.query_params.get("limit", "80")
        try:
            limit_number = min(max(int(limit), 1), 300)
        except (TypeError, ValueError):
            limit_number = 80

        rows = queryset[:limit_number]
        data = AdminOrderSerializer(rows, many=True).data
        if not has_full_pii_access(request.user):
            data = apply_masking_to_orders(data)
        else:
            _log_pii_view_if_needed(
                request,
                target_type="Order",
                metadata={
                    "endpoint": "admin/orders",
                    "count": len(data),
                },
            )
        return success_response(data)


class AdminOrderUpdateAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"PATCH": {AdminPermission.ORDER_UPDATE}}

    def patch(self, request, order_no: str, *args, **kwargs):
        order = get_object_or_404(Order, order_no=order_no)
        serializer = AdminOrderUpdateSerializer(data=request.data, context={"order": order})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        idempotency_key = extract_idempotency_key(request, payload)
        request_hash = build_request_hash({k: v for k, v in payload.items() if k != "idempotency_key"})
        replay_response = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.orders.patch",
            request_hash=request_hash,
        )
        if replay_response is not None:
            return replay_response

        with transaction.atomic():
            order = get_object_or_404(Order.objects.select_for_update(), order_no=order_no)
            serializer = AdminOrderUpdateSerializer(data=request.data, context={"order": order})
            serializer.is_valid(raise_exception=True)
            payload = serializer.validated_data

            before = _copy_for_audit(
                order,
                (
                    "status",
                    "payment_status",
                    "shipping_status",
                    "product_order_status",
                    "courier_name",
                    "tracking_no",
                    "recipient",
                    "phone",
                    "road_address",
                    "jibun_address",
                    "detail_address",
                ),
            )

            now = timezone.now()
            is_updated = False
            status_changed = False

            if "status" in payload:
                _assert_transition(order.status, payload["status"], ORDER_STATUS_TRANSITIONS, "주문")
                if payload["status"] != order.status:
                    status_changed = True
                order.status = payload["status"]
                is_updated = True

            if "payment_status" in payload:
                _assert_transition(
                    order.payment_status,
                    payload["payment_status"],
                    PAYMENT_STATUS_TRANSITIONS,
                    "결제",
                )
                if payload["payment_status"] != order.payment_status:
                    status_changed = True
                order.payment_status = payload["payment_status"]
                is_updated = True

            if "shipping_status" in payload:
                _assert_transition(
                    order.shipping_status,
                    payload["shipping_status"],
                    SHIPPING_STATUS_TRANSITIONS,
                    "배송",
                )
                if payload["shipping_status"] != order.shipping_status:
                    status_changed = True
                order.shipping_status = payload["shipping_status"]
                is_updated = True

            if "product_order_status" in payload:
                if payload["product_order_status"] != order.product_order_status:
                    status_changed = True
                order.product_order_status = payload["product_order_status"]
                is_updated = True
            elif any(key in payload for key in ("status", "payment_status", "shipping_status")):
                next_product_order_status = _derive_product_order_status(order)
                if next_product_order_status != order.product_order_status:
                    order.product_order_status = next_product_order_status
                    status_changed = True
                    is_updated = True

            for field in (
                "recipient",
                "phone",
                "postal_code",
                "road_address",
                "jibun_address",
                "detail_address",
                "courier_name",
                "tracking_no",
            ):
                if field in payload:
                    setattr(order, field, payload[field])
                    is_updated = True

            if payload.get("issue_invoice"):
                if not order.invoice_issued_at:
                    order.invoice_issued_at = now
                if order.shipping_status in {Order.ShippingStatus.READY, Order.ShippingStatus.PREPARING}:
                    _assert_transition(
                        order.shipping_status,
                        Order.ShippingStatus.SHIPPED,
                        SHIPPING_STATUS_TRANSITIONS,
                        "배송",
                    )
                    order.shipping_status = Order.ShippingStatus.SHIPPED
                    status_changed = True
                if not order.shipped_at:
                    order.shipped_at = now
                is_updated = True

            if order.shipping_status == Order.ShippingStatus.SHIPPED and not order.shipped_at:
                order.shipped_at = now
                is_updated = True

            if payload.get("mark_delivered"):
                _assert_transition(
                    order.shipping_status,
                    Order.ShippingStatus.DELIVERED,
                    SHIPPING_STATUS_TRANSITIONS,
                    "배송",
                )
                order.shipping_status = Order.ShippingStatus.DELIVERED
                order.delivered_at = now
                status_changed = True
                is_updated = True
            elif order.shipping_status == Order.ShippingStatus.DELIVERED and not order.delivered_at:
                order.delivered_at = now
                is_updated = True

            if not is_updated:
                return error_response("NO_UPDATE_FIELDS", "변경할 값이 없습니다.", status_code=status.HTTP_400_BAD_REQUEST)

            order.save()

            refreshed = (
                Order.objects.select_related("user")
                .prefetch_related("items", "return_requests")
                .get(id=order.id)
            )
            response_data = AdminOrderSerializer(refreshed).data
            if not has_full_pii_access(request.user):
                response_data = apply_masking_to_orders(response_data)
            else:
                _log_pii_view_if_needed(
                    request,
                    target_type="Order",
                    target_id=str(order.order_no),
                    metadata={"endpoint": "admin/orders/{order_no}"},
                )

            response = success_response(response_data, message="주문/배송 정보가 업데이트되었습니다.")
            save_idempotent_response(
                request=request,
                key=idempotency_key,
                action="admin.orders.patch",
                request_hash=request_hash,
                response=response,
                target_type="Order",
                target_id=str(order.order_no),
            )
            if status_changed:
                log_audit_event(
                    request,
                    action="ORDER_STATUS_CHANGED",
                    target_type="Order",
                    target_id=str(order.order_no),
                    before=before,
                    after=_copy_for_audit(
                        order,
                        (
                            "status",
                            "payment_status",
                            "shipping_status",
                            "product_order_status",
                            "courier_name",
                            "tracking_no",
                            "recipient",
                            "phone",
                            "road_address",
                            "jibun_address",
                            "detail_address",
                        ),
                    ),
                    idempotency_key=idempotency_key,
                )
            return response


class AdminInquiryListAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"GET": {AdminPermission.INQUIRY_VIEW}}

    def get(self, request, *args, **kwargs):
        queryset = OneToOneInquiry.objects.select_related("user", "assigned_admin").order_by("-created_at")

        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q)
                | Q(content__icontains=q)
                | Q(user__email__icontains=q)
                | Q(user__name__icontains=q)
            )

        for field in ("status", "category", "priority"):
            value = request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})

        assigned_admin_id = request.query_params.get("assigned_admin_id")
        if assigned_admin_id and str(assigned_admin_id).isdigit():
            queryset = queryset.filter(assigned_admin_id=int(assigned_admin_id))

        if request.query_params.get("overdue") == "true":
            queryset = queryset.filter(
                status=OneToOneInquiry.Status.OPEN,
                sla_due_at__isnull=False,
                sla_due_at__lt=timezone.now(),
            )

        limit = request.query_params.get("limit", "200")
        try:
            limit_number = min(max(int(limit), 1), 500)
        except (TypeError, ValueError):
            limit_number = 200

        data = AdminInquirySerializer(queryset[:limit_number], many=True).data
        if not has_full_pii_access(request.user):
            data = apply_masking_to_inquiries(data)
        else:
            _log_pii_view_if_needed(
                request,
                target_type="Inquiry",
                metadata={
                    "endpoint": "admin/inquiries",
                    "count": len(data),
                },
            )
        return success_response(data)


class AdminInquiryAnswerAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"PATCH": {AdminPermission.INQUIRY_UPDATE}}

    def patch(self, request, inquiry_id: int, *args, **kwargs):
        inquiry = get_object_or_404(OneToOneInquiry, id=inquiry_id)
        serializer = AdminInquiryAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        idempotency_key = extract_idempotency_key(request, payload)
        request_hash = build_request_hash({k: v for k, v in payload.items() if k != "idempotency_key"})
        replay_response = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.inquiries.patch",
            request_hash=request_hash,
        )
        if replay_response is not None:
            return replay_response

        before = _copy_for_audit(
            inquiry,
            (
                "status",
                "category",
                "priority",
                "assigned_admin_id",
                "answer",
                "internal_note",
                "sla_due_at",
            ),
        )
        delete_answer = bool(payload.pop("delete_answer", False))

        updated_fields = ["updated_at"]
        now = timezone.now()

        if delete_answer:
            inquiry.answer = ""
            updated_fields.append("answer")
            if "status" not in payload:
                inquiry.status = OneToOneInquiry.Status.OPEN
                updated_fields.append("status")
            if inquiry.answered_at is not None:
                inquiry.answered_at = None
                updated_fields.append("answered_at")
            if inquiry.resolved_at is not None:
                inquiry.resolved_at = None
                updated_fields.append("resolved_at")

        if "answer" in payload:
            inquiry.answer = payload["answer"]
            updated_fields.append("answer")
            if payload["answer"] and not inquiry.first_response_at:
                inquiry.first_response_at = now
                updated_fields.append("first_response_at")
            if (
                payload["answer"]
                and inquiry.status == OneToOneInquiry.Status.OPEN
                and "status" not in payload
                and not delete_answer
            ):
                inquiry.status = OneToOneInquiry.Status.ANSWERED
                updated_fields.append("status")

        if "status" in payload:
            inquiry.status = payload["status"]
            updated_fields.append("status")

        if "category" in payload:
            inquiry.category = payload["category"]
            updated_fields.append("category")

        if "priority" in payload:
            inquiry.priority = payload["priority"]
            updated_fields.append("priority")

        if "internal_note" in payload:
            inquiry.internal_note = payload["internal_note"]
            updated_fields.append("internal_note")

        if "sla_due_at" in payload:
            inquiry.sla_due_at = payload["sla_due_at"]
            updated_fields.append("sla_due_at")

        if "assigned_admin_id" in payload:
            assigned_admin_id = payload.get("assigned_admin_id")
            inquiry.assigned_admin = User.objects.filter(id=assigned_admin_id).first() if assigned_admin_id else None
            updated_fields.append("assigned_admin")

        if inquiry.status == OneToOneInquiry.Status.OPEN:
            inquiry.resolved_at = None
            updated_fields.append("resolved_at")
        elif inquiry.status == OneToOneInquiry.Status.ANSWERED:
            if not inquiry.answered_at:
                inquiry.answered_at = now
                updated_fields.append("answered_at")
            inquiry.resolved_at = None
            updated_fields.append("resolved_at")
        elif inquiry.status == OneToOneInquiry.Status.CLOSED:
            if not inquiry.answered_at:
                inquiry.answered_at = now
                updated_fields.append("answered_at")
            if not inquiry.resolved_at:
                inquiry.resolved_at = now
                updated_fields.append("resolved_at")

        inquiry.save(update_fields=list(dict.fromkeys(updated_fields)))
        response_data = AdminInquirySerializer(inquiry).data
        if not has_full_pii_access(request.user):
            response_data = apply_masking_to_inquiries(response_data)
        else:
            _log_pii_view_if_needed(
                request,
                target_type="Inquiry",
                target_id=str(inquiry.id),
                metadata={"endpoint": "admin/inquiries/{id}/answer"},
            )

        response = success_response(response_data, message="CS 문의가 업데이트되었습니다.")
        save_idempotent_response(
            request=request,
            key=idempotency_key,
            action="admin.inquiries.patch",
            request_hash=request_hash,
            response=response,
            target_type="Inquiry",
            target_id=str(inquiry.id),
        )
        log_audit_event(
            request,
            action="INQUIRY_UPDATED",
            target_type="Inquiry",
            target_id=str(inquiry.id),
            before=before,
            after=_copy_for_audit(
                inquiry,
                (
                    "status",
                    "category",
                    "priority",
                    "assigned_admin_id",
                    "answer",
                    "internal_note",
                    "sla_due_at",
                ),
            ),
            idempotency_key=idempotency_key,
        )
        return response


class AdminSupportNoticeListCreateAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "GET": {AdminPermission.INQUIRY_VIEW},
        "POST": {AdminPermission.INQUIRY_UPDATE},
    }

    def get(self, request, *args, **kwargs):
        queryset = SupportNotice.objects.all().order_by("-is_pinned", "-published_at", "-id")

        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(content__icontains=q))

        is_active = request.query_params.get("is_active")
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))

        data = AdminSupportNoticeSerializer(queryset[:300], many=True).data
        return success_response(data)

    def post(self, request, *args, **kwargs):
        serializer = AdminSupportNoticeUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        title = str(payload.get("title", "")).strip()
        content = str(payload.get("content", "")).strip()
        if not title or not content:
            raise ValidationError({"detail": "제목과 내용을 모두 입력해주세요."})

        notice = SupportNotice.objects.create(
            title=title,
            content=content,
            is_pinned=bool(payload.get("is_pinned", False)),
            is_active=bool(payload.get("is_active", True)),
            published_at=payload.get("published_at") or timezone.now(),
        )

        data = AdminSupportNoticeSerializer(notice).data
        log_audit_event(
            request,
            action="SUPPORT_NOTICE_CREATED",
            target_type="SupportNotice",
            target_id=str(notice.id),
            after=data,
        )
        return success_response(data, message="공지사항이 등록되었습니다.", status_code=status.HTTP_201_CREATED)


class AdminSupportNoticeDetailAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "PATCH": {AdminPermission.INQUIRY_UPDATE},
        "DELETE": {AdminPermission.INQUIRY_UPDATE},
    }

    def patch(self, request, notice_id: int, *args, **kwargs):
        notice = get_object_or_404(SupportNotice, id=notice_id)
        serializer = AdminSupportNoticeUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        before = AdminSupportNoticeSerializer(notice).data
        updated_fields: list[str] = []
        for field in ("title", "content", "is_pinned", "is_active", "published_at"):
            if field in payload:
                setattr(notice, field, payload[field])
                updated_fields.append(field)

        if "is_active" in payload and payload["is_active"] and "published_at" not in payload and not notice.published_at:
            notice.published_at = timezone.now()
            updated_fields.append("published_at")

        if not updated_fields:
            raise ValidationError({"detail": "변경할 값을 하나 이상 전달해주세요."})

        notice.save(update_fields=list(dict.fromkeys([*updated_fields, "updated_at"])))
        data = AdminSupportNoticeSerializer(notice).data
        log_audit_event(
            request,
            action="SUPPORT_NOTICE_UPDATED",
            target_type="SupportNotice",
            target_id=str(notice.id),
            before=before,
            after=data,
        )
        return success_response(data, message="공지사항이 수정되었습니다.")

    def delete(self, request, notice_id: int, *args, **kwargs):
        notice = get_object_or_404(SupportNotice, id=notice_id)
        before = AdminSupportNoticeSerializer(notice).data
        notice.delete()
        log_audit_event(
            request,
            action="SUPPORT_NOTICE_DELETED",
            target_type="SupportNotice",
            target_id=str(notice_id),
            before=before,
        )
        return success_response(message="공지사항이 삭제되었습니다.")


class AdminSupportFaqListCreateAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "GET": {AdminPermission.INQUIRY_VIEW},
        "POST": {AdminPermission.INQUIRY_UPDATE},
    }

    def get(self, request, *args, **kwargs):
        queryset = SupportFaq.objects.all().order_by("category", "sort_order", "id")

        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(Q(question__icontains=q) | Q(answer__icontains=q))

        category = request.query_params.get("category", "").strip()
        if category:
            queryset = queryset.filter(category=category)

        is_active = request.query_params.get("is_active")
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))

        data = AdminSupportFaqSerializer(queryset[:500], many=True).data
        return success_response(data)

    def post(self, request, *args, **kwargs):
        serializer = AdminSupportFaqUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        question = str(payload.get("question", "")).strip()
        answer = str(payload.get("answer", "")).strip()
        if not question or not answer:
            raise ValidationError({"detail": "질문과 답변을 모두 입력해주세요."})

        faq = SupportFaq.objects.create(
            category=str(payload.get("category", "일반")).strip() or "일반",
            question=question,
            answer=answer,
            sort_order=int(payload.get("sort_order", 0)),
            is_active=bool(payload.get("is_active", True)),
        )

        data = AdminSupportFaqSerializer(faq).data
        log_audit_event(
            request,
            action="SUPPORT_FAQ_CREATED",
            target_type="SupportFaq",
            target_id=str(faq.id),
            after=data,
        )
        return success_response(data, message="FAQ가 등록되었습니다.", status_code=status.HTTP_201_CREATED)


class AdminSupportFaqDetailAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "PATCH": {AdminPermission.INQUIRY_UPDATE},
        "DELETE": {AdminPermission.INQUIRY_UPDATE},
    }

    def patch(self, request, faq_id: int, *args, **kwargs):
        faq = get_object_or_404(SupportFaq, id=faq_id)
        serializer = AdminSupportFaqUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        before = AdminSupportFaqSerializer(faq).data
        updated_fields: list[str] = []
        for field in ("category", "question", "answer", "sort_order", "is_active"):
            if field in payload:
                setattr(faq, field, payload[field])
                updated_fields.append(field)

        if not updated_fields:
            raise ValidationError({"detail": "변경할 값을 하나 이상 전달해주세요."})

        faq.save(update_fields=list(dict.fromkeys([*updated_fields, "updated_at"])))
        data = AdminSupportFaqSerializer(faq).data
        log_audit_event(
            request,
            action="SUPPORT_FAQ_UPDATED",
            target_type="SupportFaq",
            target_id=str(faq.id),
            before=before,
            after=data,
        )
        return success_response(data, message="FAQ가 수정되었습니다.")

    def delete(self, request, faq_id: int, *args, **kwargs):
        faq = get_object_or_404(SupportFaq, id=faq_id)
        before = AdminSupportFaqSerializer(faq).data
        faq.delete()
        log_audit_event(
            request,
            action="SUPPORT_FAQ_DELETED",
            target_type="SupportFaq",
            target_id=str(faq_id),
            before=before,
        )
        return success_response(message="FAQ가 삭제되었습니다.")


class AdminReviewListAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"GET": {AdminPermission.REVIEW_VIEW}}

    def get(self, request, *args, **kwargs):
        queryset = (
            Review.objects.select_related("user", "product", "admin_replied_by")
            .prefetch_related("images")
            .annotate(
                report_total_count=Count("reports", distinct=True),
                report_pending_count=Count(
                    "reports",
                    filter=Q(reports__status=ReviewReport.Status.PENDING),
                    distinct=True,
                ),
                last_reported_at=Max("reports__created_at"),
            )
        )

        status_value = request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)

        product_id = request.query_params.get("product_id")
        if product_id and str(product_id).isdigit():
            queryset = queryset.filter(product_id=int(product_id))

        best_only = str(request.query_params.get("best_only", "")).lower()
        if best_only in {"true", "1", "yes", "y"}:
            queryset = queryset.filter(is_best=True)

        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(content__icontains=q)
                | Q(title__icontains=q)
                | Q(user__email__icontains=q)
                | Q(user__name__icontains=q)
                | Q(product__name__icontains=q)
            )

        sort = request.query_params.get("sort", "latest")
        if sort == "score_asc":
            queryset = queryset.order_by("score", "-created_at")
        else:
            queryset = queryset.order_by("-created_at")

        page_size = request.query_params.get("page_size", "10")
        page_number = request.query_params.get("page", "1")

        try:
            page_size_value = min(max(int(page_size), 1), 100)
        except (TypeError, ValueError):
            page_size_value = 10

        try:
            page_number_value = max(int(page_number), 1)
        except (TypeError, ValueError):
            page_number_value = 1

        paginator = Paginator(queryset, page_size_value)
        if paginator.count == 0:
            return success_response(
                {
                    "count": 0,
                    "page": 1,
                    "page_size": page_size_value,
                    "total_pages": 1,
                    "has_next": False,
                    "has_previous": False,
                    "results": [],
                }
            )

        try:
            page_obj = paginator.page(page_number_value)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages or 1)

        rows = AdminReviewSerializer(page_obj.object_list, many=True, context={"request": request}).data
        if not has_full_pii_access(request.user):
            rows = apply_masking_to_inquiries(rows)
        else:
            _log_pii_view_if_needed(
                request,
                target_type="Review",
                metadata={"endpoint": "admin/reviews", "count": len(rows)},
            )
        return success_response(
            {
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size_value,
                "total_pages": paginator.num_pages,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
                "results": rows,
            }
        )


class AdminReviewVisibilityAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"PATCH": {AdminPermission.REVIEW_UPDATE}}

    def patch(self, request, review_id: int, *args, **kwargs):
        serializer = AdminReviewVisibilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        idempotency_key = extract_idempotency_key(request, payload)
        request_hash = build_request_hash({"visible": payload.get("visible")})
        replay_response = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.reviews.visibility.patch",
            request_hash=request_hash,
        )
        if replay_response is not None:
            return replay_response

        review = get_object_or_404(Review.objects.select_related("product"), id=review_id)
        visible = payload["visible"]
        next_status = Review.Status.VISIBLE if visible else Review.Status.HIDDEN

        before = {"status": review.status}
        if review.status != next_status:
            review.status = next_status
            review.save(update_fields=["status", "updated_at"])
            refresh_product_rating(review.product)

        response = success_response(
            AdminReviewSerializer(review, context={"request": request}).data,
            message="리뷰 노출 상태가 변경되었습니다.",
        )
        save_idempotent_response(
            request=request,
            key=idempotency_key,
            action="admin.reviews.visibility.patch",
            request_hash=request_hash,
            response=response,
            target_type="Review",
            target_id=str(review.id),
        )
        log_audit_event(
            request,
            action="REVIEW_STATUS_CHANGED",
            target_type="Review",
            target_id=str(review.id),
            before=before,
            after={"status": review.status},
            idempotency_key=idempotency_key,
        )
        return response


class AdminReviewManageAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"PATCH": {AdminPermission.REVIEW_UPDATE}}

    def patch(self, request, review_id: int, *args, **kwargs):
        serializer = AdminReviewManageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        idempotency_key = extract_idempotency_key(request, payload)
        request_hash = build_request_hash({k: v for k, v in payload.items() if k != "idempotency_key"})
        replay_response = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.reviews.manage.patch",
            request_hash=request_hash,
        )
        if replay_response is not None:
            return replay_response

        review = get_object_or_404(Review.objects.select_related("admin_replied_by"), id=review_id)
        before = _copy_review_manage_audit(review)
        changed_fields: list[str] = []

        if "is_best" in payload:
            is_best = bool(payload["is_best"])
            if review.is_best != is_best:
                review.is_best = is_best
                changed_fields.append("is_best")

        if payload.get("delete_answer"):
            if review.admin_reply or review.admin_replied_at or review.admin_replied_by_id:
                review.admin_reply = ""
                review.admin_replied_at = None
                review.admin_replied_by = None
                changed_fields.extend(["admin_reply", "admin_replied_at", "admin_replied_by"])
        elif "answer" in payload:
            answer = str(payload.get("answer") or "").strip()
            if answer:
                reply_changed = (
                    review.admin_reply != answer
                    or review.admin_replied_by_id != request.user.id
                    or review.admin_replied_at is None
                )
                if reply_changed:
                    review.admin_reply = answer
                    review.admin_replied_at = timezone.now()
                    review.admin_replied_by = request.user
                    changed_fields.extend(["admin_reply", "admin_replied_at", "admin_replied_by"])
            else:
                if review.admin_reply or review.admin_replied_at or review.admin_replied_by_id:
                    review.admin_reply = ""
                    review.admin_replied_at = None
                    review.admin_replied_by = None
                    changed_fields.extend(["admin_reply", "admin_replied_at", "admin_replied_by"])

        if changed_fields:
            review.save(update_fields=list(dict.fromkeys([*changed_fields, "updated_at"])))

        response_data = AdminReviewSerializer(review, context={"request": request}).data
        if not has_full_pii_access(request.user):
            response_data = apply_masking_to_inquiries(response_data)
        else:
            _log_pii_view_if_needed(
                request,
                target_type="Review",
                target_id=str(review.id),
                metadata={"endpoint": "admin/reviews/{id}/manage"},
            )

        response = success_response(response_data, message="리뷰 설정이 저장되었습니다.")
        save_idempotent_response(
            request=request,
            key=idempotency_key,
            action="admin.reviews.manage.patch",
            request_hash=request_hash,
            response=response,
            target_type="Review",
            target_id=str(review.id),
        )
        log_audit_event(
            request,
            action="REVIEW_MANAGED",
            target_type="Review",
            target_id=str(review.id),
            before=before,
            after=_copy_review_manage_audit(review),
            metadata={"fields": list(dict.fromkeys(changed_fields))},
            idempotency_key=idempotency_key,
        )
        return response


class AdminReviewReportManageAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"PATCH": {AdminPermission.REVIEW_UPDATE}}

    def patch(self, request, review_id: int, *args, **kwargs):
        serializer = AdminReviewReportManageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        action = payload["action"]
        next_status = ReviewReport.Status.RESOLVED if action == "RESOLVE" else ReviewReport.Status.REJECTED

        idempotency_key = extract_idempotency_key(request, payload)
        request_hash = build_request_hash({"action": action})
        replay_response = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.reviews.reports.patch",
            request_hash=request_hash,
        )
        if replay_response is not None:
            return replay_response

        review = get_object_or_404(Review, id=review_id)
        pending_queryset = ReviewReport.objects.filter(review_id=review.id, status=ReviewReport.Status.PENDING)
        before_pending_count = pending_queryset.count()

        if before_pending_count:
            now = timezone.now()
            pending_queryset.update(
                status=next_status,
                handled_at=now,
                handled_by=request.user,
                updated_at=now,
            )

        review_row = (
            Review.objects.select_related("user", "product", "admin_replied_by")
            .prefetch_related("images")
            .annotate(
                report_total_count=Count("reports", distinct=True),
                report_pending_count=Count(
                    "reports",
                    filter=Q(reports__status=ReviewReport.Status.PENDING),
                    distinct=True,
                ),
                last_reported_at=Max("reports__created_at"),
            )
            .get(id=review.id)
        )
        response_data = AdminReviewSerializer(review_row, context={"request": request}).data
        if not has_full_pii_access(request.user):
            response_data = apply_masking_to_inquiries(response_data)
        else:
            _log_pii_view_if_needed(
                request,
                target_type="Review",
                target_id=str(review.id),
                metadata={"endpoint": "admin/reviews/{id}/reports"},
            )

        response = success_response(response_data, message="리뷰 신고 처리 상태가 저장되었습니다.")
        save_idempotent_response(
            request=request,
            key=idempotency_key,
            action="admin.reviews.reports.patch",
            request_hash=request_hash,
            response=response,
            target_type="Review",
            target_id=str(review.id),
        )

        after_pending_count = ReviewReport.objects.filter(review_id=review.id, status=ReviewReport.Status.PENDING).count()
        log_audit_event(
            request,
            action="REVIEW_REPORTS_HANDLED",
            target_type="Review",
            target_id=str(review.id),
            before={"pending_reports": before_pending_count},
            after={"pending_reports": after_pending_count, "applied_status": next_status},
            metadata={"action": action},
            idempotency_key=idempotency_key,
        )
        return response


class AdminReviewDeleteAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"DELETE": {AdminPermission.REVIEW_UPDATE}}

    def delete(self, request, review_id: int, *args, **kwargs):
        idempotency_key = extract_idempotency_key(request, {})
        request_hash = build_request_hash({"review_id": review_id, "method": "DELETE"})
        replay_response = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.reviews.delete",
            request_hash=request_hash,
        )
        if replay_response is not None:
            return replay_response

        review = get_object_or_404(Review.objects.select_related("product"), id=review_id)
        before = {"status": review.status}
        if review.status != Review.Status.DELETED:
            review.status = Review.Status.DELETED
            review.save(update_fields=["status", "updated_at"])
            refresh_product_rating(review.product)
        response = success_response(message="리뷰가 삭제 처리되었습니다.")
        save_idempotent_response(
            request=request,
            key=idempotency_key,
            action="admin.reviews.delete",
            request_hash=request_hash,
            response=response,
            target_type="Review",
            target_id=str(review.id),
        )
        log_audit_event(
            request,
            action="REVIEW_DELETED",
            target_type="Review",
            target_id=str(review.id),
            before=before,
            after={"status": review.status},
            idempotency_key=idempotency_key,
        )
        return response


class AdminReturnRequestListCreateAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "GET": {AdminPermission.RETURN_VIEW},
        "POST": {AdminPermission.RETURN_UPDATE},
    }

    def get(self, request, *args, **kwargs):
        queryset = ReturnRequest.objects.select_related("order", "user").order_by("-requested_at")

        status_value = request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)

        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(order__order_no__icontains=q)
                | Q(reason_title__icontains=q)
                | Q(user__email__icontains=q)
                | Q(order__recipient__icontains=q)
            )

        limit = request.query_params.get("limit", "200")
        try:
            limit_number = min(max(int(limit), 1), 500)
        except (TypeError, ValueError):
            limit_number = 200

        data = AdminReturnRequestSerializer(queryset[:limit_number], many=True).data
        if not has_full_pii_access(request.user):
            data = apply_masking_to_returns(data)
        else:
            _log_pii_view_if_needed(
                request,
                target_type="ReturnRequest",
                metadata={"endpoint": "admin/returns", "count": len(data)},
            )
        return success_response(data)

    def post(self, request, *args, **kwargs):
        serializer = AdminReturnRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        idempotency_key = extract_idempotency_key(request, payload)
        request_hash = build_request_hash({k: v for k, v in payload.items() if k != "idempotency_key"})
        replay_response = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.returns.create",
            request_hash=request_hash,
        )
        if replay_response is not None:
            return replay_response

        with transaction.atomic():
            order = get_object_or_404(Order.objects.select_for_update(), order_no=payload["order_no"])
            requested_amount = payload.get("requested_amount")
            if requested_amount is None:
                requested_amount = int(order.total_amount or 0)

            return_request = ReturnRequest.objects.create(
                order=order,
                user=order.user,
                reason_title=payload["reason_title"],
                reason_detail=payload.get("reason_detail", ""),
                requested_amount=requested_amount,
            )

        response_data = AdminReturnRequestSerializer(return_request).data
        if not has_full_pii_access(request.user):
            response_data = apply_masking_to_returns(response_data)
        else:
            _log_pii_view_if_needed(
                request,
                target_type="ReturnRequest",
                target_id=str(return_request.id),
                metadata={"endpoint": "admin/returns"},
            )

        response = success_response(
            response_data,
            message="반품/환불 요청이 등록되었습니다.",
            status_code=status.HTTP_201_CREATED,
        )
        save_idempotent_response(
            request=request,
            key=idempotency_key,
            action="admin.returns.create",
            request_hash=request_hash,
            response=response,
            target_type="ReturnRequest",
            target_id=str(return_request.id),
        )
        log_audit_event(
            request,
            action="RETURN_REQUEST_CREATED",
            target_type="ReturnRequest",
            target_id=str(return_request.id),
            after={
                "status": return_request.status,
                "requested_amount": return_request.requested_amount,
                "order_no": order.order_no,
            },
            idempotency_key=idempotency_key,
        )
        return response


class AdminReturnRequestUpdateAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "PATCH": {AdminPermission.RETURN_UPDATE},
        "DELETE": {AdminPermission.RETURN_UPDATE},
    }

    def patch(self, request, return_request_id: int, *args, **kwargs):
        serializer = AdminReturnRequestUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        idempotency_key = extract_idempotency_key(request, payload)
        request_hash = build_request_hash({k: v for k, v in payload.items() if k != "idempotency_key"})
        replay_response = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.returns.patch",
            request_hash=request_hash,
        )
        if replay_response is not None:
            return replay_response

        with transaction.atomic():
            row = get_object_or_404(
                ReturnRequest.objects.select_related("order", "user").select_for_update(),
                id=return_request_id,
            )
            before = _copy_for_audit(
                row,
                (
                    "status",
                    "approved_amount",
                    "rejected_reason",
                    "pickup_courier_name",
                    "pickup_tracking_no",
                    "admin_note",
                ),
            )
            now = timezone.now()
            updated_fields = ["updated_at"]

            for field in ("approved_amount", "rejected_reason", "pickup_courier_name", "pickup_tracking_no", "admin_note"):
                if field in payload:
                    setattr(row, field, payload[field])
                    updated_fields.append(field)

            if "status" in payload:
                next_status = payload["status"]
                _assert_transition(row.status, next_status, RETURN_STATUS_TRANSITIONS, "반품")
                if next_status in {ReturnRequest.Status.REFUNDING, ReturnRequest.Status.REFUNDED}:
                    require_admin_permission(request.user, AdminPermission.REFUND_EXECUTE)

                row.status = next_status
                updated_fields.append("status")

                if row.status == ReturnRequest.Status.APPROVED and not row.approved_at:
                    row.approved_at = now
                    updated_fields.append("approved_at")
                if row.status == ReturnRequest.Status.RECEIVED and not row.received_at:
                    row.received_at = now
                    updated_fields.append("received_at")
                if row.status == ReturnRequest.Status.REFUNDED and not row.refunded_at:
                    row.refunded_at = now
                    updated_fields.append("refunded_at")
                if row.status in {ReturnRequest.Status.REJECTED, ReturnRequest.Status.CLOSED} and not row.closed_at:
                    row.closed_at = now
                    updated_fields.append("closed_at")

            row.save(update_fields=list(dict.fromkeys(updated_fields)))

            order = row.order
            if row.status == ReturnRequest.Status.REFUNDED:
                refund_amount = int(row.approved_amount or row.requested_amount or 0)
                if refund_amount >= int(order.total_amount or 0):
                    order.status = Order.Status.REFUNDED
                else:
                    order.status = Order.Status.PARTIAL_REFUNDED
                order.payment_status = Order.PaymentStatus.CANCELED
                order.product_order_status = Order.ProductOrderStatus.RETURNED
                order.save(update_fields=["status", "payment_status", "product_order_status", "updated_at"])

            refreshed = ReturnRequest.objects.select_related("order", "user").get(id=row.id)
            response_data = AdminReturnRequestSerializer(refreshed).data
            if not has_full_pii_access(request.user):
                response_data = apply_masking_to_returns(response_data)
            else:
                _log_pii_view_if_needed(
                    request,
                    target_type="ReturnRequest",
                    target_id=str(row.id),
                    metadata={"endpoint": "admin/returns/{id}"},
                )

            response = success_response(
                response_data,
                message="반품/환불 요청이 업데이트되었습니다.",
            )
            save_idempotent_response(
                request=request,
                key=idempotency_key,
                action="admin.returns.patch",
                request_hash=request_hash,
                response=response,
                target_type="ReturnRequest",
                target_id=str(row.id),
            )
            log_audit_event(
                request,
                action="RETURN_STATUS_CHANGED",
                target_type="ReturnRequest",
                target_id=str(row.id),
                before=before,
                after=_copy_for_audit(
                    row,
                    (
                        "status",
                        "approved_amount",
                        "rejected_reason",
                        "pickup_courier_name",
                        "pickup_tracking_no",
                        "admin_note",
                    ),
                ),
                idempotency_key=idempotency_key,
            )
            if row.status == ReturnRequest.Status.REFUNDED:
                log_audit_event(
                    request,
                    action="REFUND_EXECUTED",
                    target_type="ReturnRequest",
                    target_id=str(row.id),
                    metadata={
                        "order_no": order.order_no,
                        "refund_amount": int(row.approved_amount or row.requested_amount or 0),
                    },
                    idempotency_key=idempotency_key,
                )
            return response

    def delete(self, request, return_request_id: int, *args, **kwargs):
        idempotency_key = extract_idempotency_key(request, {})
        request_hash = build_request_hash({"return_request_id": return_request_id, "method": "DELETE"})
        replay_response = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.returns.delete",
            request_hash=request_hash,
        )
        if replay_response is not None:
            return replay_response

        with transaction.atomic():
            row = get_object_or_404(ReturnRequest.objects.select_related("order").select_for_update(), id=return_request_id)
            order = row.order
            before = _copy_for_audit(
                row,
                (
                    "status",
                    "approved_amount",
                    "rejected_reason",
                    "pickup_courier_name",
                    "pickup_tracking_no",
                    "admin_note",
                ),
            )
            row_id = row.id
            row.delete()

            response = success_response(message="반품/환불 요청이 삭제되었습니다.")
            save_idempotent_response(
                request=request,
                key=idempotency_key,
                action="admin.returns.delete",
                request_hash=request_hash,
                response=response,
                target_type="ReturnRequest",
                target_id=str(row_id),
            )
            log_audit_event(
                request,
                action="RETURN_REQUEST_DELETED",
                target_type="ReturnRequest",
                target_id=str(row_id),
                before=before,
                idempotency_key=idempotency_key,
            )
            return response


class AdminCouponListCreateAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "GET": {AdminPermission.COUPON_VIEW},
        "POST": {AdminPermission.COUPON_UPDATE},
    }

    def get(self, request, *args, **kwargs):
        queryset = UserCoupon.objects.select_related("user").order_by("-created_at")

        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(Q(user__email__icontains=q) | Q(code__icontains=q) | Q(name__icontains=q))

        used = request.query_params.get("is_used")
        if used in {"true", "false"}:
            queryset = queryset.filter(is_used=(used == "true"))

        return success_response(AdminCouponSerializer(queryset[:200], many=True).data)

    def post(self, request, *args, **kwargs):
        serializer = AdminCouponIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        users = []
        if payload["target"] == AdminCouponIssueSerializer.TARGET_EMAIL:
            users = list(User.objects.filter(email=payload["email"], is_active=True))
            if not users:
                return error_response(
                    "USER_NOT_FOUND",
                    "해당 이메일의 회원을 찾을 수 없습니다.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
        else:
            users = list(User.objects.filter(is_active=True, is_staff=False).order_by("id"))
            if not users:
                return error_response(
                    "USER_NOT_FOUND",
                    "쿠폰을 발급할 일반 회원이 없습니다.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )

        issued_rows = []
        defaults = {
            "name": payload["name"],
            "discount_amount": payload["discount_amount"],
            "min_order_amount": payload.get("min_order_amount", 0),
            "expires_at": payload.get("expires_at"),
            "is_used": False,
            "used_at": None,
        }

        for user in users:
            row, _ = UserCoupon.objects.update_or_create(
                user=user,
                code=payload["code"],
                defaults=defaults,
            )
            issued_rows.append(row)

        return success_response(
            {
                "issued_count": len(issued_rows),
                "coupons": AdminCouponSerializer(issued_rows[:30], many=True).data,
            },
            message="쿠폰이 발급되었습니다.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminCouponDetailAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"DELETE": {AdminPermission.COUPON_UPDATE}}

    def delete(self, request, coupon_id: int, *args, **kwargs):
        coupon = get_object_or_404(UserCoupon, id=coupon_id)
        coupon.delete()
        return success_response(message="쿠폰이 삭제되었습니다.")


class AdminStaffUserListAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"GET": {AdminPermission.STAFF_VIEW}}

    def get(self, request, *args, **kwargs):
        rows = list(
            User.objects.filter(is_active=True, is_staff=True)
            .order_by("id")
            .values("id", "email", "name", "admin_role")
        )
        return success_response(rows)


class AdminAuditLogListAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"GET": {AdminPermission.AUDIT_LOG_VIEW}}

    def get(self, request, *args, **kwargs):
        queryset = AuditLog.objects.select_related("actor_admin").order_by("-occurred_at")

        action = request.query_params.get("action", "").strip()
        if action:
            queryset = queryset.filter(action=action)

        result = request.query_params.get("result", "").strip()
        if result:
            queryset = queryset.filter(result=result)

        target_type = request.query_params.get("target_type", "").strip()
        if target_type:
            queryset = queryset.filter(target_type=target_type)

        target_id = request.query_params.get("target_id", "").strip()
        if target_id:
            queryset = queryset.filter(target_id=target_id)

        actor_admin_id = request.query_params.get("actor_admin_id")
        if actor_admin_id and str(actor_admin_id).isdigit():
            queryset = queryset.filter(actor_admin_id=int(actor_admin_id))

        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(action__icontains=q)
                | Q(target_type__icontains=q)
                | Q(target_id__icontains=q)
                | Q(request_id__icontains=q)
                | Q(idempotency_key__icontains=q)
                | Q(actor_admin__email__icontains=q)
            )

        limit = request.query_params.get("limit", "200")
        try:
            limit_number = min(max(int(limit), 1), 1000)
        except (TypeError, ValueError):
            limit_number = 200

        rows = []
        for row in queryset[:limit_number]:
            rows.append(
                {
                    "id": row.id,
                    "occurred_at": row.occurred_at,
                    "actor_admin_id": row.actor_admin_id,
                    "actor_admin_email": row.actor_admin.email if row.actor_admin else "",
                    "actor_role": row.actor_role,
                    "action": row.action,
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                    "request_id": row.request_id,
                    "idempotency_key": row.idempotency_key,
                    "ip": str(row.ip or ""),
                    "user_agent": row.user_agent,
                    "before_json": row.before_json,
                    "after_json": row.after_json,
                    "metadata_json": row.metadata_json,
                    "result": row.result,
                    "error_code": row.error_code,
                }
            )

        return success_response(AdminAuditLogSerializer(rows, many=True).data)


class AdminHomeBannerListCreateAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "GET": {AdminPermission.BANNER_VIEW},
        "POST": {AdminPermission.BANNER_UPDATE},
    }

    def get(self, request, *args, **kwargs):
        rows = HomeBanner.objects.all().order_by("sort_order", "id")
        return success_response(AdminHomeBannerSerializer(rows, many=True, context={"request": request}).data)

    def post(self, request, *args, **kwargs):
        serializer = AdminBannerUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        title = (payload.get("title") or "").strip()
        if not title:
            return error_response("INVALID_BANNER_TITLE", "배너 제목을 입력해주세요.", status_code=status.HTTP_400_BAD_REQUEST)

        row = HomeBanner(
            title=title,
            subtitle=(payload.get("subtitle") or "").strip(),
            description=(payload.get("description") or "").strip(),
            cta_text=(payload.get("cta_text") or "").strip(),
            link_url=(payload.get("link_url") or "").strip(),
            sort_order=int(payload.get("sort_order", 0)),
            is_active=bool(payload.get("is_active", True)),
        )
        image_file = request.FILES.get("image")
        if image_file:
            row.image = image_file
        row.save()

        return success_response(
            AdminHomeBannerSerializer(row, context={"request": request}).data,
            message="배너가 생성되었습니다.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminHomeBannerDetailAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "PATCH": {AdminPermission.BANNER_UPDATE},
        "DELETE": {AdminPermission.BANNER_UPDATE},
    }

    def patch(self, request, banner_id: int, *args, **kwargs):
        row = get_object_or_404(HomeBanner, id=banner_id)
        serializer = AdminBannerUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        updated_fields: list[str] = []
        for field in ("subtitle", "description", "cta_text", "link_url", "sort_order", "is_active"):
            if field in payload:
                setattr(row, field, payload[field])
                updated_fields.append(field)

        if "title" in payload:
            title = (payload.get("title") or "").strip()
            if not title:
                return error_response(
                    "INVALID_BANNER_TITLE",
                    "배너 제목을 입력해주세요.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            row.title = title
            updated_fields.append("title")

        image_file = request.FILES.get("image")
        if image_file:
            row.image = image_file
            updated_fields.append("image")

        if not updated_fields:
            return error_response("NO_UPDATE_FIELDS", "변경할 값이 없습니다.", status_code=status.HTTP_400_BAD_REQUEST)

        row.save(update_fields=list(dict.fromkeys(updated_fields)))
        return success_response(
            AdminHomeBannerSerializer(row, context={"request": request}).data,
            message="배너 정보가 저장되었습니다.",
        )

    def delete(self, request, banner_id: int, *args, **kwargs):
        row = get_object_or_404(HomeBanner, id=banner_id)
        row.delete()
        return success_response(message="배너가 삭제되었습니다.")


class AdminBrandPageSettingAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "GET": {AdminPermission.BANNER_VIEW},
        "PATCH": {AdminPermission.BANNER_UPDATE},
    }

    @staticmethod
    def _get_setting() -> BrandPageSetting:
        row = BrandPageSetting.objects.order_by("id").first()
        if row:
            return row
        return BrandPageSetting.objects.create()

    def get(self, request, *args, **kwargs):
        row = self._get_setting()
        return success_response(AdminBrandPageSettingSerializer(row).data)

    def patch(self, request, *args, **kwargs):
        row = self._get_setting()
        serializer = AdminBrandPageSettingUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        if not payload:
            return error_response("NO_UPDATE_FIELDS", "변경할 값이 없습니다.", status_code=status.HTTP_400_BAD_REQUEST)

        updated_fields: list[str] = []
        for field in ("hero_eyebrow", "hero_title", "hero_description"):
            if field in payload:
                setattr(row, field, payload[field])
                updated_fields.append(field)

        row.save(update_fields=list(dict.fromkeys(updated_fields + ["updated_at"])))
        return success_response(AdminBrandPageSettingSerializer(row).data, message="브랜드 페이지 상단 정보가 저장되었습니다.")


class AdminBrandStorySectionListCreateAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "GET": {AdminPermission.BANNER_VIEW},
        "POST": {AdminPermission.BANNER_UPDATE},
    }

    def get(self, request, *args, **kwargs):
        rows = BrandStorySection.objects.all().order_by("sort_order", "id")
        return success_response(AdminBrandStorySectionSerializer(rows, many=True, context={"request": request}).data)

    def post(self, request, *args, **kwargs):
        serializer = AdminBrandStorySectionUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        title = (payload.get("title") or "").strip()
        if not title:
            return error_response("INVALID_BRAND_SECTION_TITLE", "구획 제목을 입력해주세요.", status_code=status.HTTP_400_BAD_REQUEST)

        row = BrandStorySection(
            eyebrow=(payload.get("eyebrow") or "").strip(),
            title=title,
            description=(payload.get("description") or "").strip(),
            image_alt=(payload.get("image_alt") or "").strip(),
            sort_order=int(payload.get("sort_order", 0)),
            is_active=bool(payload.get("is_active", True)),
        )
        image_file = request.FILES.get("image")
        if image_file:
            row.image = image_file
        row.save()

        return success_response(
            AdminBrandStorySectionSerializer(row, context={"request": request}).data,
            message="브랜드 구획이 생성되었습니다.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminBrandStorySectionDetailAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "PATCH": {AdminPermission.BANNER_UPDATE},
        "DELETE": {AdminPermission.BANNER_UPDATE},
    }

    def patch(self, request, section_id: int, *args, **kwargs):
        row = get_object_or_404(BrandStorySection, id=section_id)
        serializer = AdminBrandStorySectionUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        updated_fields: list[str] = []
        for field in ("eyebrow", "description", "image_alt", "sort_order", "is_active"):
            if field in payload:
                setattr(row, field, payload[field])
                updated_fields.append(field)

        if "title" in payload:
            title = (payload.get("title") or "").strip()
            if not title:
                return error_response(
                    "INVALID_BRAND_SECTION_TITLE",
                    "구획 제목을 입력해주세요.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            row.title = title
            updated_fields.append("title")

        image_file = request.FILES.get("image")
        if image_file:
            row.image = image_file
            updated_fields.append("image")

        if not updated_fields:
            return error_response("NO_UPDATE_FIELDS", "변경할 값이 없습니다.", status_code=status.HTTP_400_BAD_REQUEST)

        row.save(update_fields=list(dict.fromkeys(updated_fields + ["updated_at"])))
        return success_response(
            AdminBrandStorySectionSerializer(row, context={"request": request}).data,
            message="브랜드 구획이 저장되었습니다.",
        )

    def delete(self, request, section_id: int, *args, **kwargs):
        row = get_object_or_404(BrandStorySection, id=section_id)
        row.delete()
        return success_response(message="브랜드 구획이 삭제되었습니다.")


class AdminProductMetaAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"GET": {AdminPermission.PRODUCT_VIEW}}

    def get(self, request, *args, **kwargs):
        badge_options = [
            {"code": code, "label": label}
            for code, label in ProductBadge.BadgeType.choices
        ]
        tax_status_options = [
            {"code": code, "label": label}
            for code, label in Product.TaxStatus.choices
        ]
        category_options = list(
            Category.objects.filter(is_active=True)
            .order_by("name")
            .values("id", "name", "slug")
        )
        return success_response(
            {
                "badge_options": badge_options,
                "tax_status_options": tax_status_options,
                "category_options": category_options,
            }
        )


class AdminProductListCreateAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "GET": {AdminPermission.PRODUCT_VIEW},
        "POST": {AdminPermission.PRODUCT_UPDATE},
    }

    def get(self, request, *args, **kwargs):
        queryset = Product.objects.prefetch_related("badges", "images", "options").order_by("-created_at")

        q = request.query_params.get("q", "").strip()
        if q:
            query_filter = (
                Q(name__icontains=q)
                | Q(one_line__icontains=q)
                | Q(description__icontains=q)
                | Q(sku__icontains=q)
                | Q(manufacturer__icontains=q)
                | Q(origin_country__icontains=q)
                | Q(search_keywords__icontains=q)
            )
            if q.isdigit():
                query_filter |= Q(id=int(q))
            queryset = queryset.filter(query_filter)

        is_active = request.query_params.get("is_active")
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))

        category_id = request.query_params.get("category_id")
        if category_id and str(category_id).isdigit():
            queryset = queryset.filter(category_id=int(category_id))

        limit = request.query_params.get("limit", "200")
        try:
            limit_number = min(max(int(limit), 1), 500)
        except (TypeError, ValueError):
            limit_number = 200

        rows = queryset[:limit_number]
        return success_response(AdminProductManageSerializer(rows, many=True, context={"request": request}).data)

    def post(self, request, *args, **kwargs):
        serializer = AdminProductUpsertSerializer(data=_build_product_payload(request.data))
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        name = (payload.get("name") or "").strip()
        if not name:
            return error_response("INVALID_PRODUCT_NAME", "상품명을 입력해주세요.", status_code=status.HTTP_400_BAD_REQUEST)
        if "price" not in payload or "original_price" not in payload:
            return error_response(
                "INVALID_PRODUCT_PRICE",
                "판매가와 정상가를 입력해주세요.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        sku = (payload.get("sku") or "").strip() or None
        if sku and Product.objects.filter(sku=sku).exists():
            return error_response(
                "DUPLICATE_PRODUCT_SKU",
                "이미 사용 중인 상품관리코드(SKU)입니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        category = None
        if "category_id" in payload:
            category_id = payload.get("category_id")
            if category_id:
                category = Category.objects.filter(id=category_id, is_active=True).first()
                if not category:
                    return error_response(
                        "INVALID_CATEGORY",
                        "유효한 카테고리를 선택해주세요.",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )

        product = Product.objects.create(
            category=category,
            sku=sku,
            name=name,
            one_line=(payload.get("one_line") or "").strip(),
            description=(payload.get("description") or "").strip(),
            intake=(payload.get("intake") or "").strip(),
            target=(payload.get("target") or "").strip(),
            manufacturer=(payload.get("manufacturer") or "").strip(),
            origin_country=(payload.get("origin_country") or "").strip(),
            tax_status=payload.get("tax_status", Product.TaxStatus.TAXABLE),
            delivery_fee=payload.get("delivery_fee", 3000),
            free_shipping_amount=payload.get("free_shipping_amount", 50000),
            search_keywords=payload.get("search_keywords", []),
            release_date=payload.get("release_date"),
            display_start_at=payload.get("display_start_at"),
            display_end_at=payload.get("display_end_at"),
            price=payload["price"],
            original_price=payload["original_price"],
            stock=payload.get("stock", 0),
            is_active=payload.get("is_active", True),
        )

        badge_types = payload.get("badge_types", [])
        if badge_types:
            _set_product_badges(product, badge_types)
        _sync_product_package_options(product, package_options=payload.get("package_options"))

        _sync_product_images(
            product,
            thumbnail_file=request.FILES.get("thumbnail"),
            image_files=request.FILES.getlist("images"),
        )

        refreshed = Product.objects.prefetch_related("badges", "images", "options").get(id=product.id)
        return success_response(
            AdminProductManageSerializer(refreshed, context={"request": request}).data,
            message="상품이 생성되었습니다.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminProductDetailAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "PATCH": {AdminPermission.PRODUCT_UPDATE},
        "DELETE": {AdminPermission.PRODUCT_UPDATE},
    }

    def patch(self, request, product_id: int, *args, **kwargs):
        product = get_object_or_404(Product, id=product_id)
        serializer = AdminProductUpsertSerializer(data=_build_product_payload(request.data))
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        updated_fields = ["updated_at"]
        field_names = (
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
        )
        for field in field_names:
            if field in payload:
                value = payload[field]
                if field == "name":
                    value = str(value).strip()
                    if not value:
                        return error_response(
                            "INVALID_PRODUCT_NAME",
                            "상품명을 입력해주세요.",
                            status_code=status.HTTP_400_BAD_REQUEST,
                        )
                if field in {"description", "one_line", "intake", "target", "manufacturer", "origin_country"}:
                    value = str(value).strip()
                setattr(product, field, value)
                updated_fields.append(field)

        if "sku" in payload:
            next_sku = (payload.get("sku") or "").strip() or None
            if next_sku and Product.objects.exclude(id=product.id).filter(sku=next_sku).exists():
                return error_response(
                    "DUPLICATE_PRODUCT_SKU",
                    "이미 사용 중인 상품관리코드(SKU)입니다.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            product.sku = next_sku
            updated_fields.append("sku")

        if "category_id" in payload:
            category_id = payload.get("category_id")
            if category_id is None:
                product.category = None
            else:
                category = Category.objects.filter(id=category_id, is_active=True).first()
                if not category:
                    return error_response(
                        "INVALID_CATEGORY",
                        "유효한 카테고리를 선택해주세요.",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
                product.category = category
            updated_fields.append("category")

        if "badge_types" in payload:
            _set_product_badges(product, payload.get("badge_types", []))
        if "package_options" in payload:
            _sync_product_package_options(product, package_options=payload.get("package_options"))

        thumbnail_file = request.FILES.get("thumbnail")
        image_files = request.FILES.getlist("images")
        delete_image_ids = payload.get("delete_image_ids", [])
        has_thumbnail_image_id = "thumbnail_image_id" in payload
        thumbnail_image_id = payload.get("thumbnail_image_id") if has_thumbnail_image_id else None

        has_image_update = bool(thumbnail_file or image_files or delete_image_ids or has_thumbnail_image_id)
        if has_image_update:
            _sync_product_images(
                product,
                thumbnail_file=thumbnail_file,
                image_files=image_files,
                delete_image_ids=delete_image_ids,
                thumbnail_image_id=thumbnail_image_id,
            )

        if (
            len(updated_fields) == 1
            and "badge_types" not in payload
            and "package_options" not in payload
            and not has_image_update
        ):
            return error_response("NO_UPDATE_FIELDS", "변경할 값이 없습니다.", status_code=status.HTTP_400_BAD_REQUEST)

        product.save(update_fields=list(dict.fromkeys(updated_fields)))
        refreshed = Product.objects.prefetch_related("badges", "images", "options").get(id=product.id)
        return success_response(
            AdminProductManageSerializer(refreshed, context={"request": request}).data,
            message="상품 정보가 저장되었습니다.",
        )

    def delete(self, request, product_id: int, *args, **kwargs):
        product = get_object_or_404(Product, id=product_id)
        product.delete()
        return success_response(message="상품이 삭제되었습니다.")


class AdminUserListAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"GET": {AdminPermission.USER_VIEW}}

    def get(self, request, *args, **kwargs):
        queryset = User.objects.annotate(
            order_count=Count("orders", distinct=True),
            review_count=Count("reviews", distinct=True),
            inquiry_count=Count("inquiries", distinct=True),
        ).order_by("-created_at")

        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(email__icontains=q)
                | Q(name__icontains=q)
                | Q(phone__icontains=q)
            )

        is_active = request.query_params.get("is_active")
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))

        is_staff = request.query_params.get("is_staff")
        if is_staff in {"true", "false"}:
            queryset = queryset.filter(is_staff=(is_staff == "true"))

        limit = request.query_params.get("limit", "200")
        try:
            limit_number = min(max(int(limit), 1), 1000)
        except (TypeError, ValueError):
            limit_number = 200

        rows = queryset[:limit_number]
        data = AdminUserManageSerializer(rows, many=True).data
        if not has_full_pii_access(request.user):
            data = apply_masking_to_users(data)
        else:
            _log_pii_view_if_needed(
                request,
                target_type="User",
                metadata={"endpoint": "admin/users/manage", "count": len(data)},
            )
        return success_response(data)


class AdminUserDetailAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "PATCH": {AdminPermission.USER_UPDATE},
        "DELETE": {AdminPermission.USER_UPDATE},
    }

    def patch(self, request, user_id: int, *args, **kwargs):
        target = get_object_or_404(User, id=user_id)
        serializer = AdminUserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        idempotency_key = extract_idempotency_key(request, payload)
        request_hash = build_request_hash({k: v for k, v in payload.items() if k != "idempotency_key"})
        replay_response = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.users.patch",
            request_hash=request_hash,
        )
        if replay_response is not None:
            return replay_response

        if target.is_superuser and ("is_active" in payload or "is_staff" in payload):
            return error_response(
                "INVALID_TARGET_USER",
                "슈퍼유저 권한 상태는 이 화면에서 변경할 수 없습니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if target.id == request.user.id and payload.get("is_active") is False:
            return error_response(
                "INVALID_TARGET_USER",
                "현재 로그인한 관리자 계정은 비활성화할 수 없습니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if "admin_role" in payload and get_admin_role(request.user) != User.AdminRole.SUPER_ADMIN:
            return error_response(
                "FORBIDDEN",
                "관리자 역할 변경은 SUPER_ADMIN만 수행할 수 있습니다.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        before = _copy_for_audit(target, ("is_staff", "admin_role", "is_active", "name", "phone"))
        updated_fields = ["updated_at"]
        for field in ("name", "phone", "is_active", "is_staff"):
            if field in payload:
                setattr(target, field, payload[field])
                updated_fields.append(field)

        if "admin_role" in payload:
            target.admin_role = payload["admin_role"]
            updated_fields.append("admin_role")

        if "is_staff" in payload and payload["is_staff"] is False:
            if target.admin_role != User.AdminRole.READ_ONLY:
                target.admin_role = User.AdminRole.READ_ONLY
                updated_fields.append("admin_role")
        elif "is_staff" in payload and payload["is_staff"] is True and "admin_role" not in payload:
            if not target.admin_role:
                target.admin_role = User.AdminRole.OPS
                updated_fields.append("admin_role")

        target.save(update_fields=list(dict.fromkeys(updated_fields)))
        refreshed = User.objects.annotate(
            order_count=Count("orders", distinct=True),
            review_count=Count("reviews", distinct=True),
            inquiry_count=Count("inquiries", distinct=True),
        ).get(id=target.id)
        response_data = AdminUserManageSerializer(refreshed).data
        role_changed = before.get("admin_role") != refreshed.admin_role or before.get("is_staff") != refreshed.is_staff
        if not has_full_pii_access(request.user):
            response_data = apply_masking_to_users(response_data)
        else:
            _log_pii_view_if_needed(
                request,
                target_type="User",
                target_id=str(refreshed.id),
                metadata={"endpoint": "admin/users/manage/{id}"},
            )

        response = success_response(response_data, message="회원 정보가 저장되었습니다.")
        save_idempotent_response(
            request=request,
            key=idempotency_key,
            action="admin.users.patch",
            request_hash=request_hash,
            response=response,
            target_type="User",
            target_id=str(refreshed.id),
        )
        if role_changed:
            log_audit_event(
                request,
                action="ADMIN_ROLE_CHANGED",
                target_type="User",
                target_id=str(refreshed.id),
                before={"is_staff": before.get("is_staff"), "admin_role": before.get("admin_role")},
                after={"is_staff": refreshed.is_staff, "admin_role": refreshed.admin_role},
                idempotency_key=idempotency_key,
            )
        return response

    def delete(self, request, user_id: int, *args, **kwargs):
        idempotency_key = extract_idempotency_key(request, {})
        request_hash = build_request_hash({"user_id": user_id, "method": "DELETE"})
        replay_response = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.users.delete",
            request_hash=request_hash,
        )
        if replay_response is not None:
            return replay_response

        target = get_object_or_404(User, id=user_id)
        if target.id == request.user.id:
            return error_response(
                "INVALID_TARGET_USER",
                "현재 로그인한 관리자 계정은 비활성화할 수 없습니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if not target.is_active:
            return success_response(message="이미 비활성화된 회원입니다.")

        target.is_active = False
        target.save(update_fields=["is_active", "updated_at"])
        response = success_response(message="회원이 비활성화되었습니다.")
        save_idempotent_response(
            request=request,
            key=idempotency_key,
            action="admin.users.delete",
            request_hash=request_hash,
            response=response,
            target_type="User",
            target_id=str(user_id),
        )
        log_audit_event(
            request,
            action="USER_DEACTIVATED",
            target_type="User",
            target_id=str(user_id),
            after={"is_active": False},
            idempotency_key=idempotency_key,
        )
        return response
