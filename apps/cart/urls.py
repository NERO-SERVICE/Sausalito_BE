from django.urls import path

from .views import CartAPIView, CartItemCreateAPIView, CartItemUpdateDeleteAPIView

urlpatterns = [
    path("cart", CartAPIView.as_view(), name="cart"),
    path("cart/items", CartItemCreateAPIView.as_view(), name="cart-item-create"),
    path("cart/items/<int:item_id>", CartItemUpdateDeleteAPIView.as_view(), name="cart-item-update-delete"),
]
