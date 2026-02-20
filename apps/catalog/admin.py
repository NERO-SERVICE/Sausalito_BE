from django.contrib import admin

from .models import (
    BrandPageSetting,
    BrandStorySection,
    Category,
    HomeBanner,
    Product,
    ProductBadge,
    ProductDetailImage,
    ProductDetailMeta,
    ProductImage,
    ProductOption,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class ProductBadgeInline(admin.TabularInline):
    model = ProductBadge
    extra = 0


class ProductOptionInline(admin.TabularInline):
    model = ProductOption
    extra = 0


class ProductDetailImageInline(admin.TabularInline):
    model = ProductDetailImage
    extra = 0


class ProductDetailMetaInline(admin.StackedInline):
    model = ProductDetailMeta
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "price", "stock", "popular_score", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "one_line", "description")
    inlines = [ProductImageInline, ProductBadgeInline, ProductOptionInline, ProductDetailMetaInline]


@admin.register(ProductDetailMeta)
class ProductDetailMetaAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "shipping_fee", "free_shipping_threshold", "inquiry_count")
    inlines = [ProductDetailImageInline]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(HomeBanner)
class HomeBannerAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")


@admin.register(BrandPageSetting)
class BrandPageSettingAdmin(admin.ModelAdmin):
    list_display = ("id", "hero_eyebrow", "hero_title", "updated_at")


@admin.register(BrandStorySection)
class BrandStorySectionAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "sort_order", "is_active", "updated_at")
    list_editable = ("sort_order", "is_active")
