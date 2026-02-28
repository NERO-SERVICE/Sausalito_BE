from __future__ import annotations

from django.conf import settings
from django.db import IntegrityError, transaction
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

from .models import BankTransferAccountConfig, BankTransferRequest, PaymentTransaction
from .services import apply_order_payment_approval
from .serializers import (
    AdminBankTransferActionSerializer,
    AdminBankTransferAccountConfigSerializer,
    AdminBankTransferAccountConfigUpdateSerializer,
    AdminBankTransferSerializer,
    BankTransferRequestCreateSerializer,
    BankTransferRequestSerializer,
)


def _default_bank_transfer_account_config_values() -> dict[str, str]:
    return {
        "bank_name": str(getattr(settings, "BANK_TRANSFER_BANK_NAME", "신한은행")),
        "bank_account_no": str(getattr(settings, "BANK_TRANSFER_ACCOUNT_NO", "110-555-012345")),
        "account_holder": str(getattr(settings, "BANK_TRANSFER_ACCOUNT_HOLDER", "소살리토")),
        "guide_message": str(
            getattr(
                settings,
                "BANK_TRANSFER_GUIDE_MESSAGE",
                "입금 후 관리자 확인이 완료되면 결제완료 처리됩니다.",
            )
        ),
        "verification_notice": str(
            getattr(
                settings,
                "BANK_TRANSFER_VERIFICATION_NOTICE",
                "입금자명은 주문자명과 동일하게 입력해 주세요.",
            )
        ),
        "cash_receipt_guide": str(
            getattr(
                settings,
                "BANK_TRANSFER_CASH_RECEIPT_GUIDE",
                "결제완료 후 마이페이지 또는 고객센터에서 현금영수증 발급을 요청할 수 있습니다.",
            )
        ),
        "business_name": str(getattr(settings, "STORE_BUSINESS_NAME", "주식회사 네로")),
        "business_ceo_name": str(getattr(settings, "STORE_CEO_NAME", "")),
        "business_no": str(getattr(settings, "STORE_BUSINESS_NO", "123-45-67890")),
        "ecommerce_no": str(getattr(settings, "STORE_ECOMMERCE_NO", "2026-서울마포-0001")),
        "business_address": str(getattr(settings, "STORE_BUSINESS_ADDRESS", "")),
        "support_phone": str(getattr(settings, "STORE_SUPPORT_PHONE", "1588-1234")),
        "support_email": str(getattr(settings, "STORE_SUPPORT_EMAIL", "cs@nero.ai.kr")),
        "support_hours": str(
            getattr(
                settings,
                "STORE_SUPPORT_HOURS",
                "평일 10:00 - 18:00 / 점심 12:30 - 13:30",
            )
        ),
    }


def _get_or_create_bank_transfer_account_config() -> BankTransferAccountConfig:
    defaults = _default_bank_transfer_account_config_values()
    try:
        row, _ = BankTransferAccountConfig.objects.get_or_create(singleton_key=1, defaults=defaults)
        return row
    except IntegrityError:
        # Parallel first-creation race fallback
        return BankTransferAccountConfig.objects.get(singleton_key=1)


