from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.accounts.admin_security import (
    AdminPermission,
    AdminRBACPermission,
    build_request_hash,
    extract_idempotency_key,
    get_idempotent_replay_response,
    has_full_pii_access,
    log_audit_event,
    mask_email,
    mask_name,
    mask_phone,
    save_idempotent_response,
)
from apps.common.response import error_response, success_response
from apps.orders.models import Order
from apps.orders.serializers import OrderSerializer

from .models import BankTransferRequest, PaymentTransaction, WebhookEvent
from .services import apply_order_payment_approval
from .serializers import (
    AdminBankTransferActionSerializer,
    AdminBankTransferSerializer,
    BankTransferRequestCreateSerializer,
    BankTransferRequestSerializer,
    NaverPayApproveSerializer,
    NaverPayCancelSerializer,
    NaverPayReadySerializer,
    NaverPayWebhookSerializer,
)


def get_bank_transfer_account_info() -> dict[str, str]:
    return {
        "bank_name": str(getattr(settings, "BANK_TRANSFER_BANK_NAME", "신한은행")),
        "bank_account_no": str(getattr(settings, "BANK_TRANSFER_ACCOUNT_NO", "110-555-012345")),
        "account_holder": str(getattr(settings, "BANK_TRANSFER_ACCOUNT_HOLDER", "소살리토")),
    }


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
            try:
                apply_order_payment_approval(order)
            except ValueError as exc:
                return error_response("OUT_OF_STOCK", str(exc))

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


class BankTransferAccountInfoAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        account = get_bank_transfer_account_info()
        return success_response(
            {
                **account,
                "guide_message": "입금 후 관리자 확인이 완료되면 결제완료 처리됩니다.",
            }
        )


class BankTransferRequestListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        queryset = (
            BankTransferRequest.objects.filter(user=request.user)
            .select_related("order")
            .order_by("-created_at")
        )
        return success_response(BankTransferRequestSerializer(queryset, many=True).data)

    def post(self, request, *args, **kwargs):
        serializer = BankTransferRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        order = (
            Order.objects.filter(order_no=payload["order_no"], user=request.user)
            .select_related("user")
            .prefetch_related("items__product", "items__product_option")
            .first()
        )
        if not order:
            return error_response("ORDER_NOT_FOUND", "주문을 찾을 수 없습니다.", status_code=status.HTTP_404_NOT_FOUND)

        if order.status in {Order.Status.CANCELED, Order.Status.REFUNDED}:
            return error_response("INVALID_ORDER_STATUS", "계좌이체를 접수할 수 없는 주문 상태입니다.")

        idempotency_key = extract_idempotency_key(request, payload)
        if idempotency_key:
            duplicate = (
                BankTransferRequest.objects.filter(user=request.user, idempotency_key=idempotency_key)
                .select_related("order")
                .first()
            )
            if duplicate:
                return success_response(
                    BankTransferRequestSerializer(duplicate).data,
                    message="이미 접수된 계좌이체 요청입니다.",
                )

        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .filter(id=order.id)
                .select_related("user")
                .prefetch_related("items__product", "items__product_option")
                .first()
            )
            if not order:
                return error_response("ORDER_NOT_FOUND", "주문을 찾을 수 없습니다.", status_code=status.HTTP_404_NOT_FOUND)

            existing = (
                order.bank_transfer_requests.filter(
                    status__in=[BankTransferRequest.Status.REQUESTED, BankTransferRequest.Status.APPROVED]
                )
                .order_by("-created_at")
                .first()
            )
            if existing:
                if existing.status == BankTransferRequest.Status.REQUESTED:
                    return error_response("PENDING_TRANSFER_EXISTS", "이미 접수된 계좌이체 요청이 있습니다.")
                return error_response("PAYMENT_ALREADY_APPROVED", "이미 결제완료 처리된 주문입니다.")

            account = get_bank_transfer_account_info()
            transfer = BankTransferRequest.objects.create(
                order=order,
                user=request.user,
                depositor_name=payload["depositor_name"],
                depositor_phone=payload.get("depositor_phone", ""),
                transfer_amount=order.total_amount,
                bank_name=account["bank_name"],
                bank_account_no=account["bank_account_no"],
                account_holder=account["account_holder"],
                transfer_note=payload.get("transfer_note", ""),
                **({"idempotency_key": idempotency_key} if idempotency_key else {}),
            )

            PaymentTransaction.objects.create(
                order=order,
                provider=PaymentTransaction.Provider.BANK_TRANSFER,
                status=PaymentTransaction.Status.READY,
                raw_request_json={
                    "order_no": order.order_no,
                    "transfer_request_id": str(transfer.id),
                    "depositor_name": transfer.depositor_name,
                    "depositor_phone": transfer.depositor_phone,
                    "transfer_amount": transfer.transfer_amount,
                    "transfer_note": transfer.transfer_note,
                },
                raw_response_json={"status": transfer.status},
            )

            if order.payment_status == Order.PaymentStatus.UNPAID:
                order.payment_status = Order.PaymentStatus.READY
                order.save(update_fields=["payment_status", "updated_at"])

        data = BankTransferRequestSerializer(transfer).data
        data["account_info"] = get_bank_transfer_account_info()
        return success_response(
            data,
            message="계좌이체 요청이 접수되었습니다. 입금 확인 후 결제완료 처리됩니다.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminBankTransferListAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"GET": {AdminPermission.ORDER_VIEW}}

    def get(self, request, *args, **kwargs):
        queryset = (
            BankTransferRequest.objects.select_related("order", "user", "approved_by", "rejected_by")
            .order_by("-created_at")
        )

        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(order__order_no__icontains=q)
                | Q(user__email__icontains=q)
                | Q(user__name__icontains=q)
                | Q(depositor_name__icontains=q)
                | Q(depositor_phone__icontains=q)
            )

        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        limit = request.query_params.get("limit", "200")
        try:
            limit_number = min(max(int(limit), 1), 500)
        except (TypeError, ValueError):
            limit_number = 200

        rows = queryset[:limit_number]
        data = AdminBankTransferSerializer(rows, many=True).data
        if not has_full_pii_access(request.user):
            for row in data:
                row["user_email"] = mask_email(str(row.get("user_email") or ""))
                row["user_name"] = mask_name(str(row.get("user_name") or ""))
                row["depositor_name"] = mask_name(str(row.get("depositor_name") or ""))
                row["depositor_phone"] = mask_phone(str(row.get("depositor_phone") or ""))
        else:
            log_audit_event(
                request,
                action="PII_FULL_VIEW",
                target_type="BankTransferRequest",
                metadata={"endpoint": "admin/bank-transfers", "count": len(data)},
            )

        return success_response(data)


class AdminBankTransferActionAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {"PATCH": {AdminPermission.ORDER_UPDATE}}

    def patch(self, request, transfer_id: str, *args, **kwargs):
        serializer = AdminBankTransferActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        idempotency_key = extract_idempotency_key(request, payload)
        request_hash = build_request_hash({k: v for k, v in payload.items() if k != "idempotency_key"})
        replay = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.bank_transfer.patch",
            request_hash=request_hash,
        )
        if replay is not None:
            return replay

        with transaction.atomic():
            transfer = get_object_or_404(
                BankTransferRequest.objects.select_for_update().select_related("order", "user"),
                id=transfer_id,
            )
            order = (
                Order.objects.select_for_update()
                .filter(id=transfer.order_id)
                .prefetch_related("items__product", "items__product_option")
                .first()
            )
            if not order:
                return error_response("ORDER_NOT_FOUND", "주문을 찾을 수 없습니다.", status_code=status.HTTP_404_NOT_FOUND)
            transfer.order = order

            serializer = AdminBankTransferActionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            payload = serializer.validated_data
            next_status = payload["status"]

            if transfer.status != BankTransferRequest.Status.REQUESTED and transfer.status != next_status:
                return error_response(
                    "INVALID_TRANSFER_STATUS",
                    f"이미 처리된 요청입니다. ({transfer.status})",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            before = {
                "transfer_status": transfer.status,
                "order_status": order.status,
                "payment_status": order.payment_status,
            }

            now = timezone.now()
            if next_status == BankTransferRequest.Status.APPROVED:
                if transfer.status == BankTransferRequest.Status.REQUESTED:
                    try:
                        apply_order_payment_approval(order)
                    except ValueError as exc:
                        return error_response("OUT_OF_STOCK", str(exc))

                    transfer.status = BankTransferRequest.Status.APPROVED
                    transfer.approved_by = request.user
                    transfer.approved_at = now
                    transfer.rejected_by = None
                    transfer.rejected_at = None
                    transfer.rejection_reason = ""

                    PaymentTransaction.objects.create(
                        order=order,
                        provider=PaymentTransaction.Provider.BANK_TRANSFER,
                        status=PaymentTransaction.Status.APPROVED,
                        approved_at=now,
                        payment_key=f"BT-{str(transfer.id).replace('-', '')[:20]}",
                        raw_request_json={"transfer_id": str(transfer.id), "action": "APPROVED"},
                        raw_response_json={
                            "transfer_status": BankTransferRequest.Status.APPROVED,
                            "order_status": order.status,
                            "payment_status": order.payment_status,
                        },
                    )
                action_name = "BANK_TRANSFER_APPROVED"
                message = "계좌이체가 결제완료 처리되었습니다."
            else:
                if transfer.status == BankTransferRequest.Status.REQUESTED:
                    transfer.status = BankTransferRequest.Status.REJECTED
                    transfer.rejected_by = request.user
                    transfer.rejected_at = now
                    transfer.approved_by = None
                    transfer.approved_at = None
                    transfer.rejection_reason = payload.get("rejection_reason", "")

                    if order.status != Order.Status.PAID:
                        order.status = Order.Status.FAILED
                        order.payment_status = Order.PaymentStatus.FAILED
                        order.save(update_fields=["status", "payment_status", "updated_at"])

                    PaymentTransaction.objects.create(
                        order=order,
                        provider=PaymentTransaction.Provider.BANK_TRANSFER,
                        status=PaymentTransaction.Status.FAILED,
                        fail_message=transfer.rejection_reason,
                        raw_request_json={"transfer_id": str(transfer.id), "action": "REJECTED"},
                        raw_response_json={
                            "transfer_status": BankTransferRequest.Status.REJECTED,
                            "order_status": order.status,
                            "payment_status": order.payment_status,
                        },
                    )
                action_name = "BANK_TRANSFER_REJECTED"
                message = "계좌이체 요청이 반려 처리되었습니다."

            if "admin_memo" in payload:
                transfer.admin_memo = payload.get("admin_memo", "")
            transfer.save(
                update_fields=[
                    "status",
                    "approved_by",
                    "approved_at",
                    "rejected_by",
                    "rejected_at",
                    "rejection_reason",
                    "admin_memo",
                    "updated_at",
                ]
            )

            refreshed = BankTransferRequest.objects.select_related(
                "order", "user", "approved_by", "rejected_by"
            ).get(id=transfer.id)
            response_data = AdminBankTransferSerializer(refreshed).data
            if not has_full_pii_access(request.user):
                response_data["user_email"] = mask_email(str(response_data.get("user_email") or ""))
                response_data["user_name"] = mask_name(str(response_data.get("user_name") or ""))
                response_data["depositor_name"] = mask_name(str(response_data.get("depositor_name") or ""))
                response_data["depositor_phone"] = mask_phone(str(response_data.get("depositor_phone") or ""))

            response = success_response(response_data, message=message)
            save_idempotent_response(
                request=request,
                key=idempotency_key,
                action="admin.bank_transfer.patch",
                request_hash=request_hash,
                response=response,
                target_type="BankTransferRequest",
                target_id=str(refreshed.id),
            )

            after = {
                "transfer_status": refreshed.status,
                "order_status": refreshed.order.status,
                "payment_status": refreshed.order.payment_status,
            }
            log_audit_event(
                request,
                action=action_name,
                target_type="BankTransferRequest",
                target_id=str(refreshed.id),
                before=before,
                after=after,
                metadata={"order_no": refreshed.order.order_no},
                idempotency_key=idempotency_key,
            )

            return response
