from __future__ import annotations

from rest_framework import serializers

from .models import HomeBanner, Product, ProductBadge, ProductDetailMeta, ProductImage, ProductOption

BADGE_LABEL_MAP = {
    ProductBadge.BadgeType.HOT: "HOT",
    ProductBadge.BadgeType.BESTSELLER: "베스트셀러",
    ProductBadge.BadgeType.DISCOUNT: "할인",
    ProductBadge.BadgeType.NEW: "신상품",
    ProductBadge.BadgeType.RECOMMENDED: "추천",
}


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.CharField(source="image_url")

    class Meta:
        model = ProductImage
        fields = ("url", "is_thumbnail", "sort_order")


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
        thumbnail = obj.images.filter(is_thumbnail=True).first() or obj.images.first()
        return thumbnail.image_url if thumbnail else ""

    def get_badges(self, obj: Product) -> list[str]:
        return [BADGE_LABEL_MAP.get(b.badge_type, b.badge_type) for b in obj.badges.all()]


class ProductDetailSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
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

    def get_review_summary(self, obj: Product) -> dict:
        return {
            "avg": obj.rating_avg,
            "count": obj.review_count,
        }


class ProductDetailMetaSerializer(serializers.ModelSerializer):
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


class HomeBannerSerializer(serializers.ModelSerializer):
    image = serializers.CharField(source="image_url")
    cta = serializers.CharField(source="cta_text")
    link = serializers.CharField(source="link_url")

    class Meta:
        model = HomeBanner
        fields = ("id", "subtitle", "title", "description", "cta", "link", "image")
