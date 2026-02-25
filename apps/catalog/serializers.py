from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import UserCoupon
from apps.common.media_utils import build_public_file_url, has_accessible_file_reference

from .models import (
    BrandPageSetting,
    BrandStorySection,
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
    return has_accessible_file_reference(field_file)


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ("url", "is_thumbnail", "sort_order")

    def get_url(self, obj: ProductImage) -> str:
        if not has_valid_image_file(obj.image):
            return ""
        return build_public_file_url(obj.image, request=self.context.get("request"))


class ProductOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductOption
        fields = ("id", "duration_months", "benefit_label", "name", "price", "stock", "is_active")


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

        return build_public_file_url(thumbnail.image, request=self.context.get("request"))

    def get_badges(self, obj: Product) -> list[str]:
        return [BADGE_LABEL_MAP.get(b.badge_type, b.badge_type) for b in obj.badges.all()]


class ProductDetailSerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()
    badges = serializers.SerializerMethodField()
    review_summary = serializers.SerializerMethodField()
    coupon_benefit = serializers.SerializerMethodField()

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
            "coupon_benefit",
        )

    def get_badges(self, obj: Product) -> list[str]:
        return [BADGE_LABEL_MAP.get(b.badge_type, b.badge_type) for b in obj.badges.all()]

    def get_images(self, obj: Product) -> list[dict]:
        valid_images = [image for image in obj.images.all() if has_valid_image_file(image.image)]
        return ProductImageSerializer(valid_images, many=True, context=self.context).data

    def get_options(self, obj: Product) -> list[dict]:
        queryset = obj.options.filter(is_active=True).order_by("duration_months", "id")
        return ProductOptionSerializer(queryset, many=True).data

    def get_review_summary(self, obj: Product) -> dict:
        return {
            "avg": obj.rating_avg,
            "count": obj.review_count,
        }

    def get_coupon_benefit(self, obj: Product) -> dict:
        request = self.context.get("request")
        user = getattr(request, "user", None)

        base_price = int(obj.price or 0)
        base_original_price = int(obj.original_price or base_price or 0)
        if base_original_price <= 0:
            base_original_price = max(base_price, 1)

        def calc_discount_rate(original_price: int, discounted_price: int) -> float:
            if original_price <= 0:
                return 0.0
            rate = (1 - (discounted_price / original_price)) * 100
            return round(max(rate, 0.0), 2)

        result = {
            "is_authenticated": bool(user and user.is_authenticated),
            "has_available_coupon": False,
            "has_eligible_coupon": False,
            "available_coupon_count": 0,
            "eligible_coupon_count": 0,
            "soon_expiring_coupon_count": 0,
            "base_price": base_price,
            "base_original_price": base_original_price,
            "base_discount_rate": calc_discount_rate(base_original_price, base_price),
            "max_extra_discount_rate": 0.0,
            "max_final_discount_rate": calc_discount_rate(base_original_price, base_price),
            "price_after_best_coupon": base_price,
            "marketing_copy": "로그인하면 보유 쿠폰 기반 추가 할인 혜택을 확인할 수 있어요.",
            "best_coupon": None,
            "coupon_items": [],
        }
        if not (user and user.is_authenticated):
            return result

        now = timezone.now()
        valid_coupons = [
            row
            for row in UserCoupon.objects.filter(user=user, is_used=False).order_by("-discount_amount", "expires_at", "-id")
            if not row.is_expired
        ]

        soon_expiring_threshold = now + timedelta(days=3)
        coupon_items: list[dict] = []
        for row in valid_coupons:
            min_order_amount = int(row.min_order_amount or 0)
            discount_amount = int(row.discount_amount or 0)
            is_eligible = base_price >= min_order_amount
            required_amount = max(min_order_amount - base_price, 0)
            applied_discount_amount = min(base_price, discount_amount) if is_eligible else 0
            final_price = max(base_price - applied_discount_amount, 0)
            extra_discount_rate = round((applied_discount_amount / base_price) * 100, 2) if base_price > 0 else 0.0
            final_discount_rate = calc_discount_rate(base_original_price, final_price)

            coupon_items.append(
                {
                    "id": int(row.id),
                    "name": row.name,
                    "code": row.code,
                    "discount_amount": discount_amount,
                    "min_order_amount": min_order_amount,
                    "expires_at": row.expires_at,
                    "is_eligible": is_eligible,
                    "required_amount": required_amount,
                    "applied_discount_amount": applied_discount_amount,
                    "final_price": final_price,
                    "extra_discount_rate": extra_discount_rate,
                    "final_discount_rate": final_discount_rate,
                }
            )

        eligible_items = [item for item in coupon_items if item["is_eligible"]]
        eligible_items.sort(
            key=lambda item: (item["applied_discount_amount"], item["final_discount_rate"]),
            reverse=True,
        )
        best_coupon = eligible_items[0] if eligible_items else None
        soon_expiring_coupon_count = sum(
            1
            for row in valid_coupons
            if row.expires_at and now <= row.expires_at <= soon_expiring_threshold
        )

        result.update(
            {
                "has_available_coupon": bool(valid_coupons),
                "has_eligible_coupon": bool(eligible_items),
                "available_coupon_count": len(valid_coupons),
                "eligible_coupon_count": len(eligible_items),
                "soon_expiring_coupon_count": soon_expiring_coupon_count,
                "best_coupon": best_coupon,
                "coupon_items": coupon_items,
            }
        )

        if best_coupon:
            result["max_extra_discount_rate"] = best_coupon["extra_discount_rate"]
            result["max_final_discount_rate"] = best_coupon["final_discount_rate"]
            result["price_after_best_coupon"] = best_coupon["final_price"]
            result["marketing_copy"] = (
                f"보유 쿠폰으로 최대 {best_coupon['applied_discount_amount']:,}원 추가 할인받을 수 있어요."
            )
        elif valid_coupons:
            min_required = min((item["required_amount"] for item in coupon_items), default=0)
            result["marketing_copy"] = (
                f"보유 쿠폰 {len(valid_coupons)}장 · {min_required:,}원 더 담으면 쿠폰 적용이 가능해요."
                if min_required > 0
                else "보유 쿠폰 조건을 확인하고 추가 할인을 적용해보세요."
            )
        else:
            result["marketing_copy"] = "사용 가능한 쿠폰이 없습니다. 신규/이벤트 쿠폰을 확인해보세요."

        return result


class ProductDetailImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProductDetailImage
        fields = ("url", "sort_order")

    def get_url(self, obj: ProductDetailImage) -> str:
        if not has_valid_image_file(obj.image):
            return ""
        return build_public_file_url(obj.image, request=self.context.get("request"))


class ProductDetailMetaSerializer(serializers.ModelSerializer):
    detail_images = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()

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
            "options",
            "add_ons",
            "today_ship_text",
            "inquiry_count",
            "detail_images",
        )

    def get_detail_images(self, obj: ProductDetailMeta) -> list[str]:
        valid_images = [image for image in obj.images.all() if has_valid_image_file(image.image)]
        serializer = ProductDetailImageSerializer(valid_images, many=True, context=self.context)
        return [row["url"] for row in serializer.data]

    def get_options(self, obj: ProductDetailMeta) -> list[dict]:
        queryset = obj.product.options.filter(is_active=True).order_by("duration_months", "id")
        return ProductOptionSerializer(queryset, many=True).data


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
        return build_public_file_url(obj.image, request=self.context.get("request"))


class BrandPageSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandPageSetting
        fields = ("hero_eyebrow", "hero_title", "hero_description")


class BrandStorySectionSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = BrandStorySection
        fields = (
            "id",
            "eyebrow",
            "title",
            "description",
            "image",
            "image_alt",
            "sort_order",
        )

    def get_image(self, obj: BrandStorySection) -> str:
        if not has_valid_image_file(obj.image):
            return ""
        return build_public_file_url(obj.image, request=self.context.get("request"))
