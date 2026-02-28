from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from apps.catalog.models import Product, ProductOption
from apps.common.media_utils import build_public_file_url

from .models import Cart, CartItem


class CartProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    price = serializers.IntegerField()
    image = serializers.CharField()


class CartOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    price = serializers.IntegerField()


class CartItemSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()
    option = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ("id", "product", "option", "quantity", "line_total")

    def get_product(self, obj: CartItem) -> dict:
        image = obj.product.images.filter(is_thumbnail=True).first() or obj.product.images.first()
        image_url = ""
        if image and image.image:
            image_url = build_public_file_url(image.image, request=self.context.get("request"))
        return {
            "id": obj.product.id,
            "name": obj.product.name,
            "price": obj.product.price,
            "image": image_url,
        }

    def get_option(self, obj: CartItem) -> dict | None:
        if not obj.product_option:
            return None
        return {
            "id": obj.product_option.id,
            "name": obj.product_option.name,
            "price": obj.product_option.price,
        }

    def get_line_total(self, obj: CartItem) -> int:
        unit_price = obj.product_option.price if obj.product_option else obj.product.price
        return unit_price * obj.quantity


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    shipping = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ("id", "items", "subtotal", "shipping", "total", "updated_at")

    def _subtotal(self, obj: Cart) -> int:
        subtotal = 0
        for item in obj.items.select_related("product", "product_option"):
            unit_price = item.product_option.price if item.product_option else item.product.price
            subtotal += unit_price * item.quantity
        return subtotal

    def get_subtotal(self, obj: Cart) -> int:
        return self._subtotal(obj)

    def get_shipping(self, obj: Cart) -> int:
        subtotal = self._subtotal(obj)
        if subtotal == 0:
            return 0
        return settings.DEFAULT_SHIPPING_FEE if subtotal < settings.FREE_SHIPPING_THRESHOLD else 0

    def get_total(self, obj: Cart) -> int:
        subtotal = self._subtotal(obj)
        shipping = settings.DEFAULT_SHIPPING_FEE if (subtotal > 0 and subtotal < settings.FREE_SHIPPING_THRESHOLD) else 0
        return subtotal + shipping


class CartItemCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    option_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, max_value=99, default=1)

    def validate(self, attrs):
        product = Product.objects.filter(id=attrs["product_id"], is_active=True).first()
        if not product:
            raise serializers.ValidationError("유효한 상품이 아닙니다.")
        attrs["product"] = product

        option_id = attrs.get("option_id")
        option = None
        if option_id is not None:
            option = ProductOption.objects.filter(id=option_id, product=product, is_active=True).first()
            if not option:
                raise serializers.ValidationError("유효한 옵션이 아닙니다.")
        attrs["option"] = option

        if option and option.stock < attrs["quantity"]:
            raise serializers.ValidationError("옵션 재고가 부족합니다.")
        if product.stock < attrs["quantity"]:
            raise serializers.ValidationError("상품 재고가 부족합니다.")

        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        cart, _ = Cart.objects.get_or_create(user=user)

        product = self.validated_data["product"]
        option = self.validated_data["option"]
        quantity = self.validated_data["quantity"]

        item = cart.items.filter(product=product, product_option=option).first()
        if item:
            item.quantity = min(99, item.quantity + quantity)
            item.save(update_fields=["quantity", "updated_at"])
            return item

        return CartItem.objects.create(cart=cart, product=product, product_option=option, quantity=quantity)


class CartItemUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=99)

    def validate(self, attrs):
        item: CartItem = self.context["item"]
        quantity = int(attrs["quantity"])
        product = item.product
        option = item.product_option

        if not product or not product.is_active:
            raise serializers.ValidationError("구매할 수 없는 상품입니다.")
        if option:
            if not option.is_active:
                raise serializers.ValidationError("구매할 수 없는 옵션입니다.")
            if option.stock < quantity:
                raise serializers.ValidationError("옵션 재고가 부족합니다.")
        if product.stock < quantity:
            raise serializers.ValidationError("상품 재고가 부족합니다.")
        return attrs

    def save(self, **kwargs):
        item: CartItem = self.context["item"]
        item.quantity = self.validated_data["quantity"]
        item.save(update_fields=["quantity", "updated_at"])
        return item
