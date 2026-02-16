from django.contrib import admin

from .models import PaymentTransaction, WebhookEvent


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "provider", "status", "payment_key", "approved_at", "created_at")
    list_filter = ("provider", "status")
    search_fields = ("order__order_no", "payment_key", "idempotency_key")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "event_type", "event_id", "is_processed", "processed_at")
    list_filter = ("provider", "event_type", "is_processed")
    search_fields = ("event_id",)
