from __future__ import annotations

from django.db.models import Count
from rest_framework import status
from rest_framework.generics import ListCreateAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.common.response import success_response

from .models import Review
from .serializers import ReviewCreateSerializer, ReviewListSerializer


class ReviewListCreateAPIView(ListCreateAPIView):
    queryset = (
        Review.objects.filter(status=Review.Status.VISIBLE)
        .select_related("user", "product", "admin_replied_by")
        .prefetch_related("images")
    )
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ReviewCreateSerializer
        return ReviewListSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_queryset(self):
        queryset = self.queryset

        product_id = self.request.query_params.get("product_id")
        if product_id and str(product_id).isdigit():
            queryset = queryset.filter(product_id=int(product_id))

        has_image = self.request.query_params.get("has_image")
        if has_image == "true":
            queryset = queryset.annotate(image_count=Count("images")).filter(image_count__gt=0)

        best_only = str(self.request.query_params.get("best_only", "")).lower()
        if best_only in {"true", "1", "yes", "y"}:
            queryset = queryset.filter(is_best=True)

        sort = self.request.query_params.get("sort", "latest")
        if sort == "helpful":
            queryset = queryset.order_by("-helpful_count", "-id")
        elif sort == "score":
            queryset = queryset.order_by("-score", "-id")
        else:
            queryset = queryset.order_by("-created_at", "-id")

        return queryset

    def create(self, request, *args, **kwargs):
        payload = request.data.copy()
        files = request.FILES.getlist("images")
        if files:
            if hasattr(payload, "setlist"):
                payload.setlist("images", files)
            elif isinstance(payload, dict):
                payload["images"] = files

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        review = serializer.save()

        read_serializer = ReviewListSerializer(review, context={"request": request})
        return success_response(read_serializer.data, message="리뷰가 등록되었습니다.", status_code=status.HTTP_201_CREATED)


class ProductReviewSummaryAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, product_id: int, *args, **kwargs):
        queryset = Review.objects.filter(product_id=product_id, status=Review.Status.VISIBLE)
        count = queryset.count()
        if count == 0:
            data = {
                "average": 0,
                "count": 0,
                "distribution": {str(star): 0 for star in range(1, 6)},
            }
            return success_response(data)

        average = round(sum(queryset.values_list("score", flat=True)) / count, 2)
        distribution = {str(star): queryset.filter(score=star).count() for star in range(1, 6)}
        data = {
            "average": average,
            "count": count,
            "distribution": distribution,
        }
        return success_response(data)
