from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.common.response import error_response, success_response
from apps.orders.models import Order
from apps.orders.serializers import OrderSerializer

from .models import PaymentTransaction, WebhookEvent
from .serializers import (
    NaverPayApproveSerializer,
    NaverPayCancelSerializer,
    NaverPayReadySerializer,
    NaverPayWebhookSerializer,
)


class NaverPayReadyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = NaverPayReadySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order = Order.objects.filter(order_no=data["order_no"], user=request.user).first()
        if not order:
            return error_response("ORDER_NOT_FOUND", "주문을 찾을 수 없습니다.", status_code=status.HTTP_404_NOT_FOUND)

        if order.status not in {Order.Status.PENDING, Order.Status.FAILED}:
            return error_response("INVALID_ORDER_STATUS", "결제 준비가 불가능한 주문 상태입니다.")

        payment = PaymentTransaction.objects.create(
            order=order,
            provider=PaymentTransaction.Provider.NAVERPAY,
            status=PaymentTransaction.Status.READY,
            raw_request_json=data,
        )

        query = urlencode(
            {
                "order_no": order.order_no,
                "transaction_id": payment.id,
                "amount": order.total_amount,
                "return_url": data["return_url"],
                "cancel_url": data["cancel_url"],
                "fail_url": data["fail_url"],
            }
        )
        redirect_url = f"https://mockpay.sausalito.local/naverpay/checkout?{query}"

        order.payment_status = Order.PaymentStatus.READY
        order.save(update_fields=["payment_status", "updated_at"])

        return success_response(
            {
                "order_no": order.order_no,
                "transaction_id": payment.id,
                "redirect_url": redirect_url,
            },
            message="결제 준비가 완료되었습니다.",
        )


class NaverPayApproveAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = NaverPayApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order = Order.objects.filter(order_no=data["order_no"]).prefetch_related("items__product", "items__product_option").first()
        if not order:
            return error_response("ORDER_NOT_FOUND", "주문을 찾을 수 없습니다.", status_code=status.HTTP_404_NOT_FOUND)

        if order.total_amount != data["amount"]:
            return error_response("INVALID_AMOUNT", "결제 금액이 주문 금액과 일치하지 않습니다.")

        with transaction.atomic():
            if order.status != Order.Status.PAID:
                for item in order.items.select_related("product", "product_option"):
                    product = item.product
                    option = item.product_option
                    if product and product.stock < item.quantity:
                        return error_response("OUT_OF_STOCK", f"재고가 부족합니다. ({product.name})")
                    if option and option.stock < item.quantity:
                        return error_response("OUT_OF_STOCK", f"재고가 부족합니다. ({option.name})")

                for item in order.items.select_related("product", "product_option"):
                    product = item.product
                    option = item.product_option
                    if product:
                        product.stock -= item.quantity
                        product.save(update_fields=["stock", "updated_at"])
                    if option:
                        option.stock -= item.quantity
                        option.save(update_fields=["stock"])

            payment = (
                order.payment_transactions.filter(provider=PaymentTransaction.Provider.NAVERPAY)
                .order_by("-created_at")
                .first()
            )
            if payment is None:
                payment = PaymentTransaction.objects.create(
                    order=order,
                    provider=PaymentTransaction.Provider.NAVERPAY,
                    status=PaymentTransaction.Status.READY,
                )

            payment.payment_key = data["payment_key"]
            payment.status = PaymentTransaction.Status.APPROVED
            payment.approved_at = timezone.now()
            payment.raw_response_json = data
            payment.save(
                update_fields=[
                    "payment_key",
                    "status",
                    "approved_at",
                    "raw_response_json",
                    "updated_at",
                ]
            )

            order.status = Order.Status.PAID
            order.payment_status = Order.PaymentStatus.APPROVED
            order.save(update_fields=["status", "payment_status", "updated_at"])

        return success_response(
            {
                "order_no": order.order_no,
                "status": order.status,
                "payment_status": order.payment_status,
            },
            message="결제 승인이 완료되었습니다.",
        )


class NaverPayWebhookAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        if not self._verify_signature(request):
            return error_response("INVALID_SIGNATURE", "유효하지 않은 웹훅 서명입니다.", status_code=status.HTTP_401_UNAUTHORIZED)

        serializer = NaverPayWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        event, created = WebhookEvent.objects.get_or_create(
            event_id=data["event_id"],
            defaults={
                "provider": data.get("provider", "NAVERPAY"),
                "event_type": data["event_type"],
                "payload_json": data,
            },
        )
        if not created:
            return success_response(message="이미 처리된 이벤트입니다.")

        order_no = data.get("order_no")
        order = Order.objects.filter(order_no=order_no).first() if order_no else None

        try:
            if order and data.get("status") == "CANCELED":
                order.status = Order.Status.CANCELED
                order.payment_status = Order.PaymentStatus.CANCELED
                order.save(update_fields=["status", "payment_status", "updated_at"])
            if order and data.get("status") == "FAILED":
                order.status = Order.Status.FAILED
                order.payment_status = Order.PaymentStatus.FAILED
                order.save(update_fields=["status", "payment_status", "updated_at"])

            event.is_processed = True
            event.processed_at = timezone.now()
            event.save(update_fields=["is_processed", "processed_at"])
        except Exception as exc:
            event.fail_reason = str(exc)
            event.save(update_fields=["fail_reason"])
            raise

        return success_response(message="웹훅 이벤트가 처리되었습니다.")

    def _verify_signature(self, request) -> bool:
        secret = settings.NAVERPAY_WEBHOOK_SECRET
        if not secret:
            return True

        signature = request.headers.get("X-Naverpay-Signature", "")
        body = request.body
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)


class NaverPayCancelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = NaverPayCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order = (
            Order.objects.filter(order_no=data["order_no"], user=request.user)
            .prefetch_related("items__product", "items__product_option")
            .first()
        )
        if not order:
            return error_response("ORDER_NOT_FOUND", "주문을 찾을 수 없습니다.", status_code=status.HTTP_404_NOT_FOUND)

        if order.status not in {Order.Status.PAID, Order.Status.PARTIAL_REFUNDED}:
            return error_response("INVALID_ORDER_STATUS", "취소/환불 가능한 주문 상태가 아닙니다.")

        cancel_amount = data.get("amount") or order.total_amount
        full_cancel = cancel_amount >= order.total_amount

        with transaction.atomic():
            if full_cancel:
                for item in order.items.select_related("product", "product_option"):
                    if item.product:
                        item.product.stock += item.quantity
                        item.product.save(update_fields=["stock", "updated_at"])
                    if item.product_option:
                        item.product_option.stock += item.quantity
                        item.product_option.save(update_fields=["stock"])
                order.status = Order.Status.REFUNDED
            else:
                order.status = Order.Status.PARTIAL_REFUNDED

            order.payment_status = Order.PaymentStatus.CANCELED
            order.save(update_fields=["status", "payment_status", "updated_at"])

            PaymentTransaction.objects.create(
                order=order,
                provider=PaymentTransaction.Provider.NAVERPAY,
                status=PaymentTransaction.Status.CANCELED,
                fail_message=data.get("reason", ""),
                raw_request_json=data,
                raw_response_json={"canceled": True, "amount": cancel_amount},
            )

        return success_response(OrderSerializer(order).data, message="결제가 취소되었습니다.")
