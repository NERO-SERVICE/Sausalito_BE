from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Address,
    AuditLog,
    DepositTransaction,
    IdempotencyRecord,
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
    list_display = ("id", "email", "username", "name", "is_staff", "admin_role", "is_active", "created_at")
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
                    "admin_role",
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


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "occurred_at", "actor_admin", "actor_role", "action", "target_type", "target_id", "result")
    search_fields = ("action", "target_type", "target_id", "actor_admin__email", "request_id", "idempotency_key")
    list_filter = ("result", "action", "actor_role")
    readonly_fields = (
        "occurred_at",
        "actor_admin",
        "actor_role",
        "action",
        "target_type",
        "target_id",
        "request_id",
        "idempotency_key",
        "ip",
        "user_agent",
        "before_json",
        "after_json",
        "metadata_json",
        "result",
        "error_code",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "key", "action", "actor_admin", "response_status_code", "target_type", "target_id")
    search_fields = ("key", "action", "actor_admin__email", "target_type", "target_id")
    readonly_fields = (
        "created_at",
        "updated_at",
        "key",
        "action",
        "actor_admin",
        "request_hash",
        "response_status_code",
        "response_body",
        "target_type",
        "target_id",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
