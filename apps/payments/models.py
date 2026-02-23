from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


def generate_idempotency_key() -> str:
    return uuid.uuid4().hex


class PaymentTransaction(models.Model):
    class Provider(models.TextChoices):
        NAVERPAY = "NAVERPAY", "NAVERPAY"
        BANK_TRANSFER = "BANK_TRANSFER", "BANK_TRANSFER"

    class Status(models.TextChoices):
        READY = "READY", "READY"
        APPROVED = "APPROVED", "APPROVED"
        FAILED = "FAILED", "FAILED"
        CANCELED = "CANCELED", "CANCELED"

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="payment_transactions")
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.BANK_TRANSFER)
    payment_key = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.READY)
    approved_at = models.DateTimeField(null=True, blank=True)
    fail_code = models.CharField(max_length=100, blank=True)
    fail_message = models.TextField(blank=True)
    raw_request_json = models.JSONField(default=dict, blank=True)
    raw_response_json = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=64, unique=True, default=generate_idempotency_key)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class WebhookEvent(models.Model):
    provider = models.CharField(max_length=50)
    event_type = models.CharField(max_length=100)
    event_id = models.CharField(max_length=255, unique=True)
    payload_json = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)
    is_processed = models.BooleanField(default=False)
    fail_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class BankTransferRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "REQUESTED"
        APPROVED = "APPROVED", "APPROVED"
        REJECTED = "REJECTED", "REJECTED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="bank_transfer_requests")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bank_transfer_requests",
    )
    depositor_name = models.CharField(max_length=100)
    depositor_phone = models.CharField(max_length=20, blank=True)
    transfer_amount = models.PositiveIntegerField(default=0)
    bank_name = models.CharField(max_length=100)
    bank_account_no = models.CharField(max_length=50)
    account_holder = models.CharField(max_length=100)
    transfer_note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_bank_transfer_requests",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rejected_bank_transfer_requests",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    admin_memo = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=64, unique=True, default=generate_idempotency_key)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["order", "status"]),
        ]


class BankTransferAccountConfig(models.Model):
    # 싱글톤 설정 테이블로 사용하기 위한 고정 키
    singleton_key = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    bank_name = models.CharField(max_length=100, default="신한은행")
    bank_account_no = models.CharField(max_length=50, default="110-555-012345")
    account_holder = models.CharField(max_length=100, default="소살리토")
    guide_message = models.CharField(max_length=255, default="입금 후 관리자 확인이 완료되면 결제완료 처리됩니다.")
    verification_notice = models.CharField(max_length=255, default="입금자명은 주문자명과 동일하게 입력해 주세요.")
    cash_receipt_guide = models.CharField(
        max_length=255,
        default="결제완료 후 마이페이지 또는 고객센터에서 현금영수증 발급을 요청할 수 있습니다.",
    )
    business_name = models.CharField(max_length=150, default="주식회사 네로")
    business_ceo_name = models.CharField(max_length=120, blank=True, default="")
    business_no = models.CharField(max_length=40, default="123-45-67890")
    ecommerce_no = models.CharField(max_length=80, default="2026-서울마포-0001")
    business_address = models.CharField(max_length=255, blank=True, default="")
    support_phone = models.CharField(max_length=60, default="1588-1234")
    support_email = models.CharField(max_length=120, default="cs@nero.ai.kr")
    support_hours = models.CharField(max_length=150, default="평일 10:00 - 18:00 / 점심 12:30 - 13:30")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Bank Transfer Account Config"
        verbose_name_plural = "Bank Transfer Account Config"

    def __str__(self) -> str:
        return f"{self.bank_name} {self.bank_account_no} ({self.account_holder})"
