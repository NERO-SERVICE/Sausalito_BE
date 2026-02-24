from __future__ import annotations

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.orders.models import Order, OrderItem
from apps.reviews.models import Review


class ReviewCreateRestrictionTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="review-user@test.local",
            password="pass1234",
            name="리뷰고객",
        )
        self.other_user = User.objects.create_user(
            email="other-user@test.local",
            password="pass1234",
            name="다른고객",
        )
        self.product = Product.objects.create(
            name="리뷰 작성 제한 테스트 상품",
            price=15000,
            original_price=17000,
            stock=50,
            is_active=True,
        )

    def _create_order_item(
        self,
        *,
        user: User,
        product: Product,
        shipping_status: str = Order.ShippingStatus.DELIVERED,
        payment_status: str = Order.PaymentStatus.APPROVED,
        product_order_status: str = Order.ProductOrderStatus.DELIVERED,
    ) -> OrderItem:
        delivered_at = timezone.now() if shipping_status == Order.ShippingStatus.DELIVERED else None
        order = Order.objects.create(
            user=user,
            status=Order.Status.PAID,
            payment_status=payment_status,
            shipping_status=shipping_status,
            product_order_status=product_order_status,
            subtotal_amount=product.price,
            shipping_fee=0,
            discount_amount=0,
            total_amount=product.price,
            recipient="홍길동",
            phone="01012345678",
            postal_code="04524",
            road_address="서울특별시 중구 세종대로 110",
            jibun_address="서울 중구 태평로1가 31",
            detail_address="201호",
            delivered_at=delivered_at,
        )
        return OrderItem.objects.create(
            order=order,
            product=product,
            product_id_snapshot=product.id,
            product_name_snapshot=product.name,
            option_name_snapshot="",
            unit_price=product.price,
            quantity=1,
            line_total=product.price,
        )

    def test_create_review_requires_delivered_order_item(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/v1/reviews",
            {
                "order_item_id": 999999,
                "product_id": self.product.id,
                "score": 5,
                "title": "리뷰",
                "content": "좋아요",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("주문번호-주문상품", str(response.data))
        self.assertEqual(Review.objects.count(), 0)

    def test_create_review_matches_delivered_order_item(self):
        matched_item = self._create_order_item(user=self.user, product=self.product)
        self.client.force_authenticate(self.user)

        response = self.client.post(
            "/api/v1/reviews",
            {
                "order_item_id": matched_item.id,
                "product_id": self.product.id,
                "score": 5,
                "title": "실구매 후기",
                "content": "배송완료 주문건으로 작성",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        review = Review.objects.get()
        self.assertEqual(review.user_id, self.user.id)
        self.assertEqual(review.product_id, self.product.id)
        self.assertEqual(review.order_item_id, matched_item.id)

    def test_create_review_matches_purchase_confirmed_order_item(self):
        matched_item = self._create_order_item(
            user=self.user,
            product=self.product,
            product_order_status=Order.ProductOrderStatus.PURCHASE_CONFIRMED,
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(
            "/api/v1/reviews",
            {
                "order_item_id": matched_item.id,
                "product_id": self.product.id,
                "score": 5,
                "title": "구매확정 후기",
                "content": "구매확정 상태에서 작성",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        review = Review.objects.get(id=response.data["data"]["id"])
        self.assertEqual(review.order_item_id, matched_item.id)

    def test_create_review_rejects_non_reviewable_product_order_status(self):
        shipping_item = self._create_order_item(
            user=self.user,
            product=self.product,
            shipping_status=Order.ShippingStatus.SHIPPED,
            product_order_status=Order.ProductOrderStatus.SHIPPING,
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(
            "/api/v1/reviews",
            {
                "order_item_id": shipping_item.id,
                "product_id": self.product.id,
                "score": 4,
                "title": "작성 시도",
                "content": "배송중 상태에서는 작성 불가",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("주문번호-주문상품", str(response.data))

    def test_same_order_item_cannot_be_reviewed_twice(self):
        order_item = self._create_order_item(user=self.user, product=self.product)
        self.client.force_authenticate(self.user)

        first = self.client.post(
            "/api/v1/reviews",
            {
                "order_item_id": order_item.id,
                "product_id": self.product.id,
                "score": 4,
                "title": "첫 리뷰",
                "content": "첫 작성",
            },
            format="json",
        )
        second = self.client.post(
            "/api/v1/reviews",
            {
                "order_item_id": order_item.id,
                "product_id": self.product.id,
                "score": 5,
                "title": "두번째 리뷰",
                "content": "중복 작성 시도",
            },
            format="json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        self.assertIn("주문번호-주문상품", str(second.data))
        self.assertEqual(Review.objects.count(), 1)

    def test_same_product_can_be_reviewed_once_per_purchase_order_item(self):
        first_item = self._create_order_item(user=self.user, product=self.product)
        second_item = self._create_order_item(user=self.user, product=self.product)
        self.client.force_authenticate(self.user)

        first = self.client.post(
            "/api/v1/reviews",
            {
                "order_item_id": first_item.id,
                "product_id": self.product.id,
                "score": 5,
                "title": "첫 구매 후기",
                "content": "2월 3일 주문건 후기",
            },
            format="json",
        )
        second = self.client.post(
            "/api/v1/reviews",
            {
                "order_item_id": second_item.id,
                "product_id": self.product.id,
                "score": 4,
                "title": "두번째 구매 후기",
                "content": "2월 7일 주문건 후기",
            },
            format="json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(Review.objects.count(), 2)
        self.assertEqual(
            set(Review.objects.values_list("order_item_id", flat=True)),
            {first_item.id, second_item.id},
        )

    def test_eligible_products_endpoint_returns_only_reviewable_rows(self):
        consumed = self._create_order_item(user=self.user, product=self.product)
        remaining = self._create_order_item(user=self.user, product=self.product)
        self._create_order_item(
            user=self.user,
            product=self.product,
            shipping_status=Order.ShippingStatus.PREPARING,
            payment_status=Order.PaymentStatus.APPROVED,
            product_order_status=Order.ProductOrderStatus.PAYMENT_COMPLETED,
        )
        self._create_order_item(user=self.other_user, product=self.product)
        Review.objects.create(
            product=self.product,
            user=self.user,
            order_item=consumed,
            score=5,
            title="이미 작성한 리뷰",
            content="중복 방지",
        )

        self.client.force_authenticate(self.user)
        response = self.client.get("/api/v1/reviews/eligible-products")
        self.assertEqual(response.status_code, 200)

        rows = response.data["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["order_item_id"]), remaining.id)
        self.assertEqual(rows[0]["order_no"], remaining.order.order_no)
        self.assertEqual(int(rows[0]["product_id"]), self.product.id)
        self.assertEqual(rows[0]["product_order_status"], Order.ProductOrderStatus.DELIVERED)
