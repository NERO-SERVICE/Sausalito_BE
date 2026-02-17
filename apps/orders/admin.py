from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product",
        "product_option",
        "product_id_snapshot",
        "product_name_snapshot",
        "option_name_snapshot",
        "unit_price",
        "quantity",
        "line_total",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_no",
        "user",
        "status",
        "payment_status",
        "shipping_status",
        "total_amount",
        "courier_name",
        "tracking_no",
        "created_at",
    )
    list_filter = ("status", "payment_status", "shipping_status")
    search_fields = ("order_no", "recipient", "phone", "user__email")
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "product_name_snapshot", "quantity", "line_total")
