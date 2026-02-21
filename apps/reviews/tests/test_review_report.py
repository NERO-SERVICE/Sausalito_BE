from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, IdempotencyRecord, User
from apps.catalog.models import Product
from apps.reviews.models import Review, ReviewReport


class ReviewReportFlowTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.author = User.objects.create_user(
            email="author@test.local",
            password="pass1234",
            name="작성자",
        )
        self.customer = User.objects.create_user(
            email="customer@test.local",
            password="pass1234",
            name="고객회원",
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
            name="리뷰 신고 테스트 상품",
            price=10000,
            original_price=12000,
            stock=30,
            is_active=True,
        )
        self.review = Review.objects.create(
            product=self.product,
            user=self.author,
            score=4,
            title="후기 제목",
            content="후기 본문",
        )

    def test_user_can_report_review_and_report_flag_is_exposed(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post(
            f"/api/v1/reviews/{self.review.id}/report",
            {"reason": "ABUSE", "detail": "부적절한 표현"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        self.assertTrue(
            ReviewReport.objects.filter(
                review_id=self.review.id,
                reporter_id=self.customer.id,
                status=ReviewReport.Status.PENDING,
            ).exists()
        )

        listed = self.client.get("/api/v1/reviews")
        self.assertEqual(listed.status_code, 200)
        rows = listed.data["data"]["results"]
        row = next(item for item in rows if int(item["id"]) == self.review.id)
        self.assertTrue(row["is_reported_by_me"])
        self.assertTrue(row["isReportedByMe"])

        self.client.force_authenticate(None)
        listed_as_anonymous = self.client.get("/api/v1/reviews")
        rows_anonymous = listed_as_anonymous.data["data"]["results"]
        row_anonymous = next(item for item in rows_anonymous if int(item["id"]) == self.review.id)
        self.assertFalse(row_anonymous["is_reported_by_me"])

    def test_admin_can_handle_report_with_idempotency(self):
        ReviewReport.objects.create(
            review=self.review,
            reporter=self.customer,
            reason=ReviewReport.Reason.ETC,
            detail="확인이 필요합니다.",
        )
        self.client.force_authenticate(self.admin)
        payload = {"action": "RESOLVE", "idempotency_key": "review-report-idem-1"}

        first = self.client.patch(
            f"/api/v1/admin/reviews/{self.review.id}/reports",
            payload,
            format="json",
        )
        second = self.client.patch(
            f"/api/v1/admin/reviews/{self.review.id}/reports",
            payload,
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        report = ReviewReport.objects.get(review_id=self.review.id, reporter_id=self.customer.id)
        self.assertEqual(report.status, ReviewReport.Status.RESOLVED)
        self.assertEqual(report.handled_by_id, self.admin.id)
        self.assertIsNotNone(report.handled_at)

        self.assertEqual(first.data["data"]["report_pending_count"], 0)
        self.assertEqual(first.data["data"]["report_status"], "HANDLED")

        self.assertEqual(
            IdempotencyRecord.objects.filter(key="review-report-idem-1", action="admin.reviews.reports.patch").count(),
            1,
        )
        self.assertEqual(
            AuditLog.objects.filter(action="REVIEW_REPORTS_HANDLED", target_type="Review", target_id=str(self.review.id)).count(),
            1,
        )
