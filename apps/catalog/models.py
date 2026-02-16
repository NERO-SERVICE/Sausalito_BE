from __future__ import annotations

from django.db import models

from apps.common.file_utils import (
    banner_image_upload_to,
    product_detail_image_upload_to,
    product_image_upload_to,
    validate_image_file,
)


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    name = models.CharField(max_length=255)
    one_line = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    intake = models.TextField(blank=True)
    target = models.TextField(blank=True)
    ingredients = models.JSONField(default=list, blank=True)
    cautions = models.JSONField(default=list, blank=True)
    faq = models.JSONField(default=list, blank=True)
    price = models.PositiveIntegerField()
    original_price = models.PositiveIntegerField()
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    release_date = models.DateField(null=True, blank=True)
    popular_score = models.PositiveIntegerField(default=0)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    review_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(
        upload_to=product_image_upload_to,
        validators=[validate_image_file],
        null=True,
        blank=True,
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_thumbnail = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "id"]


class ProductBadge(models.Model):
    class BadgeType(models.TextChoices):
        HOT = "HOT", "HOT"
        BESTSELLER = "BESTSELLER", "BESTSELLER"
        DISCOUNT = "DISCOUNT", "DISCOUNT"
        NEW = "NEW", "NEW"
        RECOMMENDED = "RECOMMENDED", "RECOMMENDED"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="badges")
    badge_type = models.CharField(max_length=20, choices=BadgeType.choices)

    class Meta:
        unique_together = ("product", "badge_type")
        ordering = ["id"]


class ProductOption(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=255)
    price = models.PositiveIntegerField()
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]


class ProductDetailMeta(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="detail_meta")
    coupon_text = models.CharField(max_length=255, blank=True)
    shipping_fee = models.PositiveIntegerField(default=3000)
    free_shipping_threshold = models.PositiveIntegerField(default=50000)
    interest_free_text = models.CharField(max_length=255, blank=True)
    purchase_types = models.JSONField(default=list, blank=True)
    subscription_benefit = models.CharField(max_length=255, blank=True)
    options_label = models.CharField(max_length=100, default="상품구성")
    add_ons = models.JSONField(default=list, blank=True)
    today_ship_text = models.CharField(max_length=255, blank=True)
    inquiry_count = models.PositiveIntegerField(default=0)


class ProductDetailImage(models.Model):
    detail_meta = models.ForeignKey(ProductDetailMeta, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(
        upload_to=product_detail_image_upload_to,
        validators=[validate_image_file],
        null=True,
        blank=True,
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]


class HomeBanner(models.Model):
    subtitle = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    cta_text = models.CharField(max_length=100, blank=True)
    image = models.ImageField(
        upload_to=banner_image_upload_to,
        validators=[validate_image_file],
        null=True,
        blank=True,
    )
    link_url = models.CharField(max_length=500, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]
