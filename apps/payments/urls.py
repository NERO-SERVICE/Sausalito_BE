from django.urls import path

from .views import (
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
]
