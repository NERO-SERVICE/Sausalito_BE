from __future__ import annotations

from datetime import timedelta

from django.core.paginator import EmptyPage, Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView

from apps.catalog.models import HomeBanner, Product, ProductBadge, ProductImage
from apps.common.response import error_response, success_response
from apps.orders.models import Order, ReturnRequest, SettlementRecord
from apps.reviews.models import Review
from apps.reviews.serializers import refresh_product_rating

from .admin_serializers import (
    AdminBannerUpsertSerializer,
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
    AdminReviewVisibilitySerializer,
    AdminSettlementGenerateSerializer,
    AdminSettlementSerializer,
    AdminSettlementUpdateSerializer,
    AdminUserManageSerializer,
    AdminUserUpdateSerializer,
)
from .models import OneToOneInquiry, User, UserCoupon


def _calculate_return_deduction(order: Order) -> int:
    return int(
        order.return_requests.filter(status__in=[ReturnRequest.Status.REFUNDED, ReturnRequest.Status.CLOSED])
        .aggregate(total=Coalesce(Sum("approved_amount"), 0))
        .get("total")
        or 0
    )


def _calculate_settlement_payload(
    order: Order,
    *,
    pg_fee: int | None = None,
    platform_fee: int | None = None,
    return_deduction: int | None = None,
) -> dict:
    gross_amount = int(order.total_amount or 0)
    pg_fee_value = int(pg_fee if pg_fee is not None else round(gross_amount * 0.033))
    platform_fee_value = int(platform_fee if platform_fee is not None else round(gross_amount * 0.08))
    return_deduction_value = int(return_deduction if return_deduction is not None else _calculate_return_deduction(order))

    return {
        "gross_amount": gross_amount,
        "discount_amount": int(order.discount_amount or 0),
        "shipping_fee": int(order.shipping_fee or 0),
        "pg_fee": pg_fee_value,
        "platform_fee": platform_fee_value,
        "return_deduction": return_deduction_value,
        "settlement_amount": gross_amount - pg_fee_value - platform_fee_value - return_deduction_value,
    }


def _ensure_settlement_record(order: Order) -> SettlementRecord:
    payload = _calculate_settlement_payload(order)
    defaults = {
        **payload,
        "status": SettlementRecord.Status.PENDING,
        "expected_payout_date": timezone.localdate(order.created_at + timedelta(days=3)) if order.created_at else None,
    }

    settlement, created = SettlementRecord.objects.get_or_create(order=order, defaults=defaults)
    if created:
        return settlement

    settlement.gross_amount = payload["gross_amount"]
    settlement.discount_amount = payload["discount_amount"]
    settlement.shipping_fee = payload["shipping_fee"]
    settlement.return_deduction = payload["return_deduction"]
    settlement.settlement_amount = (
        settlement.gross_amount - settlement.pg_fee - settlement.platform_fee - settlement.return_deduction
    )

    if settlement.expected_payout_date is None and order.created_at:
        settlement.expected_payout_date = timezone.localdate(order.created_at + timedelta(days=3))

    settlement.save(
        update_fields=[
            "gross_amount",
            "discount_amount",
            "shipping_fee",
            "return_deduction",
            "settlement_amount",
            "expected_payout_date",
            "updated_at",
        ]
    )
    return settlement


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


def _build_product_payload(data) -> dict:
    payload: dict = {}
    field_pairs = (
        ("name", "name"),
        ("one_line", "one_line"),
        ("description", "description"),
        ("price", "price"),
        ("original_price", "original_price"),
        ("stock", "stock"),
        ("is_active", "is_active"),
    )

    for source_field, target_field in field_pairs:
        if hasattr(data, "__contains__"):
            if source_field in data:
                payload[target_field] = data.get(source_field)
        else:
            value = data.get(source_field)
            if value is not None:
                payload[target_field] = value

    badge_raw = data.getlist("badge_types") if hasattr(data, "getlist") else data.get("badge_types")
    if isinstance(badge_raw, list) and len(badge_raw) == 1 and "," in str(badge_raw[0]):
        badge_raw = str(badge_raw[0])
    if badge_raw is not None and (not isinstance(badge_raw, list) or badge_raw):
        payload["badge_types"] = _normalize_badge_types(badge_raw)

    return payload


def _set_product_badges(product: Product, badge_types: list[str]) -> None:
    ProductBadge.objects.filter(product=product).delete()
    ProductBadge.objects.bulk_create(
        [ProductBadge(product=product, badge_type=badge_type) for badge_type in badge_types],
        ignore_conflicts=True,
    )


class AdminDashboardAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        orders = Order.objects.all()
        paid_orders = orders.filter(payment_status=Order.PaymentStatus.APPROVED)

        total_paid_amount = paid_orders.aggregate(total=Coalesce(Sum("total_amount"), 0)).get("total") or 0
        total_order_amount = orders.aggregate(total=Coalesce(Sum("total_amount"), 0)).get("total") or 0

        today = timezone.localdate()
        today_paid_amount = (
            paid_orders.filter(created_at__date=today).aggregate(total=Coalesce(Sum("total_amount"), 0)).get("total") or 0
        )

        shipping_pending_count = orders.filter(
            payment_status=Order.PaymentStatus.APPROVED,
            shipping_status__in=[Order.ShippingStatus.READY, Order.ShippingStatus.PREPARING],
        ).count()

        now = timezone.now()
        open_return_statuses = [
            ReturnRequest.Status.REQUESTED,
            ReturnRequest.Status.APPROVED,
            ReturnRequest.Status.PICKUP_SCHEDULED,
            ReturnRequest.Status.RECEIVED,
            ReturnRequest.Status.REFUNDING,
        ]

        settlements = SettlementRecord.objects.all()
        pending_settlement_amount = (
            settlements.exclude(status=SettlementRecord.Status.PAID)
            .aggregate(total=Coalesce(Sum("settlement_amount"), 0))
            .get("total")
            or 0
        )
        paid_settlement_amount = (
            settlements.filter(status=SettlementRecord.Status.PAID)
            .aggregate(total=Coalesce(Sum("settlement_amount"), 0))
            .get("total")
            or 0
        )

        data = {
            "summary": {
                "total_orders": orders.count(),
                "paid_orders": paid_orders.count(),
                "total_order_amount": int(total_order_amount),
                "total_paid_amount": int(total_paid_amount),
                "today_paid_amount": int(today_paid_amount),
                "shipping_pending_count": shipping_pending_count,
                "shipping_shipped_count": orders.filter(shipping_status=Order.ShippingStatus.SHIPPED).count(),
                "shipping_delivered_count": orders.filter(shipping_status=Order.ShippingStatus.DELIVERED).count(),
                "open_inquiry_count": OneToOneInquiry.objects.filter(status=OneToOneInquiry.Status.OPEN).count(),
                "overdue_inquiry_count": OneToOneInquiry.objects.filter(
                    status=OneToOneInquiry.Status.OPEN,
                    sla_due_at__isnull=False,
                    sla_due_at__lt=now,
                ).count(),
                "hidden_review_count": Review.objects.filter(status=Review.Status.HIDDEN).count(),
                "open_return_count": ReturnRequest.objects.filter(status__in=open_return_statuses).count(),
                "completed_return_count": ReturnRequest.objects.filter(status=ReturnRequest.Status.REFUNDED).count(),
                "pending_settlement_amount": int(pending_settlement_amount),
                "paid_settlement_amount": int(paid_settlement_amount),
            },
            "recent_orders": AdminOrderSerializer(
                Order.objects.select_related("user", "settlement_record").prefetch_related("items", "return_requests").order_by("-created_at")[:12],
                many=True,
            ).data,
            "recent_inquiries": AdminInquirySerializer(
                OneToOneInquiry.objects.select_related("user", "assigned_admin").order_by("-created_at")[:12],
                many=True,
            ).data,
            "recent_reviews": AdminReviewSerializer(
                Review.objects.select_related("user", "product").prefetch_related("images").order_by("-created_at")[:12],
                many=True,
                context={"request": request},
            ).data,
            "recent_returns": AdminReturnRequestSerializer(
                ReturnRequest.objects.select_related("order", "user").order_by("-requested_at")[:12],
                many=True,
            ).data,
            "recent_settlements": AdminSettlementSerializer(
                SettlementRecord.objects.select_related("order", "order__user").order_by("-created_at")[:12],
                many=True,
            ).data,
        }
        return success_response(data)


class AdminOrderListAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        queryset = (
            Order.objects.select_related("user", "settlement_record")
            .prefetch_related("items", "return_requests")
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
        return success_response(AdminOrderSerializer(rows, many=True).data)


class AdminOrderUpdateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, order_no: str, *args, **kwargs):
        order = get_object_or_404(Order, order_no=order_no)
        serializer = AdminOrderUpdateSerializer(data=request.data, context={"order": order})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        is_updated = False
        now = timezone.now()

        for field in (
            "status",
            "payment_status",
            "shipping_status",
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
                order.shipping_status = Order.ShippingStatus.SHIPPED
            if not order.shipped_at:
                order.shipped_at = now
            is_updated = True

        if order.shipping_status == Order.ShippingStatus.SHIPPED and not order.shipped_at:
            order.shipped_at = now
            is_updated = True

        if payload.get("mark_delivered"):
            order.shipping_status = Order.ShippingStatus.DELIVERED
            order.delivered_at = now
            is_updated = True
        elif order.shipping_status == Order.ShippingStatus.DELIVERED and not order.delivered_at:
            order.delivered_at = now
            is_updated = True

        if not is_updated:
            return error_response("NO_UPDATE_FIELDS", "변경할 값이 없습니다.", status_code=status.HTTP_400_BAD_REQUEST)

        order.save()
        _ensure_settlement_record(order)

        refreshed = Order.objects.select_related("user", "settlement_record").prefetch_related("items", "return_requests").get(id=order.id)
        return success_response(AdminOrderSerializer(refreshed).data, message="주문/배송 정보가 업데이트되었습니다.")


class AdminInquiryListAPIView(APIView):
    permission_classes = [IsAdminUser]

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

        return success_response(AdminInquirySerializer(queryset[:limit_number], many=True).data)


class AdminInquiryAnswerAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, inquiry_id: int, *args, **kwargs):
        inquiry = get_object_or_404(OneToOneInquiry, id=inquiry_id)
        serializer = AdminInquiryAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
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
        return success_response(AdminInquirySerializer(inquiry).data, message="CS 문의가 업데이트되었습니다.")


class AdminReviewListAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        queryset = Review.objects.select_related("user", "product").prefetch_related("images")

        status_value = request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)

        product_id = request.query_params.get("product_id")
        if product_id and str(product_id).isdigit():
            queryset = queryset.filter(product_id=int(product_id))

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
    permission_classes = [IsAdminUser]

    def patch(self, request, review_id: int, *args, **kwargs):
        review = get_object_or_404(Review.objects.select_related("product"), id=review_id)
        serializer = AdminReviewVisibilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        visible = serializer.validated_data["visible"]
        next_status = Review.Status.VISIBLE if visible else Review.Status.HIDDEN

        if review.status != next_status:
            review.status = next_status
            review.save(update_fields=["status", "updated_at"])
            refresh_product_rating(review.product)

        return success_response(
            AdminReviewSerializer(review, context={"request": request}).data,
            message="리뷰 노출 상태가 변경되었습니다.",
        )


class AdminReviewDeleteAPIView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, review_id: int, *args, **kwargs):
        review = get_object_or_404(Review.objects.select_related("product"), id=review_id)
        if review.status != Review.Status.DELETED:
            review.status = Review.Status.DELETED
            review.save(update_fields=["status", "updated_at"])
            refresh_product_rating(review.product)
        return success_response(message="리뷰가 삭제 처리되었습니다.")


class AdminReturnRequestListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

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

        return success_response(AdminReturnRequestSerializer(queryset[:limit_number], many=True).data)

    def post(self, request, *args, **kwargs):
        serializer = AdminReturnRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        order = get_object_or_404(Order, order_no=payload["order_no"])
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

        settlement = _ensure_settlement_record(order)
        if settlement.status != SettlementRecord.Status.PAID:
            settlement.status = SettlementRecord.Status.HOLD
            settlement.save(update_fields=["status", "updated_at"])

        return success_response(
            AdminReturnRequestSerializer(return_request).data,
            message="반품/환불 요청이 등록되었습니다.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminReturnRequestUpdateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, return_request_id: int, *args, **kwargs):
        row = get_object_or_404(ReturnRequest.objects.select_related("order", "user"), id=return_request_id)
        serializer = AdminReturnRequestUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        now = timezone.now()
        updated_fields = ["updated_at"]

        for field in ("approved_amount", "rejected_reason", "pickup_courier_name", "pickup_tracking_no", "admin_note"):
            if field in payload:
                setattr(row, field, payload[field])
                updated_fields.append(field)

        if "status" in payload:
            row.status = payload["status"]
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
            order.save(update_fields=["status", "payment_status", "updated_at"])

        settlement = _ensure_settlement_record(order)
        if settlement.status != SettlementRecord.Status.PAID:
            has_open_return = order.return_requests.filter(
                status__in=[
                    ReturnRequest.Status.REQUESTED,
                    ReturnRequest.Status.APPROVED,
                    ReturnRequest.Status.PICKUP_SCHEDULED,
                    ReturnRequest.Status.RECEIVED,
                    ReturnRequest.Status.REFUNDING,
                ]
            ).exists()
            settlement.status = SettlementRecord.Status.HOLD if has_open_return else SettlementRecord.Status.PENDING
            settlement.settlement_amount = (
                settlement.gross_amount - settlement.pg_fee - settlement.platform_fee - _calculate_return_deduction(order)
            )
            settlement.return_deduction = _calculate_return_deduction(order)
            settlement.save(update_fields=["status", "return_deduction", "settlement_amount", "updated_at"])

        refreshed = ReturnRequest.objects.select_related("order", "user").get(id=row.id)
        return success_response(
            AdminReturnRequestSerializer(refreshed).data,
            message="반품/환불 요청이 업데이트되었습니다.",
        )

    def delete(self, request, return_request_id: int, *args, **kwargs):
        row = get_object_or_404(ReturnRequest.objects.select_related("order"), id=return_request_id)
        order = row.order
        row.delete()

        settlement = SettlementRecord.objects.filter(order=order).first()
        if settlement and settlement.status != SettlementRecord.Status.PAID:
            has_open_return = order.return_requests.filter(
                status__in=[
                    ReturnRequest.Status.REQUESTED,
                    ReturnRequest.Status.APPROVED,
                    ReturnRequest.Status.PICKUP_SCHEDULED,
                    ReturnRequest.Status.RECEIVED,
                    ReturnRequest.Status.REFUNDING,
                ]
            ).exists()
            settlement.status = SettlementRecord.Status.HOLD if has_open_return else SettlementRecord.Status.PENDING
            settlement.return_deduction = _calculate_return_deduction(order)
            settlement.settlement_amount = (
                settlement.gross_amount - settlement.pg_fee - settlement.platform_fee - settlement.return_deduction
            )
            settlement.save(update_fields=["status", "return_deduction", "settlement_amount", "updated_at"])

        return success_response(message="반품/환불 요청이 삭제되었습니다.")


class AdminSettlementListGenerateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        queryset = SettlementRecord.objects.select_related("order", "order__user").order_by("-created_at")

        status_value = request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)

        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(Q(order__order_no__icontains=q) | Q(order__user__email__icontains=q))

        limit = request.query_params.get("limit", "200")
        try:
            limit_number = min(max(int(limit), 1), 500)
        except (TypeError, ValueError):
            limit_number = 200

        return success_response(AdminSettlementSerializer(queryset[:limit_number], many=True).data)

    def post(self, request, *args, **kwargs):
        serializer = AdminSettlementGenerateSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        only_paid_orders = serializer.validated_data.get("only_paid_orders", True)

        queryset = Order.objects.all().order_by("-created_at")
        if only_paid_orders:
            queryset = queryset.filter(payment_status=Order.PaymentStatus.APPROVED)

        upserted = []
        for order in queryset[:1000]:
            upserted.append(_ensure_settlement_record(order))

        return success_response(
            {
                "generated_count": len(upserted),
                "settlements": AdminSettlementSerializer(upserted[:30], many=True).data,
            },
            message="정산 레코드가 생성/갱신되었습니다.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminSettlementUpdateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, settlement_id: int, *args, **kwargs):
        settlement = get_object_or_404(SettlementRecord.objects.select_related("order", "order__user"), id=settlement_id)
        serializer = AdminSettlementUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        updated_fields = ["updated_at"]

        for field in (
            "status",
            "pg_fee",
            "platform_fee",
            "return_deduction",
            "expected_payout_date",
            "memo",
        ):
            if field in payload:
                setattr(settlement, field, payload[field])
                updated_fields.append(field)

        settlement.settlement_amount = (
            int(settlement.gross_amount or 0)
            - int(settlement.pg_fee or 0)
            - int(settlement.platform_fee or 0)
            - int(settlement.return_deduction or 0)
        )
        updated_fields.append("settlement_amount")

        if payload.get("mark_paid"):
            settlement.status = SettlementRecord.Status.PAID
            settlement.paid_at = timezone.now()
            updated_fields.extend(["status", "paid_at"])
        elif settlement.status == SettlementRecord.Status.PAID and not settlement.paid_at:
            settlement.paid_at = timezone.now()
            updated_fields.append("paid_at")

        settlement.save(update_fields=list(dict.fromkeys(updated_fields)))
        return success_response(
            AdminSettlementSerializer(settlement).data,
            message="정산 정보가 업데이트되었습니다.",
        )

    def delete(self, request, settlement_id: int, *args, **kwargs):
        settlement = get_object_or_404(SettlementRecord, id=settlement_id)
        if settlement.status == SettlementRecord.Status.PAID:
            return error_response(
                "INVALID_SETTLEMENT_STATUS",
                "지급 완료된 정산은 삭제할 수 없습니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        settlement.delete()
        return success_response(message="정산 레코드가 삭제되었습니다.")


class AdminCouponListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

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
    permission_classes = [IsAdminUser]

    def delete(self, request, coupon_id: int, *args, **kwargs):
        coupon = get_object_or_404(UserCoupon, id=coupon_id)
        coupon.delete()
        return success_response(message="쿠폰이 삭제되었습니다.")


class AdminStaffUserListAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        rows = list(
            User.objects.filter(is_active=True, is_staff=True)
            .order_by("id")
            .values("id", "email", "name")
        )
        return success_response(rows)


class AdminHomeBannerListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

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
    permission_classes = [IsAdminUser]

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


class AdminProductListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        queryset = Product.objects.prefetch_related("badges", "images").order_by("-created_at")

        q = request.query_params.get("q", "").strip()
        if q:
            query_filter = Q(name__icontains=q) | Q(one_line__icontains=q) | Q(description__icontains=q)
            if q.isdigit():
                query_filter |= Q(id=int(q))
            queryset = queryset.filter(query_filter)

        is_active = request.query_params.get("is_active")
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))

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

        product = Product.objects.create(
            name=name,
            one_line=(payload.get("one_line") or "").strip(),
            description=(payload.get("description") or "").strip(),
            price=payload["price"],
            original_price=payload["original_price"],
            stock=payload.get("stock", 0),
            is_active=payload.get("is_active", True),
        )

        badge_types = payload.get("badge_types", [])
        if badge_types:
            _set_product_badges(product, badge_types)

        thumbnail_file = request.FILES.get("thumbnail")
        if thumbnail_file:
            ProductImage.objects.create(product=product, image=thumbnail_file, is_thumbnail=True, sort_order=0)

        refreshed = Product.objects.prefetch_related("badges", "images").get(id=product.id)
        return success_response(
            AdminProductManageSerializer(refreshed, context={"request": request}).data,
            message="상품이 생성되었습니다.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminProductDetailAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, product_id: int, *args, **kwargs):
        product = get_object_or_404(Product, id=product_id)
        serializer = AdminProductUpsertSerializer(data=_build_product_payload(request.data))
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        updated_fields = ["updated_at"]
        for field in ("name", "one_line", "description", "price", "original_price", "stock", "is_active"):
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
                setattr(product, field, value)
                updated_fields.append(field)

        if "badge_types" in payload:
            _set_product_badges(product, payload.get("badge_types", []))

        thumbnail_file = request.FILES.get("thumbnail")
        if thumbnail_file:
            thumbnail = product.images.filter(is_thumbnail=True).order_by("id").first()
            if thumbnail:
                thumbnail.image = thumbnail_file
                thumbnail.sort_order = 0
                thumbnail.save(update_fields=["image", "sort_order"])
            else:
                ProductImage.objects.create(product=product, image=thumbnail_file, is_thumbnail=True, sort_order=0)

        if len(updated_fields) == 1 and "badge_types" not in payload and not thumbnail_file:
            return error_response("NO_UPDATE_FIELDS", "변경할 값이 없습니다.", status_code=status.HTTP_400_BAD_REQUEST)

        product.save(update_fields=list(dict.fromkeys(updated_fields)))
        refreshed = Product.objects.prefetch_related("badges", "images").get(id=product.id)
        return success_response(
            AdminProductManageSerializer(refreshed, context={"request": request}).data,
            message="상품 정보가 저장되었습니다.",
        )

    def delete(self, request, product_id: int, *args, **kwargs):
        product = get_object_or_404(Product, id=product_id)
        product.delete()
        return success_response(message="상품이 삭제되었습니다.")


class AdminUserListAPIView(APIView):
    permission_classes = [IsAdminUser]

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
        return success_response(AdminUserManageSerializer(rows, many=True).data)


class AdminUserDetailAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, user_id: int, *args, **kwargs):
        target = get_object_or_404(User, id=user_id)
        serializer = AdminUserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

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

        updated_fields = ["updated_at"]
        for field in ("name", "phone", "is_active", "is_staff"):
            if field in payload:
                setattr(target, field, payload[field])
                updated_fields.append(field)

        target.save(update_fields=list(dict.fromkeys(updated_fields)))
        refreshed = User.objects.annotate(
            order_count=Count("orders", distinct=True),
            review_count=Count("reviews", distinct=True),
            inquiry_count=Count("inquiries", distinct=True),
        ).get(id=target.id)
        return success_response(AdminUserManageSerializer(refreshed).data, message="회원 정보가 저장되었습니다.")

    def delete(self, request, user_id: int, *args, **kwargs):
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
        return success_response(message="회원이 비활성화되었습니다.")
