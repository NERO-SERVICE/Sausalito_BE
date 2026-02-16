from __future__ import annotations

from django.db.models import Q
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.views import APIView

from apps.common.response import success_response

from .models import HomeBanner, Product
from .serializers import (
    HomeBannerSerializer,
    ProductDetailMetaSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
)

SORTING_MAP = {
    "popular": "-popular_score",
    "newest": "-release_date",
    "priceAsc": "price",
    "priceDesc": "-price",
    "review": "-review_count",
}


class HomeBannerListAPIView(APIView):
    def get(self, request, *args, **kwargs):
        banners = HomeBanner.objects.filter(is_active=True).order_by("sort_order", "id")
        return success_response(HomeBannerSerializer(banners, many=True).data)


class ProductListAPIView(ListAPIView):
    serializer_class = ProductListSerializer

    def get_queryset(self):
        queryset = (
            Product.objects.filter(is_active=True)
            .prefetch_related("images", "badges")
            .order_by("-popular_score", "id")
        )

        q = self.request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(name__icontains=q) | Q(one_line__icontains=q) | Q(description__icontains=q)
            )

        min_price = self.request.query_params.get("min_price")
        max_price = self.request.query_params.get("max_price")
        if min_price and str(min_price).isdigit():
            queryset = queryset.filter(price__gte=int(min_price))
        if max_price and str(max_price).isdigit():
            queryset = queryset.filter(price__lte=int(max_price))

        sort = self.request.query_params.get("sort")
        if sort in SORTING_MAP:
            queryset = queryset.order_by(SORTING_MAP[sort], "id")

        return queryset


class ProductDetailAPIView(RetrieveAPIView):
    queryset = Product.objects.filter(is_active=True).prefetch_related("images", "badges", "options")
    serializer_class = ProductDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response(serializer.data)


class ProductDetailMetaAPIView(APIView):
    def get(self, request, pk: int, *args, **kwargs):
        product = Product.objects.filter(pk=pk, is_active=True).select_related("detail_meta").first()
        if not product:
            return success_response(None)
        detail_meta = getattr(product, "detail_meta", None)
        if not detail_meta:
            return success_response(None)
        return success_response(ProductDetailMetaSerializer(detail_meta).data)
