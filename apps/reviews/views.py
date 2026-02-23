from __future__ import annotations

from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import ListCreateAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from apps.common.response import success_response

from .models import Review, ReviewReport
from .serializers import (
    EligibleReviewProductSerializer,
    ReviewCreateSerializer,
    ReviewListSerializer,
    ReviewReportCreateSerializer,
    build_eligible_review_products,
)


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
        request_user = getattr(self.request, "user", None)
        if request_user and request_user.is_authenticated:
            queryset = queryset.prefetch_related(
                Prefetch(
                    "reports",
                    queryset=ReviewReport.objects.filter(reporter_id=request_user.id).only("id", "review_id"),
                    to_attr="reported_by_current_user",
                )
            )

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


class ReviewEligibleProductsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        rows = build_eligible_review_products(user=request.user)
        serializer = EligibleReviewProductSerializer(rows, many=True)
        return success_response(serializer.data)


class ReviewReportCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, review_id: int, *args, **kwargs):
        review = get_object_or_404(Review.objects.select_related("user"), id=review_id)
        if review.status != Review.Status.VISIBLE:
            raise ValidationError("신고 가능한 리뷰가 아닙니다.")
        if review.user_id == request.user.id:
            raise ValidationError("본인이 작성한 리뷰는 신고할 수 없습니다.")

        serializer = ReviewReportCreateSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        reason = payload.get("reason", ReviewReport.Reason.ETC)
        detail = (payload.get("detail") or "").strip()

        report, created = ReviewReport.objects.get_or_create(
            review=review,
            reporter=request.user,
            defaults={
                "reason": reason,
                "detail": detail,
                "status": ReviewReport.Status.PENDING,
            },
        )

        if not created:
            report.reason = reason
            report.detail = detail
            report.status = ReviewReport.Status.PENDING
            report.handled_at = None
            report.handled_by = None
            report.save(update_fields=["reason", "detail", "status", "handled_at", "handled_by", "updated_at"])

        return success_response(
            {
                "review_id": review.id,
                "status": report.status,
                "reason": report.reason,
                "detail": report.detail,
                "created_at": report.created_at,
            },
            message="리뷰 신고가 접수되었습니다." if created else "리뷰 신고 내용이 업데이트되었습니다.",
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
