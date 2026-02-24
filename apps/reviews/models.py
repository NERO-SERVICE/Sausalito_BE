from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.file_utils import review_image_upload_to, validate_image_file


class Review(models.Model):
    class Status(models.TextChoices):
        VISIBLE = "VISIBLE", "VISIBLE"
        HIDDEN = "HIDDEN", "HIDDEN"
        DELETED = "DELETED", "DELETED"

    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    order_item = models.ForeignKey(
        "orders.OrderItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviews",
    )
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=255, blank=True)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.VISIBLE)
    is_best = models.BooleanField(default=False)
    admin_reply = models.TextField(blank=True, default="")
    admin_replied_at = models.DateTimeField(null=True, blank=True)
    admin_replied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="review_replies",
    )
    helpful_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "order_item"],
                name="uniq_review_user_order_item",
            )
        ]


class ReviewImage(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=review_image_upload_to, validators=[validate_image_file])
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def clean(self) -> None:
        if not self.review_id:
            return

        max_images = getattr(settings, "MAX_REVIEW_IMAGES", 3)
        existing_count = (
            ReviewImage.objects.filter(review_id=self.review_id)
            .exclude(pk=self.pk)
            .count()
        )
        if existing_count >= max_images:
            raise ValidationError(f"리뷰 이미지는 최대 {max_images}장까지 등록할 수 있습니다.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ReviewHelpful(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="helpful_users")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_helpful")

    class Meta:
        unique_together = ("review", "user")


class ReviewReport(models.Model):
    class Reason(models.TextChoices):
        ABUSE = "ABUSE", "ABUSE"
        ADVERTISEMENT = "ADVERTISEMENT", "ADVERTISEMENT"
        PERSONAL_INFO = "PERSONAL_INFO", "PERSONAL_INFO"
        IRRELEVANT = "IRRELEVANT", "IRRELEVANT"
        ETC = "ETC", "ETC"

    class Status(models.TextChoices):
        PENDING = "PENDING", "PENDING"
        RESOLVED = "RESOLVED", "RESOLVED"
        REJECTED = "REJECTED", "REJECTED"

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_reports")
    reason = models.CharField(max_length=32, choices=Reason.choices, default=Reason.ETC)
    detail = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    handled_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="handled_review_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("review", "reporter")