def _build_bank_transfer_account_response(row: BankTransferAccountConfig) -> dict:
    return {
        "bank_name": row.bank_name,
        "bank_account_no": row.bank_account_no,
        "account_holder": row.account_holder,
        "guide_message": row.guide_message,
        "verification_notice": row.verification_notice,
        "cash_receipt_guide": row.cash_receipt_guide,
        "business_info": {
            "name": row.business_name,
            "ceo_name": row.business_ceo_name,
            "business_no": row.business_no,
            "ecommerce_no": row.ecommerce_no,
            "address": row.business_address,
        },
        "support_info": {
            "phone": row.support_phone,
            "email": row.support_email,
            "hours": row.support_hours,
        },
        "delivery_refund_policy": {
            "default_shipping_fee": int(getattr(settings, "DEFAULT_SHIPPING_FEE", 3000)),
            "free_shipping_threshold": int(getattr(settings, "FREE_SHIPPING_THRESHOLD", 30000)),
            "return_shipping_fee": int(getattr(settings, "STORE_RETURN_SHIPPING_FEE", 3000)),
            "exchange_shipping_fee": int(getattr(settings, "STORE_EXCHANGE_SHIPPING_FEE", 6000)),
            "return_address": str(
                getattr(settings, "STORE_RETURN_ADDRESS", "서울특별시 중구 퇴계로36길 2 물류센터")
            ),
        },
        "policy_links": {
            "terms": "/pages/terms.html",
            "privacy": "/pages/privacy.html",
            "guide": "/pages/guide.html",
            "commerce_notice": "/pages/commerce-notice.html",
        },
    }


def get_bank_transfer_account_info() -> dict[str, str]:
    row = _get_or_create_bank_transfer_account_config()
    return {
        "bank_name": row.bank_name,
        "bank_account_no": row.bank_account_no,
        "account_holder": row.account_holder,
    }


class BankTransferAccountInfoAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        row = _get_or_create_bank_transfer_account_config()
        return success_response(_build_bank_transfer_account_response(row))


class AdminBankTransferAccountConfigAPIView(APIView):
    permission_classes = [AdminRBACPermission]
    required_permissions = {
        "GET": {AdminPermission.ORDER_VIEW},
        "PATCH": {AdminPermission.ORDER_UPDATE},
    }

    def get(self, request, *args, **kwargs):
        row = _get_or_create_bank_transfer_account_config()
        return success_response(AdminBankTransferAccountConfigSerializer(row).data)

    def patch(self, request, *args, **kwargs):
        serializer = AdminBankTransferAccountConfigUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        idempotency_key = extract_idempotency_key(request, payload)
        request_hash = build_request_hash({k: v for k, v in payload.items() if k != "idempotency_key"})
        replay = get_idempotent_replay_response(
            key=idempotency_key,
            action="admin.bank_transfer.account_config.patch",
            request_hash=request_hash,
        )
        if replay is not None:
            return replay

        updatable_fields = (
            "bank_name",
            "bank_account_no",
            "account_holder",
            "guide_message",
            "verification_notice",
            "cash_receipt_guide",
            "business_name",
            "business_ceo_name",
            "business_no",
            "ecommerce_no",
            "business_address",
            "support_phone",
            "support_email",
            "support_hours",
        )

        with transaction.atomic():
            row = BankTransferAccountConfig.objects.select_for_update().filter(singleton_key=1).first()
            if not row:
                row = BankTransferAccountConfig.objects.create(
                    singleton_key=1,
                    **_default_bank_transfer_account_config_values(),
                )

            before = AdminBankTransferAccountConfigSerializer(row).data
            updated_fields = ["updated_at"]
            for field in updatable_fields:
                if field in payload:
                    setattr(row, field, payload[field])
                    updated_fields.append(field)

            if len(updated_fields) == 1:
                return error_response("NO_UPDATE_FIELDS", "변경할 값이 없습니다.", status_code=status.HTTP_400_BAD_REQUEST)

            row.save(update_fields=list(dict.fromkeys(updated_fields)))
            data = AdminBankTransferAccountConfigSerializer(row).data
            response = success_response(data, message="입금 계좌 정보가 저장되었습니다.")

            save_idempotent_response(
                request=request,
                key=idempotency_key,
                action="admin.bank_transfer.account_config.patch",
                request_hash=request_hash,
                response=response,
                target_type="BankTransferAccountConfig",
                target_id=str(row.id),
            )
            log_audit_event(
                request,
                action="BANK_TRANSFER_ACCOUNT_CONFIG_UPDATED",
                target_type="BankTransferAccountConfig",
                target_id=str(row.id),
                before=before,
                after=data,
                idempotency_key=idempotency_key,
            )
            return response


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
