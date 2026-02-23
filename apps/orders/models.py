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

    class ShippingStatus(models.TextChoices):
        READY = "READY", "READY"
        PREPARING = "PREPARING", "PREPARING"
        SHIPPED = "SHIPPED", "SHIPPED"
        DELIVERED = "DELIVERED", "DELIVERED"

    class ProductOrderStatus(models.TextChoices):
        PAYMENT_PENDING = "PAYMENT_PENDING", "PAYMENT_PENDING"
        PAYMENT_COMPLETED = "PAYMENT_COMPLETED", "PAYMENT_COMPLETED"
        SHIPPING = "SHIPPING", "SHIPPING"
        DELIVERED = "DELIVERED", "DELIVERED"
        PURCHASE_CONFIRMED = "PURCHASE_CONFIRMED", "PURCHASE_CONFIRMED"
        EXCHANGE = "EXCHANGE", "EXCHANGE"
        RETURNED = "RETURNED", "RETURNED"
        CANCELED = "CANCELED", "CANCELED"
        UNPAID_CANCELED = "UNPAID_CANCELED", "UNPAID_CANCELED"

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
    jibun_address = models.CharField(max_length=255, blank=True)
    detail_address = models.CharField(max_length=255, blank=True)

    payment_status = models.CharField(max_length=24, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    shipping_status = models.CharField(max_length=24, choices=ShippingStatus.choices, default=ShippingStatus.READY)
    product_order_status = models.CharField(
        max_length=32,
        choices=ProductOrderStatus.choices,
        default=ProductOrderStatus.PAYMENT_PENDING,
    )

    courier_name = models.CharField(max_length=100, blank=True)
    tracking_no = models.CharField(max_length=100, blank=True)

    invoice_issued_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
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


class ReturnRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "REQUESTED"
        APPROVED = "APPROVED", "APPROVED"
        PICKUP_SCHEDULED = "PICKUP_SCHEDULED", "PICKUP_SCHEDULED"
        RECEIVED = "RECEIVED", "RECEIVED"
        REFUNDING = "REFUNDING", "REFUNDING"
        REFUNDED = "REFUNDED", "REFUNDED"
        REJECTED = "REJECTED", "REJECTED"
        CLOSED = "CLOSED", "CLOSED"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="return_requests")
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="return_requests")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.REQUESTED)
    reason_title = models.CharField(max_length=200)
    reason_detail = models.TextField(blank=True)
    requested_amount = models.PositiveIntegerField(default=0)
    approved_amount = models.PositiveIntegerField(default=0)
    rejected_reason = models.TextField(blank=True)
    pickup_courier_name = models.CharField(max_length=100, blank=True)
    pickup_tracking_no = models.CharField(max_length=100, blank=True)
    admin_note = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-requested_at", "-id"]

    def __str__(self) -> str:
        return f"Return {self.order.order_no} ({self.status})"
