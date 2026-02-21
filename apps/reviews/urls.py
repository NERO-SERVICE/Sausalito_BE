from django.urls import path

from .views import ProductReviewSummaryAPIView, ReviewListCreateAPIView, ReviewReportCreateAPIView

urlpatterns = [
    path("reviews", ReviewListCreateAPIView.as_view(), name="reviews"),
    path("reviews/<int:review_id>/report", ReviewReportCreateAPIView.as_view(), name="review-report"),
    path(
        "products/<int:product_id>/reviews/summary",
        ProductReviewSummaryAPIView.as_view(),
        name="product-reviews-summary",
    ),
]
