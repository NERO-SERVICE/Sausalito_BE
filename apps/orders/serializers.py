from __future__ import annotations

from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from apps.cart.models import Cart

from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = (
            "id",
            "product_id_snapshot",
            "product_name_snapshot",
            "option_name_snapshot",
            "unit_price",
            "quantity",
            "line_total",
        )


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "order_no",
            "status",
            "payment_status",
            "shipping_status",
            "subtotal_amount",
            "shipping_fee",
            "discount_amount",
            "total_amount",
            "recipient",
            "phone",
            "postal_code",
            "road_address",
            "jibun_address",
            "detail_address",
            "courier_name",
            "tracking_no",
            "invoice_issued_at",
            "shipped_at",
            "delivered_at",
            "created_at",
            "items",
        )


class OrderCreateSerializer(serializers.Serializer):
    recipient = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=20)
    postal_code = serializers.CharField(max_length=10)
    road_address = serializers.CharField(max_length=255)
    jibun_address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    detail_address = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def create(self, validated_data):
        user = self.context["request"].user
        cart, _ = Cart.objects.get_or_create(user=user)
        cart_items = list(cart.items.select_related("product", "product_option").order_by("id"))
        if not cart_items:
            raise serializers.ValidationError("장바구니가 비어 있습니다.")

        subtotal = 0
        for cart_item in cart_items:
            product = cart_item.product
            option = cart_item.product_option
            if not product or not product.is_active:
                raise serializers.ValidationError(f"구매할 수 없는 상품이 포함되어 있습니다. ({cart_item.id})")
            if product.stock < cart_item.quantity:
                raise serializers.ValidationError(f"상품 재고가 부족합니다. ({product.name})")
            if option and option.stock < cart_item.quantity:
                raise serializers.ValidationError(f"옵션 재고가 부족합니다. ({option.name})")

            unit_price = option.price if option else product.price
            subtotal += unit_price * cart_item.quantity

        shipping_fee = settings.DEFAULT_SHIPPING_FEE if subtotal < settings.FREE_SHIPPING_THRESHOLD else 0
        discount_amount = 0
        total = subtotal + shipping_fee - discount_amount

        with transaction.atomic():
            order = Order.objects.create(
                user=user,
                subtotal_amount=subtotal,
                shipping_fee=shipping_fee,
                discount_amount=discount_amount,
                total_amount=total,
                payment_status=Order.PaymentStatus.UNPAID,
                recipient=validated_data["recipient"],
                phone=validated_data["phone"],
                postal_code=validated_data["postal_code"],
                road_address=validated_data["road_address"],
                jibun_address=validated_data.get("jibun_address", ""),
                detail_address=validated_data.get("detail_address", ""),
            )

            order_items = []
            for cart_item in cart_items:
                product = cart_item.product
                option = cart_item.product_option
                unit_price = option.price if option else product.price
                order_items.append(
                    OrderItem(
                        order=order,
                        product=product,
                        product_option=option,
                        product_id_snapshot=product.id,
                        product_name_snapshot=product.name,
                        option_name_snapshot=option.name if option else "",
                        unit_price=unit_price,
                        quantity=cart_item.quantity,
                        line_total=unit_price * cart_item.quantity,
                    )
                )
            OrderItem.objects.bulk_create(order_items)

            cart.items.all().delete()

        return order
