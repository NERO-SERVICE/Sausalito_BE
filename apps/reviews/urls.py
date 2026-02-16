from django.urls import path

from .views import ProductReviewSummaryAPIView, ReviewListCreateAPIView

urlpatterns = [
    path("reviews", ReviewListCreateAPIView.as_view(), name="reviews"),
    path(
        "products/<int:product_id>/reviews/summary",
        ProductReviewSummaryAPIView.as_view(),
        name="product-reviews-summary",
    ),
]
