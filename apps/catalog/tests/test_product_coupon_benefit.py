from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserCoupon
from apps.catalog.models import Product


class ProductCouponBenefitTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="coupon-user@test.local",
            password="pass1234",
            name="쿠폰유저",
        )
        self.product = Product.objects.create(
            name="테스트 비타민",
            one_line="기초 건강 관리",
            description="상세 설명",
            intake="하루 1회",
            target="성인",
            price=30000,
            original_price=40000,
            stock=50,
            is_active=True,
        )

    def test_anonymous_product_detail_has_login_coupon_message(self):
        response = self.client.get(f"/api/v1/products/{self.product.id}")

        self.assertEqual(response.status_code, 200)
        benefit = response.data["data"]["coupon_benefit"]
        self.assertFalse(benefit["is_authenticated"])
        self.assertFalse(benefit["has_available_coupon"])
        self.assertEqual(benefit["available_coupon_count"], 0)
        self.assertIn("로그인", benefit["marketing_copy"])

    def test_authenticated_product_detail_returns_best_coupon_preview(self):
        now = timezone.now()
        UserCoupon.objects.create(
            user=self.user,
            name="즉시할인 3천원",
            code="DISC3000",
            discount_amount=3000,
            min_order_amount=20000,
            expires_at=now + timedelta(days=1),
            is_used=False,
        )
        UserCoupon.objects.create(
            user=self.user,
            name="즉시할인 5천원",
            code="DISC5000",
            discount_amount=5000,
            min_order_amount=25000,
            expires_at=now + timedelta(days=7),
            is_used=False,
        )
        UserCoupon.objects.create(
            user=self.user,
            name="조건부 7천원",
            code="DISC7000",
            discount_amount=7000,
            min_order_amount=50000,
            expires_at=now + timedelta(days=5),
            is_used=False,
        )
        UserCoupon.objects.create(
            user=self.user,
            name="만료 쿠폰",
            code="EXPIRED1",
            discount_amount=4000,
            min_order_amount=10000,
            expires_at=now - timedelta(days=1),
            is_used=False,
        )
        UserCoupon.objects.create(
            user=self.user,
            name="사용된 쿠폰",
            code="USED1",
            discount_amount=6000,
            min_order_amount=10000,
            is_used=True,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/api/v1/products/{self.product.id}")

        self.assertEqual(response.status_code, 200)
        benefit = response.data["data"]["coupon_benefit"]
        self.assertTrue(benefit["is_authenticated"])
        self.assertTrue(benefit["has_available_coupon"])
        self.assertTrue(benefit["has_eligible_coupon"])
        self.assertEqual(benefit["available_coupon_count"], 3)
        self.assertEqual(benefit["eligible_coupon_count"], 2)
        self.assertEqual(benefit["soon_expiring_coupon_count"], 1)

        best_coupon = benefit["best_coupon"]
        self.assertIsNotNone(best_coupon)
        self.assertEqual(best_coupon["discount_amount"], 5000)
        self.assertEqual(best_coupon["applied_discount_amount"], 5000)
        self.assertEqual(best_coupon["final_price"], 25000)
        self.assertAlmostEqual(float(best_coupon["extra_discount_rate"]), 16.67, places=2)
        self.assertAlmostEqual(float(best_coupon["final_discount_rate"]), 37.5, places=2)
        self.assertIn("5,000원", benefit["marketing_copy"])

    def test_authenticated_product_detail_with_only_ineligible_coupon(self):
        now = timezone.now()
        UserCoupon.objects.create(
            user=self.user,
            name="고액주문 7천원",
            code="HIGH7000",
            discount_amount=7000,
            min_order_amount=50000,
            expires_at=now + timedelta(days=3),
            is_used=False,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/api/v1/products/{self.product.id}")

        self.assertEqual(response.status_code, 200)
        benefit = response.data["data"]["coupon_benefit"]
        self.assertTrue(benefit["has_available_coupon"])
        self.assertFalse(benefit["has_eligible_coupon"])
        self.assertEqual(benefit["eligible_coupon_count"], 0)
        self.assertEqual(benefit["best_coupon"], None)
        self.assertIn("더 담으면", benefit["marketing_copy"])
        self.assertEqual(benefit["coupon_items"][0]["required_amount"], 20000)
