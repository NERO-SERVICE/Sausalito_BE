from django.contrib import admin

from .models import BankTransferAccountConfig, BankTransferRequest, PaymentTransaction, WebhookEvent


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


@admin.register(BankTransferRequest)
class BankTransferRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "user",
        "depositor_name",
        "transfer_amount",
        "status",
        "approved_at",
        "rejected_at",
        "created_at",
    )
    list_filter = ("status", "bank_name")
    search_fields = ("order__order_no", "user__email", "depositor_name", "depositor_phone", "idempotency_key")


@admin.register(BankTransferAccountConfig)
class BankTransferAccountConfigAdmin(admin.ModelAdmin):
    list_display = (
        "bank_name",
        "bank_account_no",
        "account_holder",
        "business_name",
        "business_no",
        "support_phone",
        "support_email",
        "updated_at",
    )
    search_fields = ("bank_name", "bank_account_no", "account_holder", "business_name", "support_phone", "support_email")
