from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Product, ProductOption


class CartItemUpdateStockValidationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="cart-user@test.local",
            password="pass1234",
            name="장바구니유저",
        )
        self.client.force_authenticate(user=self.user)

    def test_cannot_update_quantity_beyond_product_stock(self):
        product = Product.objects.create(
            name="재고검증 상품",
            one_line="재고검증",
            description="상세 설명",
            intake="하루 1회",
            target="성인",
            price=12000,
            original_price=15000,
            stock=2,
            is_active=True,
        )
        cart, _ = Cart.objects.get_or_create(user=self.user)
        item = CartItem.objects.create(cart=cart, product=product, quantity=1)

        response = self.client.patch(
            f"/api/v1/cart/items/{item.id}",
            {"quantity": 3},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])

    def test_cannot_update_quantity_beyond_option_stock(self):
        product = Product.objects.create(
            name="옵션재고검증 상품",
            one_line="옵션재고검증",
            description="상세 설명",
            intake="하루 1회",
            target="성인",
            price=15000,
            original_price=18000,
            stock=10,
            is_active=True,
        )
        option = ProductOption.objects.create(
            product=product,
            duration_months=1,
            name="1개월분",
            price=15000,
            stock=1,
            is_active=True,
        )
        cart, _ = Cart.objects.get_or_create(user=self.user)
        item = CartItem.objects.create(cart=cart, product=product, product_option=option, quantity=1)

        response = self.client.patch(
            f"/api/v1/cart/items/{item.id}",
            {"quantity": 2},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
