from django.urls import path

from .views import (
    HomeBannerListAPIView,
    ProductDetailAPIView,
    ProductDetailMetaAPIView,
    ProductListAPIView,
)

urlpatterns = [
    path("banners/home", HomeBannerListAPIView.as_view(), name="home-banners"),
    path("products", ProductListAPIView.as_view(), name="products"),
    path("products/<int:pk>", ProductDetailAPIView.as_view(), name="product-detail"),
    path("products/<int:pk>/detail-meta", ProductDetailMetaAPIView.as_view(), name="product-detail-meta"),
]
