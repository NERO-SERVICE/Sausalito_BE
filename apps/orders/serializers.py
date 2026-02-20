from __future__ import annotations

from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import Address
from apps.cart.models import Cart
from apps.catalog.models import Product, ProductOption

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
    save_as_default_address = serializers.BooleanField(required=False, default=True)
    buy_now_product_id = serializers.IntegerField(min_value=1, required=False)
    buy_now_option_id = serializers.IntegerField(min_value=1, required=False)
    buy_now_quantity = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        buy_now_product_id = attrs.get("buy_now_product_id")
        buy_now_option_id = attrs.get("buy_now_option_id")
        buy_now_quantity = attrs.get("buy_now_quantity")
        if buy_now_option_id and not buy_now_product_id:
            raise serializers.ValidationError({"buy_now_option_id": "buy_now_product_id와 함께 전달되어야 합니다."})
        if buy_now_quantity and not buy_now_product_id:
            raise serializers.ValidationError({"buy_now_quantity": "buy_now_product_id와 함께 전달되어야 합니다."})
        return attrs

    @staticmethod
    def _save_default_address(
        *,
        user,
        recipient: str,
        phone: str,
        postal_code: str,
        road_address: str,
        detail_address: str,
    ) -> None:
        matched = (
            Address.objects.filter(
                user=user,
                recipient=recipient,
                phone=phone,
                postal_code=postal_code,
                road_address=road_address,
                detail_address=detail_address,
            )
            .order_by("-updated_at", "-id")
            .first()
        )
        if matched:
            Address.objects.filter(user=user, is_default=True).exclude(id=matched.id).update(is_default=False)
            if not matched.is_default:
                matched.is_default = True
                matched.save(update_fields=["is_default", "updated_at"])
            return

        Address.objects.filter(user=user, is_default=True).update(is_default=False)
        Address.objects.create(
            user=user,
            recipient=recipient,
            phone=phone,
            postal_code=postal_code,
            road_address=road_address,
            detail_address=detail_address,
            is_default=True,
        )

    def create(self, validated_data):
        user = self.context["request"].user
        cart = None
        purchase_items: list[dict[str, object]] = []
        buy_now_product_id = validated_data.get("buy_now_product_id")
        save_as_default_address = bool(validated_data.get("save_as_default_address", True))

        if buy_now_product_id:
            product = Product.objects.filter(id=buy_now_product_id).first()
            if not product or not product.is_active:
                raise serializers.ValidationError({"buy_now_product_id": "구매할 수 없는 상품입니다."})

            option = None
            buy_now_option_id = validated_data.get("buy_now_option_id")
            if buy_now_option_id:
                option = ProductOption.objects.filter(id=buy_now_option_id, product=product, is_active=True).first()
                if option is None:
                    raise serializers.ValidationError({"buy_now_option_id": "구매할 수 없는 옵션입니다."})

            quantity = int(validated_data.get("buy_now_quantity") or 1)
            if product.stock < quantity:
                raise serializers.ValidationError(f"상품 재고가 부족합니다. ({product.name})")
            if option and option.stock < quantity:
                raise serializers.ValidationError(f"옵션 재고가 부족합니다. ({option.name})")

            unit_price = option.price if option else product.price
            purchase_items.append(
                {
                    "product": product,
                    "option": option,
                    "quantity": quantity,
                    "unit_price": unit_price,
                }
            )
        else:
            cart, _ = Cart.objects.get_or_create(user=user)
            cart_items = list(cart.items.select_related("product", "product_option").order_by("id"))
            if not cart_items:
                raise serializers.ValidationError("장바구니가 비어 있습니다.")

            for cart_item in cart_items:
                product = cart_item.product
                option = cart_item.product_option
                if not product or not product.is_active:
                    raise serializers.ValidationError(f"구매할 수 없는 상품이 포함되어 있습니다. ({cart_item.id})")
                if product.stock < cart_item.quantity:
                    raise serializers.ValidationError(f"상품 재고가 부족합니다. ({product.name})")
                if option and option.stock < cart_item.quantity:
                    raise serializers.ValidationError(f"옵션 재고가 부족합니다. ({option.name})")

                purchase_items.append(
                    {
                        "product": product,
                        "option": option,
                        "quantity": cart_item.quantity,
                        "unit_price": option.price if option else product.price,
                    }
                )

        subtotal = sum(int(item["unit_price"]) * int(item["quantity"]) for item in purchase_items)

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

            if save_as_default_address:
                self._save_default_address(
                    user=user,
                    recipient=validated_data["recipient"],
                    phone=validated_data["phone"],
                    postal_code=validated_data["postal_code"],
                    road_address=validated_data["road_address"],
                    detail_address=validated_data.get("detail_address", ""),
                )

            order_items = []
            for item in purchase_items:
                product = item["product"]
                option = item["option"]
                quantity = int(item["quantity"])
                unit_price = int(item["unit_price"])
                order_items.append(
                    OrderItem(
                        order=order,
                        product=product,
                        product_option=option,
                        product_id_snapshot=product.id,
                        product_name_snapshot=product.name,
                        option_name_snapshot=option.name if option else "",
                        unit_price=unit_price,
                        quantity=quantity,
                        line_total=unit_price * quantity,
                    )
                )
            OrderItem.objects.bulk_create(order_items)

            if cart is not None:
                cart.items.all().delete()

        return order
