from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Address,
    DepositTransaction,
    OneToOneInquiry,
    PointTransaction,
    RecentViewedProduct,
    User,
    UserCoupon,
    WishlistItem,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    model = User
    list_display = ("id", "email", "username", "name", "is_staff", "is_active", "created_at")
    ordering = ("-created_at",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("username", "name", "phone", "kakao_sub")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at", "date_joined", "last_login")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "recipient", "phone", "is_default", "updated_at")
    search_fields = ("user__email", "recipient", "phone")


@admin.register(PointTransaction)
class PointTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "tx_type", "amount", "balance_after", "created_at")
    search_fields = ("user__email", "description")


@admin.register(DepositTransaction)
class DepositTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "tx_type", "amount", "balance_after", "created_at")
    search_fields = ("user__email", "description")


@admin.register(UserCoupon)
class UserCouponAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "code", "name", "discount_amount", "is_used", "expires_at", "created_at")
    search_fields = ("user__email", "code", "name")
    list_filter = ("is_used",)


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "product", "created_at")
    search_fields = ("user__email", "product__name")


@admin.register(RecentViewedProduct)
class RecentViewedProductAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "product", "viewed_at")
    search_fields = ("user__email", "product__name")


@admin.register(OneToOneInquiry)
class OneToOneInquiryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "category", "priority", "status", "assigned_admin", "created_at", "answered_at")
    search_fields = ("user__email", "title", "content")
    list_filter = ("status", "category", "priority")
