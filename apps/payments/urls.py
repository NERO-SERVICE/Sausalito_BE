from django.urls import path

from .views import (
    AdminBankTransferActionAPIView,
    AdminBankTransferListAPIView,
    BankTransferAccountInfoAPIView,
    BankTransferRequestListCreateAPIView,
    NaverPayApproveAPIView,
    NaverPayCancelAPIView,
    NaverPayReadyAPIView,
    NaverPayWebhookAPIView,
)

urlpatterns = [
    path("payments/naverpay/ready", NaverPayReadyAPIView.as_view(), name="naverpay-ready"),
    path("payments/naverpay/approve", NaverPayApproveAPIView.as_view(), name="naverpay-approve"),
    path("payments/naverpay/webhook", NaverPayWebhookAPIView.as_view(), name="naverpay-webhook"),
    path("payments/naverpay/cancel", NaverPayCancelAPIView.as_view(), name="naverpay-cancel"),
    path("payments/bank-transfer/account-info", BankTransferAccountInfoAPIView.as_view(), name="bank-transfer-account-info"),
    path("payments/bank-transfer/requests", BankTransferRequestListCreateAPIView.as_view(), name="bank-transfer-requests"),
    path("admin/bank-transfers", AdminBankTransferListAPIView.as_view(), name="admin-bank-transfers"),
    path(
        "admin/bank-transfers/<uuid:transfer_id>",
        AdminBankTransferActionAPIView.as_view(),
        name="admin-bank-transfer-action",
    ),
]
