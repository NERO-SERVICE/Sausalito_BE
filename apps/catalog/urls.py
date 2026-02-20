from django.urls import path

from .views import (
    BrandBannerListAPIView,
    BrandPageAPIView,
    HomeBannerListAPIView,
    ProductDetailAPIView,
    ProductDetailMetaAPIView,
    ProductListAPIView,
)

urlpatterns = [
    path("banners/home", HomeBannerListAPIView.as_view(), name="home-banners"),
    path("banners/brand", BrandBannerListAPIView.as_view(), name="brand-banners"),
    path("brand/page", BrandPageAPIView.as_view(), name="brand-page"),
    path("products", ProductListAPIView.as_view(), name="products"),
    path("products/<int:pk>", ProductDetailAPIView.as_view(), name="product-detail"),
    path("products/<int:pk>/detail-meta", ProductDetailMetaAPIView.as_view(), name="product-detail-meta"),
]
