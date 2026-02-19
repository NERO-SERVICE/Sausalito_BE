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
