from __future__ import annotations

from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Product
from apps.orders.models import Order


class OrderCreateBuyNowFlowTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="buyer@test.local",
            password="pass1234",
            name="구매자",
            phone="01011112222",
        )
        self.client.force_authenticate(user=self.user)
        self.product_buy_now = Product.objects.create(
            name="즉시주문 상품",
            one_line="즉시주문용",
            description="상세 설명",
            intake="하루 1회",
            target="성인",
            price=12000,
            original_price=15000,
            stock=20,
            is_active=True,
        )
        self.product_in_cart = Product.objects.create(
            name="장바구니 상품",
            one_line="장바구니용",
            description="상세 설명",
            intake="하루 1회",
            target="성인",
            price=8000,
            original_price=9000,
            stock=20,
            is_active=True,
        )

    def test_buy_now_creates_single_item_order_and_keeps_existing_cart(self):
        cart, _ = Cart.objects.get_or_create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product_in_cart, quantity=1)

        response = self.client.post(
            "/api/v1/orders",
            {
                "recipient": "구매자",
                "phone": "01011112222",
                "postal_code": "04524",
                "road_address": "서울특별시 중구 세종대로 110",
                "detail_address": "10층",
                "buy_now_product_id": self.product_buy_now.id,
                "buy_now_quantity": 2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.items.count(), 1)
        item = order.items.first()
        assert item is not None
        self.assertEqual(item.product_id_snapshot, self.product_buy_now.id)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.line_total, self.product_buy_now.price * 2)

        expected_subtotal = self.product_buy_now.price * 2
        expected_shipping_fee = settings.DEFAULT_SHIPPING_FEE if expected_subtotal < settings.FREE_SHIPPING_THRESHOLD else 0
        self.assertEqual(order.subtotal_amount, expected_subtotal)
        self.assertEqual(order.shipping_fee, expected_shipping_fee)
        self.assertEqual(order.total_amount, expected_subtotal + expected_shipping_fee)

        self.assertTrue(
            CartItem.objects.filter(cart__user=self.user, product=self.product_in_cart, quantity=1).exists()
        )

    def test_default_order_create_still_uses_cart_and_clears_it(self):
        cart, _ = Cart.objects.get_or_create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product_in_cart, quantity=2)

        response = self.client.post(
            "/api/v1/orders",
            {
                "recipient": "구매자",
                "phone": "01011112222",
                "postal_code": "04524",
                "road_address": "서울특별시 중구 세종대로 110",
                "detail_address": "10층",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.items.count(), 1)
        item = order.items.first()
        assert item is not None
        self.assertEqual(item.product_id_snapshot, self.product_in_cart.id)
        self.assertEqual(item.quantity, 2)

        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())

    def test_create_order_updates_default_address_when_requested(self):
        old_default = Address.objects.create(
            user=self.user,
            recipient="기존배송지",
            phone="01099998888",
            postal_code="99999",
            road_address="서울특별시 중구 옛주소 1",
            detail_address="1층",
            is_default=True,
        )

        response = self.client.post(
            "/api/v1/orders",
            {
                "recipient": "신규배송지",
                "phone": "01011112222",
                "postal_code": "04524",
                "road_address": "서울특별시 중구 세종대로 110",
                "detail_address": "10층",
                "buy_now_product_id": self.product_buy_now.id,
                "buy_now_quantity": 1,
                "save_as_default_address": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        old_default.refresh_from_db()
        self.assertFalse(old_default.is_default)

        new_default = Address.objects.filter(user=self.user, is_default=True).order_by("-updated_at").first()
        assert new_default is not None
        self.assertEqual(new_default.recipient, "신규배송지")
        self.assertEqual(new_default.road_address, "서울특별시 중구 세종대로 110")

    def test_create_order_keeps_existing_default_when_not_requested(self):
        old_default = Address.objects.create(
            user=self.user,
            recipient="기존배송지",
            phone="01099998888",
            postal_code="99999",
            road_address="서울특별시 중구 옛주소 1",
            detail_address="1층",
            is_default=True,
        )

        response = self.client.post(
            "/api/v1/orders",
            {
                "recipient": "주문용배송지",
                "phone": "01011112222",
                "postal_code": "04524",
                "road_address": "서울특별시 중구 세종대로 110",
                "detail_address": "10층",
                "buy_now_product_id": self.product_buy_now.id,
                "buy_now_quantity": 1,
                "save_as_default_address": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        old_default.refresh_from_db()
        self.assertTrue(old_default.is_default)
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)
