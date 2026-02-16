from __future__ import annotations

from django.conf import settings
from django.db.models import Avg, Count
from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import Product

from .models import Review, ReviewImage


def has_valid_image_file(field_file) -> bool:
    if not field_file or not getattr(field_file, "name", ""):
        return False
    try:
        return field_file.storage.exists(field_file.name)
    except Exception:
        return False


class ReviewImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ReviewImage
        fields = ("url", "sort_order")

    def get_url(self, obj: ReviewImage) -> str:
        if not has_valid_image_file(obj.image):
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url


class ReviewListSerializer(serializers.ModelSerializer):
    user_masked = serializers.SerializerMethodField()
    images = ReviewImageSerializer(many=True, read_only=True)
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    helpful = serializers.IntegerField(source="helpful_count", read_only=True)

    # FE 호환 필드
    productId = serializers.IntegerField(source="product.id", read_only=True)
    user = serializers.SerializerMethodField()
    text = serializers.CharField(source="content", read_only=True)
    date = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = (
            "id",
            "product_id",
            "productId",
            "user_masked",
            "user",
            "score",
            "title",
            "content",
            "text",
            "images",
            "image",
            "helpful_count",
            "helpful",
            "created_at",
            "date",
        )

    def get_user_masked(self, obj: Review) -> str:
        source = obj.user.name or obj.user.email.split("@")[0]
        if len(source) <= 1:
            return source + "*"
        return source[0] + "**"

    def get_user(self, obj: Review) -> str:
        return self.get_user_masked(obj)

    def get_date(self, obj: Review) -> str:
        return timezone.localtime(obj.created_at).strftime("%Y.%m.%d")

    def get_image(self, obj: Review) -> str:
        first = next((image for image in obj.images.all() if has_valid_image_file(image.image)), None)
        if not first:
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(first.image.url)
        return first.image.url


class ReviewCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    score = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    content = serializers.CharField()
    images = serializers.ListField(
        child=serializers.ImageField(),
        required=False,
        allow_empty=True,
    )

    def validate_product_id(self, value: int) -> int:
        if not Product.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("유효한 상품이 아닙니다.")
        return value

    def validate_images(self, files):
        max_images = settings.MAX_REVIEW_IMAGES
        if len(files) > max_images:
            raise serializers.ValidationError(f"이미지는 최대 {max_images}장까지 업로드할 수 있습니다.")

        max_size = settings.MAX_REVIEW_IMAGE_SIZE_MB * 1024 * 1024
        for file_obj in files:
            if file_obj.size > max_size:
                raise serializers.ValidationError(
                    f"이미지 파일은 {settings.MAX_REVIEW_IMAGE_SIZE_MB}MB 이하만 업로드 가능합니다."
                )
        return files

    def create(self, validated_data):
        images = validated_data.pop("images", [])
        product = Product.objects.get(id=validated_data["product_id"])
        review = Review.objects.create(
            product=product,
            user=self.context["request"].user,
            score=validated_data["score"],
            title=validated_data.get("title", ""),
            content=validated_data["content"],
        )

        for index, image in enumerate(images):
            ReviewImage.objects.create(review=review, image=image, sort_order=index)

        refresh_product_rating(product)
        return review


def refresh_product_rating(product: Product) -> None:
    summary = product.reviews.filter(status=Review.Status.VISIBLE).aggregate(avg=Avg("score"), cnt=Count("id"))
    product.rating_avg = summary["avg"] or 0
    product.review_count = summary["cnt"] or 0
    product.save(update_fields=["rating_avg", "review_count", "updated_at"])


class ReviewSummarySerializer(serializers.Serializer):
    average = serializers.FloatField()
    count = serializers.IntegerField()
    distribution = serializers.DictField(child=serializers.IntegerField())
