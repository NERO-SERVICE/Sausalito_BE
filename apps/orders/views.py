from __future__ import annotations

from rest_framework import status
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.response import success_response

from .models import Order
from .serializers import OrderCreateSerializer, OrderSerializer


class OrderListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        queryset = Order.objects.filter(user=request.user).prefetch_related("items").order_by("-created_at")
        return success_response(OrderSerializer(queryset, many=True).data)

    def post(self, request, *args, **kwargs):
        serializer = OrderCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return success_response(
            OrderSerializer(order).data,
            message="주문이 생성되었습니다.",
            status_code=status.HTTP_201_CREATED,
        )


class OrderDetailAPIView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    lookup_field = "order_no"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return success_response(self.get_serializer(instance).data)
