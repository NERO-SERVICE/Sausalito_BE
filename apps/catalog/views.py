from __future__ import annotations

from django.db.models import Q
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.views import APIView

from apps.common.response import success_response

from .models import (
    BrandPageSetting,
    BrandStorySection,
    DEFAULT_BRAND_HERO_DESCRIPTION,
    DEFAULT_BRAND_HERO_EYEBROW,
    DEFAULT_BRAND_HERO_TITLE,
    HomeBanner,
    Product,
)
from .serializers import (
    BrandPageSettingSerializer,
    BrandStorySectionSerializer,
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


def parse_limit(raw_limit: str | None, *, default: int, max_limit: int = 20) -> int:
    if not raw_limit:
        return default
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return default
    if limit <= 0:
        return default
    return min(limit, max_limit)


class HomeBannerListAPIView(APIView):
    def get(self, request, *args, **kwargs):
        banners = HomeBanner.objects.filter(is_active=True).order_by("sort_order", "id")
        raw_limit = request.query_params.get("limit")
        if raw_limit:
            limit = parse_limit(raw_limit, default=20, max_limit=100)
            banners = banners[:limit]
        return success_response(HomeBannerSerializer(banners, many=True, context={"request": request}).data)


class BrandBannerListAPIView(APIView):
    def get(self, request, *args, **kwargs):
        limit = parse_limit(request.query_params.get("limit"), default=2, max_limit=20)
        banners = (
            HomeBanner.objects.filter(is_active=True)
            .exclude(image__isnull=True)
            .exclude(image="")
            .order_by("sort_order", "id")[:limit]
        )
        return success_response(HomeBannerSerializer(banners, many=True, context={"request": request}).data)


class BrandPageAPIView(APIView):
    def get(self, request, *args, **kwargs):
        row = BrandPageSetting.objects.order_by("id").first()
        if not row:
            row = BrandPageSetting(
                hero_eyebrow=DEFAULT_BRAND_HERO_EYEBROW,
                hero_title=DEFAULT_BRAND_HERO_TITLE,
                hero_description=DEFAULT_BRAND_HERO_DESCRIPTION,
            )

        sections = BrandStorySection.objects.filter(is_active=True).order_by("sort_order", "id")
        return success_response(
            {
                "hero": BrandPageSettingSerializer(row).data,
                "sections": BrandStorySectionSerializer(sections, many=True, context={"request": request}).data,
            }
        )


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
        product = (
            Product.objects.filter(pk=pk, is_active=True)
            .select_related("detail_meta")
            .prefetch_related("detail_meta__images", "options")
            .first()
        )
        if not product:
            return success_response(None)
        detail_meta = getattr(product, "detail_meta", None)
        if not detail_meta:
            return success_response(None)
        return success_response(ProductDetailMetaSerializer(detail_meta, context={"request": request}).data)
