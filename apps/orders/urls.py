from django.urls import path

from .views import OrderDetailAPIView, OrderListCreateAPIView

urlpatterns = [
    path("orders", OrderListCreateAPIView.as_view(), name="orders"),
    path("orders/<str:order_no>", OrderDetailAPIView.as_view(), name="order-detail"),
]
