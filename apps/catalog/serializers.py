from __future__ import annotations

from rest_framework import serializers

from .models import (
    HomeBanner,
    Product,
    ProductBadge,
    ProductDetailImage,
    ProductDetailMeta,
    ProductImage,
    ProductOption,
)

BADGE_LABEL_MAP = {
    ProductBadge.BadgeType.HOT: "HOT",
    ProductBadge.BadgeType.BESTSELLER: "베스트셀러",
    ProductBadge.BadgeType.DISCOUNT: "할인",
    ProductBadge.BadgeType.NEW: "신상품",
    ProductBadge.BadgeType.RECOMMENDED: "추천",
}


def has_valid_image_file(field_file) -> bool:
    if not field_file or not getattr(field_file, "name", ""):
        return False
    try:
        return field_file.storage.exists(field_file.name)
    except Exception:
        return False


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ("url", "is_thumbnail", "sort_order")

    def get_url(self, obj: ProductImage) -> str:
        if not has_valid_image_file(obj.image):
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url


class ProductOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductOption
        fields = ("id", "name", "price", "stock", "is_active")


class ProductReviewSummarySerializer(serializers.Serializer):
    avg = serializers.DecimalField(max_digits=3, decimal_places=2)
    count = serializers.IntegerField()


class ProductListSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    badges = serializers.SerializerMethodField()
    rating = serializers.DecimalField(source="rating_avg", max_digits=3, decimal_places=2)
    reviews = serializers.IntegerField(source="review_count")
    oneLine = serializers.CharField(source="one_line")
    originalPrice = serializers.IntegerField(source="original_price")
    popularScore = serializers.IntegerField(source="popular_score")
    releaseDate = serializers.DateField(source="release_date")

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "oneLine",
            "description",
            "price",
            "originalPrice",
            "stock",
            "badges",
            "image",
            "rating",
            "reviews",
            "popularScore",
            "releaseDate",
        )

    def get_image(self, obj: Product) -> str:
        ordered_images = list(obj.images.all())
        thumbnail = next(
            (image for image in ordered_images if image.is_thumbnail and has_valid_image_file(image.image)),
            None,
        )
        if not thumbnail:
            thumbnail = next(
                (image for image in ordered_images if has_valid_image_file(image.image)),
                None,
            )
        if not thumbnail:
            return ""

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(thumbnail.image.url)
        return thumbnail.image.url

    def get_badges(self, obj: Product) -> list[str]:
        return [BADGE_LABEL_MAP.get(b.badge_type, b.badge_type) for b in obj.badges.all()]


class ProductDetailSerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()
    options = ProductOptionSerializer(many=True, read_only=True)
    badges = serializers.SerializerMethodField()
    review_summary = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "one_line",
            "description",
            "intake",
            "target",
            "ingredients",
            "cautions",
            "faq",
            "price",
            "original_price",
            "stock",
            "popular_score",
            "rating_avg",
            "review_count",
            "badges",
            "images",
            "options",
            "review_summary",
        )

    def get_badges(self, obj: Product) -> list[str]:
        return [BADGE_LABEL_MAP.get(b.badge_type, b.badge_type) for b in obj.badges.all()]

    def get_images(self, obj: Product) -> list[dict]:
        valid_images = [image for image in obj.images.all() if has_valid_image_file(image.image)]
        return ProductImageSerializer(valid_images, many=True, context=self.context).data

    def get_review_summary(self, obj: Product) -> dict:
        return {
            "avg": obj.rating_avg,
            "count": obj.review_count,
        }


class ProductDetailImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProductDetailImage
        fields = ("url", "sort_order")

    def get_url(self, obj: ProductDetailImage) -> str:
        if not has_valid_image_file(obj.image):
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url


class ProductDetailMetaSerializer(serializers.ModelSerializer):
    detail_images = serializers.SerializerMethodField()

    class Meta:
        model = ProductDetailMeta
        fields = (
            "coupon_text",
            "shipping_fee",
            "free_shipping_threshold",
            "interest_free_text",
            "purchase_types",
            "subscription_benefit",
            "options_label",
            "add_ons",
            "today_ship_text",
            "inquiry_count",
            "detail_images",
        )

    def get_detail_images(self, obj: ProductDetailMeta) -> list[str]:
        valid_images = [image for image in obj.images.all() if has_valid_image_file(image.image)]
        serializer = ProductDetailImageSerializer(valid_images, many=True, context=self.context)
        return [row["url"] for row in serializer.data]


class HomeBannerSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    cta = serializers.CharField(source="cta_text")
    link = serializers.CharField(source="link_url")

    class Meta:
        model = HomeBanner
        fields = ("id", "subtitle", "title", "description", "cta", "link", "image")

    def get_image(self, obj: HomeBanner) -> str:
        if not has_valid_image_file(obj.image):
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url
