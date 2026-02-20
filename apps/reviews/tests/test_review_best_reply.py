from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, IdempotencyRecord, User
from apps.catalog.models import Product
from apps.reviews.models import Review


class ReviewBestReplyTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            email="customer@test.local",
            password="pass1234",
            name="리뷰회원",
        )
        self.admin = User.objects.create_user(
            email="admin@test.local",
            password="pass1234",
            is_staff=True,
            is_superuser=True,
            admin_role=User.AdminRole.SUPER_ADMIN,
            name="관리자",
        )
        self.product = Product.objects.create(
            name="테스트 상품",
            price=12000,
            original_price=15000,
            stock=100,
            is_active=True,
        )

    def test_public_review_list_supports_best_only_filter(self):
        Review.objects.create(
            product=self.product,
            user=self.customer,
            score=5,
            title="베스트 리뷰",
            content="아주 좋아요",
            is_best=True,
            admin_reply="답변 감사합니다.",
            admin_replied_by=self.admin,
        )
        Review.objects.create(
            product=self.product,
            user=self.customer,
            score=4,
            title="일반 리뷰",
            content="좋아요",
            is_best=False,
        )

        response = self.client.get("/api/v1/reviews", {"best_only": "true"})
        self.assertEqual(response.status_code, 200)

        rows = response.data["data"]["results"]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["is_best"])
        self.assertEqual(rows[0]["admin_reply"], "답변 감사합니다.")
        self.assertEqual(rows[0]["answered_by"], "관리자")

    def test_admin_can_manage_best_flag_and_reply_with_idempotency(self):
        review = Review.objects.create(
            product=self.product,
            user=self.customer,
            score=3,
            title="문의 리뷰",
            content="배송이 빨랐어요",
        )
        self.client.force_authenticate(user=self.admin)

        payload = {
            "is_best": True,
            "answer": "구매해주셔서 감사합니다.",
            "idempotency_key": "review-manage-idem-1",
        }
        first = self.client.patch(
            f"/api/v1/admin/reviews/{review.id}/manage",
            payload,
            format="json",
        )
        second = self.client.patch(
            f"/api/v1/admin/reviews/{review.id}/manage",
            payload,
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        review.refresh_from_db()
        self.assertTrue(review.is_best)
        self.assertEqual(review.admin_reply, "구매해주셔서 감사합니다.")
        self.assertEqual(review.admin_replied_by_id, self.admin.id)
        self.assertIsNotNone(review.admin_replied_at)

        self.assertEqual(
            IdempotencyRecord.objects.filter(key="review-manage-idem-1", action="admin.reviews.manage.patch").count(),
            1,
        )
        self.assertEqual(
            AuditLog.objects.filter(action="REVIEW_MANAGED", target_type="Review", target_id=str(review.id)).count(),
            1,
        )

    def test_non_admin_cannot_manage_review(self):
        review = Review.objects.create(
            product=self.product,
            user=self.customer,
            score=5,
            title="권한 테스트",
            content="리뷰 내용",
        )
        self.client.force_authenticate(user=self.customer)

        response = self.client.patch(
            f"/api/v1/admin/reviews/{review.id}/manage",
            {"is_best": True},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
