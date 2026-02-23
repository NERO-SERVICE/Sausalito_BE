from django.urls import path

from .views import (
    ProductReviewSummaryAPIView,
    ReviewEligibleProductsAPIView,
    ReviewListCreateAPIView,
    ReviewReportCreateAPIView,
)

urlpatterns = [
    path("reviews", ReviewListCreateAPIView.as_view(), name="reviews"),
    path("reviews/eligible-products", ReviewEligibleProductsAPIView.as_view(), name="review-eligible-products"),
    path("reviews/<int:review_id>/report", ReviewReportCreateAPIView.as_view(), name="review-report"),
    path(
        "products/<int:product_id>/reviews/summary",
        ProductReviewSummaryAPIView.as_view(),
        name="product-reviews-summary",
    ),
]
