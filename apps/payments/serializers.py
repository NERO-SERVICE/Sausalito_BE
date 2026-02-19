from __future__ import annotations

from rest_framework import serializers

from .models import BankTransferRequest


class BankTransferRequestCreateSerializer(serializers.Serializer):
    order_no = serializers.CharField()
    depositor_name = serializers.CharField(max_length=100)
    depositor_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    transfer_note = serializers.CharField(required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)


class BankTransferRequestSerializer(serializers.ModelSerializer):
    order_no = serializers.CharField(source="order.order_no", read_only=True)
    order_status = serializers.CharField(source="order.status", read_only=True)
    order_payment_status = serializers.CharField(source="order.payment_status", read_only=True)

    class Meta:
        model = BankTransferRequest
        fields = (
            "id",
            "order_no",
            "order_status",
            "order_payment_status",
            "status",
            "transfer_amount",
            "bank_name",
            "bank_account_no",
            "account_holder",
            "depositor_name",
            "depositor_phone",
            "transfer_note",
            "rejection_reason",
            "admin_memo",
            "approved_at",
            "rejected_at",
            "created_at",
            "updated_at",
        )


class AdminBankTransferActionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[BankTransferRequest.Status.APPROVED, BankTransferRequest.Status.REJECTED])
    rejection_reason = serializers.CharField(required=False, allow_blank=True)
    admin_memo = serializers.CharField(required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs.get("status") == BankTransferRequest.Status.REJECTED and not str(
            attrs.get("rejection_reason") or ""
        ).strip():
            raise serializers.ValidationError({"rejection_reason": "반려 처리 시 반려 사유가 필요합니다."})
        return attrs


class AdminBankTransferSerializer(serializers.ModelSerializer):
    order_no = serializers.CharField(source="order.order_no", read_only=True)
    user_email = serializers.CharField(source="user.email", default="", read_only=True)
    user_name = serializers.CharField(source="user.name", default="", read_only=True)
    order_status = serializers.CharField(source="order.status", read_only=True)
    order_payment_status = serializers.CharField(source="order.payment_status", read_only=True)
    order_shipping_status = serializers.CharField(source="order.shipping_status", read_only=True)
    order_total_amount = serializers.IntegerField(source="order.total_amount", read_only=True)
    approved_by_email = serializers.CharField(source="approved_by.email", default="", read_only=True)
    rejected_by_email = serializers.CharField(source="rejected_by.email", default="", read_only=True)

    class Meta:
        model = BankTransferRequest
        fields = (
            "id",
            "order_no",
            "user_email",
            "user_name",
            "status",
            "order_status",
            "order_payment_status",
            "order_shipping_status",
            "order_total_amount",
            "transfer_amount",
            "bank_name",
            "bank_account_no",
            "account_holder",
            "depositor_name",
            "depositor_phone",
            "transfer_note",
            "admin_memo",
            "rejection_reason",
            "approved_by_email",
            "approved_at",
            "rejected_by_email",
            "rejected_at",
            "created_at",
            "updated_at",
        )
