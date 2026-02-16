from django.contrib import admin

from .models import Review, ReviewHelpful, ReviewImage


class ReviewImageInline(admin.TabularInline):
    model = ReviewImage
    extra = 0


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "user", "score", "status", "helpful_count", "created_at")
    list_filter = ("status", "score")
    search_fields = ("product__name", "user__email", "title", "content")
    inlines = [ReviewImageInline]


@admin.register(ReviewHelpful)
class ReviewHelpfulAdmin(admin.ModelAdmin):
    list_display = ("id", "review", "user")
