from __future__ import annotations

from django.conf import settings
from django.db.models import Avg, Count
from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import Product
from apps.orders.models import Order, OrderItem

from .models import Review, ReviewImage, ReviewReport


def has_valid_image_file(field_file) -> bool:
    if not field_file or not getattr(field_file, "name", ""):
        return False
    try:
        return field_file.storage.exists(field_file.name)
    except Exception:
        return False


def get_eligible_order_items_for_review(
    *,
    user,
    product_id: int | None = None,
    order_item_id: int | None = None,
):
    eligible_product_order_statuses = (
        Order.ProductOrderStatus.DELIVERED,
        Order.ProductOrderStatus.PURCHASE_CONFIRMED,
    )
    queryset = (
        OrderItem.objects.select_related("order", "product")
        .filter(
            order__user=user,
            order__product_order_status__in=eligible_product_order_statuses,
            product__is_active=True,
        )
        .exclude(reviews__user=user)
        .order_by("-order__delivered_at", "-order__created_at", "-id")
    )

    if product_id:
        queryset = queryset.filter(product_id_snapshot=int(product_id))
    if order_item_id:
        queryset = queryset.filter(id=int(order_item_id))
    return queryset


def build_eligible_review_order_items(*, user, product_id: int | None = None) -> list[dict]:
    rows = get_eligible_order_items_for_review(user=user, product_id=product_id)
    order_items: list[dict] = []
    for row in rows:
        resolved_product_id = int(row.product_id_snapshot or (row.product.id if row.product_id and row.product else 0))
        if resolved_product_id <= 0:
            continue

        order_items.append(
            {
                "order_item_id": row.id,
                "order_no": row.order.order_no,
                "product_id": resolved_product_id,
                "product_name": row.product_name_snapshot or (row.product.name if row.product else ""),
                "option_name": row.option_name_snapshot or "",
                "quantity": row.quantity,
                "ordered_at": row.order.created_at,
                "delivered_at": row.order.delivered_at,
                "product_order_status": row.order.product_order_status,
            }
        )

    return order_items


class EligibleReviewOrderItemSerializer(serializers.Serializer):
    order_item_id = serializers.IntegerField()
    order_no = serializers.CharField()
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    option_name = serializers.CharField(allow_blank=True)
    quantity = serializers.IntegerField()
    ordered_at = serializers.DateTimeField()
    delivered_at = serializers.DateTimeField(allow_null=True)
    product_order_status = serializers.CharField()


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
    is_best = serializers.BooleanField(read_only=True)
    isBest = serializers.BooleanField(source="is_best", read_only=True)
    admin_reply = serializers.CharField(read_only=True)
    adminReply = serializers.CharField(source="admin_reply", read_only=True)
    answer = serializers.CharField(source="admin_reply", read_only=True)
    answered_at = serializers.DateTimeField(source="admin_replied_at", read_only=True)
    answeredAt = serializers.DateTimeField(source="admin_replied_at", read_only=True)
    answered_by = serializers.SerializerMethodField()
    answeredBy = serializers.SerializerMethodField()
    is_reported_by_me = serializers.SerializerMethodField()
    isReportedByMe = serializers.SerializerMethodField()

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
            "is_best",
            "isBest",
            "admin_reply",
            "adminReply",
            "answer",
            "answered_at",
            "answeredAt",
            "answered_by",
            "answeredBy",
            "is_reported_by_me",
            "isReportedByMe",
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

    def get_answered_by(self, obj: Review) -> str:
        if not obj.admin_reply:
            return ""
        return "관리자"

    def get_answeredBy(self, obj: Review) -> str:
        return self.get_answered_by(obj)

    def get_is_reported_by_me(self, obj: Review) -> bool:
        prefetched = getattr(obj, "reported_by_current_user", None)
        if prefetched is not None:
            return bool(prefetched)

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return ReviewReport.objects.filter(review_id=obj.id, reporter_id=user.id).exists()

    def get_isReportedByMe(self, obj: Review) -> bool:
        return self.get_is_reported_by_me(obj)


class ReviewCreateSerializer(serializers.Serializer):
    order_item_id = serializers.IntegerField()
    product_id = serializers.IntegerField(required=False)
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

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        order_item_id = attrs.get("order_item_id")

        if not user or not user.is_authenticated:
            raise serializers.ValidationError("로그인 후 리뷰를 작성할 수 있습니다.")

        eligible_item = get_eligible_order_items_for_review(user=user, order_item_id=order_item_id).first()
        if not eligible_item:
            raise serializers.ValidationError(
                "상품주문상태가 배송완료 또는 구매확정인 실제 주문건(주문번호-주문상품)만 리뷰를 작성할 수 있습니다."
            )

        if not eligible_item.product_id or not eligible_item.product or not eligible_item.product.is_active:
            raise serializers.ValidationError("리뷰 작성 가능한 상품 정보를 확인할 수 없습니다.")

        matched_product_id = int(eligible_item.product_id_snapshot or eligible_item.product.id)
        requested_product_id = attrs.get("product_id")
        if requested_product_id and int(requested_product_id) != matched_product_id:
            raise serializers.ValidationError("선택한 주문건과 상품 정보가 일치하지 않습니다.")

        attrs["_matched_order_item"] = eligible_item
        attrs["_matched_product"] = eligible_item.product
        attrs["product_id"] = matched_product_id
        return attrs

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
        matched_order_item = validated_data.pop("_matched_order_item", None)
        product = validated_data.pop("_matched_product", None) or Product.objects.get(id=validated_data["product_id"])
        review = Review.objects.create(
            product=product,
            user=self.context["request"].user,
            order_item=matched_order_item,
            score=validated_data["score"],
            title=validated_data.get("title", ""),
            content=validated_data["content"],
        )

        for index, image in enumerate(images):
            ReviewImage.objects.create(review=review, image=image, sort_order=index)

        refresh_product_rating(product)
        return review


class ReviewReportCreateSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ReviewReport.Reason.choices, required=False, default=ReviewReport.Reason.ETC)
    detail = serializers.CharField(required=False, allow_blank=True, max_length=500)


def refresh_product_rating(product: Product) -> None:
    summary = product.reviews.filter(status=Review.Status.VISIBLE).aggregate(avg=Avg("score"), cnt=Count("id"))
    product.rating_avg = summary["avg"] or 0
    product.review_count = summary["cnt"] or 0
    product.save(update_fields=["rating_avg", "review_count", "updated_at"])


class ReviewSummarySerializer(serializers.Serializer):
    average = serializers.FloatField()
    count = serializers.IntegerField()
    distribution = serializers.DictField(child=serializers.IntegerField())
