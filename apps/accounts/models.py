from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractUser):
    class AdminRole(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", "SUPER_ADMIN"
        OPS = "OPS", "OPS"
        CS = "CS", "CS"
        WAREHOUSE = "WAREHOUSE", "WAREHOUSE"
        FINANCE = "FINANCE", "FINANCE"
        MARKETING = "MARKETING", "MARKETING"
        READ_ONLY = "READ_ONLY", "READ_ONLY"

    username = models.CharField(max_length=150, unique=True, blank=True)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    kakao_sub = models.CharField(max_length=255, unique=True, null=True, blank=True)
    terms_agreed_at = models.DateTimeField(null=True, blank=True)
    privacy_collect_agreed_at = models.DateTimeField(null=True, blank=True)
    age_over_14_agreed_at = models.DateTimeField(null=True, blank=True)
    health_functional_food_notice_agreed_at = models.DateTimeField(null=True, blank=True)
    sms_marketing_opt_in = models.BooleanField(default=False)
    sms_marketing_opt_in_at = models.DateTimeField(null=True, blank=True)
    email_marketing_opt_in = models.BooleanField(default=False)
    email_marketing_opt_in_at = models.DateTimeField(null=True, blank=True)
    admin_role = models.CharField(max_length=24, choices=AdminRole.choices, default=AdminRole.READ_ONLY)
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
    class Category(models.TextChoices):
        DELIVERY = "DELIVERY", "DELIVERY"
        RETURN_REFUND = "RETURN_REFUND", "RETURN_REFUND"
        PAYMENT = "PAYMENT", "PAYMENT"
        ORDER = "ORDER", "ORDER"
        PRODUCT = "PRODUCT", "PRODUCT"
        ETC = "ETC", "ETC"

    class Priority(models.TextChoices):
        LOW = "LOW", "LOW"
        NORMAL = "NORMAL", "NORMAL"
        HIGH = "HIGH", "HIGH"
        URGENT = "URGENT", "URGENT"

    class Status(models.TextChoices):
        OPEN = "OPEN", "OPEN"
        ANSWERED = "ANSWERED", "ANSWERED"
        CLOSED = "CLOSED", "CLOSED"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="inquiries")
    title = models.CharField(max_length=200)
    content = models.TextField()
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.ETC)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    channel = models.CharField(max_length=20, default="WEB")
    assigned_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_inquiries",
    )
    internal_note = models.TextField(blank=True)
    answer = models.TextField(blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    sla_due_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class AuditLog(models.Model):
    class Result(models.TextChoices):
        SUCCESS = "SUCCESS", "SUCCESS"
        FAIL = "FAIL", "FAIL"

    occurred_at = models.DateTimeField(auto_now_add=True)
    actor_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    actor_role = models.CharField(max_length=24, blank=True)
    action = models.CharField(max_length=120)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=120, blank=True)
    request_id = models.CharField(max_length=120, blank=True)
    idempotency_key = models.CharField(max_length=64, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    before_json = models.JSONField(default=dict, blank=True)
    after_json = models.JSONField(default=dict, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    result = models.CharField(max_length=10, choices=Result.choices, default=Result.SUCCESS)
    error_code = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["occurred_at"]),
            models.Index(fields=["action", "occurred_at"]),
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["actor_admin", "occurred_at"]),
        ]


class IdempotencyRecord(models.Model):
    key = models.CharField(max_length=64, unique=True)
    action = models.CharField(max_length=120)
    actor_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="idempotency_records",
    )
    request_hash = models.CharField(max_length=64)
    response_status_code = models.PositiveIntegerField(default=200)
    response_body = models.JSONField(default=dict, blank=True)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
