from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True, blank=True)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    kakao_sub = models.CharField(max_length=255, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email


class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    recipient = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    postal_code = models.CharField(max_length=10)
    road_address = models.CharField(max_length=255)
    detail_address = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "-updated_at"]

    def __str__(self) -> str:
        return f"{self.user.email} - {self.recipient}"


class PointTransaction(models.Model):
    class TxType(models.TextChoices):
        EARN = "EARN", "EARN"
        USE = "USE", "USE"
        ADJUST = "ADJUST", "ADJUST"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="point_transactions")
    tx_type = models.CharField(max_length=16, choices=TxType.choices, default=TxType.EARN)
    amount = models.IntegerField()
    balance_after = models.IntegerField(default=0)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class DepositTransaction(models.Model):
    class TxType(models.TextChoices):
        CHARGE = "CHARGE", "CHARGE"
        USE = "USE", "USE"
        REFUND = "REFUND", "REFUND"
        ADJUST = "ADJUST", "ADJUST"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="deposit_transactions")
    tx_type = models.CharField(max_length=16, choices=TxType.choices, default=TxType.CHARGE)
    amount = models.IntegerField()
    balance_after = models.IntegerField(default=0)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class UserCoupon(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="coupons")
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=64)
    discount_amount = models.PositiveIntegerField(default=0)
    min_order_amount = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        unique_together = ("user", "code")

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at


class WishlistItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="wishlist_items")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        unique_together = ("user", "product")


class RecentViewedProduct(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recent_viewed_products")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="recent_viewed_products")
    viewed_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-viewed_at", "-id"]
        unique_together = ("user", "product")


class OneToOneInquiry(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "OPEN"
        ANSWERED = "ANSWERED", "ANSWERED"
        CLOSED = "CLOSED", "CLOSED"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="inquiries")
    title = models.CharField(max_length=200)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    answer = models.TextField(blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
