from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.response import success_response

from .models import Cart, CartItem
from .serializers import (
    CartItemCreateSerializer,
    CartItemSerializer,
    CartItemUpdateSerializer,
    CartSerializer,
)


class CartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        serializer = CartSerializer(cart)
        return success_response(serializer.data)


class CartItemCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = CartItemCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return success_response(
            CartItemSerializer(item).data,
            message="장바구니에 추가되었습니다.",
            status_code=status.HTTP_201_CREATED,
        )


class CartItemUpdateDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, item_id: int, *args, **kwargs):
        item = CartItem.objects.filter(id=item_id, cart__user=request.user).first()
        if not item:
            return success_response(None, message="이미 삭제된 항목입니다.")

        serializer = CartItemUpdateSerializer(data=request.data, context={"item": item})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        return success_response(CartItemSerializer(item).data, message="수량이 변경되었습니다.")

    def delete(self, request, item_id: int, *args, **kwargs):
        item = CartItem.objects.filter(id=item_id, cart__user=request.user).first()
        if item:
            item.delete()
        return success_response(message="장바구니 항목이 삭제되었습니다.")
