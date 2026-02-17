from __future__ import annotations

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView

from apps.common.response import error_response, success_response
from apps.orders.models import Order
from apps.reviews.models import Review
from apps.reviews.serializers import refresh_product_rating

from .admin_serializers import (
    AdminCouponIssueSerializer,
    AdminCouponSerializer,
    AdminInquiryAnswerSerializer,
    AdminInquirySerializer,
    AdminOrderSerializer,
    AdminOrderUpdateSerializer,
    AdminReviewSerializer,
    AdminReviewVisibilitySerializer,
)
from .models import OneToOneInquiry, User, UserCoupon


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
                "hidden_review_count": Review.objects.filter(status=Review.Status.HIDDEN).count(),
            },
            "recent_orders": AdminOrderSerializer(
                Order.objects.select_related("user").prefetch_related("items").order_by("-created_at")[:12],
                many=True,
            ).data,
            "recent_inquiries": AdminInquirySerializer(
                OneToOneInquiry.objects.select_related("user").order_by("-created_at")[:12],
                many=True,
            ).data,
            "recent_reviews": AdminReviewSerializer(
                Review.objects.select_related("user", "product").prefetch_related("images").order_by("-created_at")[:12],
                many=True,
                context={"request": request},
            ).data,
        }
        return success_response(data)


class AdminOrderListAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        queryset = Order.objects.select_related("user").prefetch_related("items").order_by("-created_at")

        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(order_no__icontains=q)
                | Q(recipient__icontains=q)
                | Q(phone__icontains=q)
                | Q(user__email__icontains=q)
            )

        for field in ("status", "payment_status", "shipping_status"):
            value = request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})

        limit = request.query_params.get("limit", "80")
        try:
            limit_number = min(max(int(limit), 1), 200)
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

        for field in ("status", "payment_status", "shipping_status", "courier_name", "tracking_no"):
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
        return success_response(AdminOrderSerializer(order).data, message="주문/배송 정보가 업데이트되었습니다.")


class AdminInquiryListAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        queryset = OneToOneInquiry.objects.select_related("user").order_by("-created_at")
        status_value = request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)

        return success_response(AdminInquirySerializer(queryset[:200], many=True).data)


class AdminInquiryAnswerAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, inquiry_id: int, *args, **kwargs):
        inquiry = get_object_or_404(OneToOneInquiry, id=inquiry_id)
        serializer = AdminInquiryAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        inquiry.answer = serializer.validated_data["answer"]
        inquiry.status = serializer.validated_data.get("status", OneToOneInquiry.Status.ANSWERED)

        if inquiry.status == OneToOneInquiry.Status.OPEN:
            inquiry.answered_at = None
        else:
            inquiry.answered_at = timezone.now()

        inquiry.save(update_fields=["answer", "status", "answered_at", "updated_at"])
        return success_response(AdminInquirySerializer(inquiry).data, message="문의 답변이 저장되었습니다.")


class AdminReviewListAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        queryset = Review.objects.select_related("user", "product").prefetch_related("images").order_by("-created_at")

        status_value = request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)

        product_id = request.query_params.get("product_id")
        if product_id and str(product_id).isdigit():
            queryset = queryset.filter(product_id=int(product_id))

        return success_response(AdminReviewSerializer(queryset[:200], many=True, context={"request": request}).data)


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
