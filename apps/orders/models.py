from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


def generate_order_no() -> str:
    now = timezone.localtime()
    return f"SAU{now.strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "PENDING"
        PAID = "PAID", "PAID"
        FAILED = "FAILED", "FAILED"
        CANCELED = "CANCELED", "CANCELED"
        REFUNDED = "REFUNDED", "REFUNDED"
        PARTIAL_REFUNDED = "PARTIAL_REFUNDED", "PARTIAL_REFUNDED"

    class PaymentStatus(models.TextChoices):
        UNPAID = "UNPAID", "UNPAID"
        READY = "READY", "READY"
        APPROVED = "APPROVED", "APPROVED"
        CANCELED = "CANCELED", "CANCELED"
        FAILED = "FAILED", "FAILED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    order_no = models.CharField(max_length=32, unique=True, default=generate_order_no)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    subtotal_amount = models.PositiveIntegerField(default=0)
    shipping_fee = models.PositiveIntegerField(default=0)
    discount_amount = models.PositiveIntegerField(default=0)
    total_amount = models.PositiveIntegerField(default=0)

    recipient = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    postal_code = models.CharField(max_length=10)
    road_address = models.CharField(max_length=255)
    detail_address = models.CharField(max_length=255, blank=True)

    payment_status = models.CharField(max_length=24, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.order_no


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items")
    product_option = models.ForeignKey(
        "catalog.ProductOption",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    product_id_snapshot = models.PositiveIntegerField()
    product_name_snapshot = models.CharField(max_length=255)
    option_name_snapshot = models.CharField(max_length=255, blank=True)
    unit_price = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField()
    line_total = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.order.order_no} - {self.product_name_snapshot}"
