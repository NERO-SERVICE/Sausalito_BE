from __future__ import annotations

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, OneToOneInquiry, SupportFaq, SupportNotice, User


class SupportBoardAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        SupportNotice.objects.all().delete()
        SupportFaq.objects.all().delete()
        OneToOneInquiry.objects.all().delete()
        self.user = User.objects.create_user(
            email="board-user@test.local",
            password="pass1234!",
            name="홍길동",
        )
        self.admin = User.objects.create_user(
            email="board-admin@test.local",
            password="pass1234!",
            is_staff=True,
            is_superuser=True,
            admin_role=User.AdminRole.SUPER_ADMIN,
            name="운영관리자",
        )

    def test_public_notice_list_is_paginated_and_excludes_inactive(self):
        for idx in range(12):
            SupportNotice.objects.create(
                title=f"공지 {idx}",
                content=f"내용 {idx}",
                is_active=True,
                is_pinned=(idx % 2 == 0),
                published_at=timezone.now(),
            )
        SupportNotice.objects.create(
            title="숨김 공지",
            content="비활성 공지",
            is_active=False,
            published_at=timezone.now(),
        )

        response = self.client.get("/api/v1/support/notices", {"page": 1, "page_size": 10})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get("success"))
        payload = response.data.get("data", {})
        rows = payload.get("results", [])
        self.assertEqual(len(rows), 10)
        self.assertEqual(payload.get("count"), 12)
        self.assertFalse(any(row.get("title") == "숨김 공지" for row in rows))

    def test_public_faq_list_filters_category_and_excludes_inactive(self):
        SupportFaq.objects.create(category="배송", question="배송기간", answer="1~2일", sort_order=0, is_active=True)
        SupportFaq.objects.create(category="배송", question="묶음배송", answer="가능", sort_order=1, is_active=True)
        SupportFaq.objects.create(category="결제", question="결제수단", answer="계좌이체", sort_order=0, is_active=True)
        SupportFaq.objects.create(category="배송", question="숨김질문", answer="숨김답변", sort_order=2, is_active=False)

        response = self.client.get("/api/v1/support/faqs", {"category": "배송"})
        self.assertEqual(response.status_code, 200)
        rows = response.data
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row.get("category") == "배송" for row in rows))
        self.assertFalse(any(row.get("question") == "숨김질문" for row in rows))

    def test_public_inquiry_list_is_paginated_and_masks_user_name(self):
        for idx in range(11):
            OneToOneInquiry.objects.create(
                user=self.user,
                title=f"문의 {idx}",
                content=f"문의 내용 {idx}",
                category=OneToOneInquiry.Category.ORDER,
            )

        response = self.client.get("/api/v1/support/inquiries", {"page": 1, "page_size": 10})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get("success"))
        payload = response.data.get("data", {})
        rows = payload.get("results", [])
        self.assertEqual(len(rows), 10)
        self.assertEqual(payload.get("count"), 11)
        self.assertTrue(all(row.get("user_name") != "홍길동" for row in rows))
        self.assertTrue(all("*" in row.get("user_name", "") for row in rows))

    def test_authenticated_user_can_create_inquiry_with_category(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            "/api/v1/users/me/inquiries",
            {
                "title": "배송 문의",
                "content": "언제 오나요?",
                "category": OneToOneInquiry.Category.DELIVERY,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data.get("success"))
        data = response.data.get("data", {})
        self.assertEqual(data.get("category"), OneToOneInquiry.Category.DELIVERY)
        self.assertEqual(data.get("status"), OneToOneInquiry.Status.OPEN)

    def test_admin_can_create_update_delete_support_notice_with_audit(self):
        self.client.force_authenticate(user=self.admin)

        created = self.client.post(
            "/api/v1/admin/support/notices",
            {
                "title": "신규 공지",
                "content": "공지 내용",
                "is_pinned": True,
                "is_active": True,
                "idempotency_key": "support-notice-create-1",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        notice_id = created.data.get("data", {}).get("id")
        self.assertTrue(notice_id)

        updated = self.client.patch(
            f"/api/v1/admin/support/notices/{notice_id}",
            {
                "title": "수정 공지",
                "is_active": False,
                "idempotency_key": "support-notice-update-1",
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data.get("data", {}).get("title"), "수정 공지")
        self.assertFalse(updated.data.get("data", {}).get("is_active"))

        deleted = self.client.delete(
            f"/api/v1/admin/support/notices/{notice_id}",
            HTTP_IDEMPOTENCY_KEY="support-notice-delete-1",
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(SupportNotice.objects.filter(id=notice_id).exists())

        actions = set(
            AuditLog.objects.filter(
                target_type="SupportNotice",
                target_id=str(notice_id),
            ).values_list("action", flat=True)
        )
        self.assertIn("SUPPORT_NOTICE_CREATED", actions)
        self.assertIn("SUPPORT_NOTICE_UPDATED", actions)
        self.assertIn("SUPPORT_NOTICE_DELETED", actions)

    def test_admin_can_create_update_delete_support_faq_with_audit(self):
        self.client.force_authenticate(user=self.admin)

        created = self.client.post(
            "/api/v1/admin/support/faqs",
            {
                "category": "배송",
                "question": "배송문의",
                "answer": "내일 도착",
                "sort_order": 1,
                "is_active": True,
                "idempotency_key": "support-faq-create-1",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        faq_id = created.data.get("data", {}).get("id")
        self.assertTrue(faq_id)

        updated = self.client.patch(
            f"/api/v1/admin/support/faqs/{faq_id}",
            {
                "answer": "모레 도착",
                "is_active": False,
                "idempotency_key": "support-faq-update-1",
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data.get("data", {}).get("answer"), "모레 도착")
        self.assertFalse(updated.data.get("data", {}).get("is_active"))

        deleted = self.client.delete(
            f"/api/v1/admin/support/faqs/{faq_id}",
            HTTP_IDEMPOTENCY_KEY="support-faq-delete-1",
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(SupportFaq.objects.filter(id=faq_id).exists())

        actions = set(
            AuditLog.objects.filter(
                target_type="SupportFaq",
                target_id=str(faq_id),
            ).values_list("action", flat=True)
        )
        self.assertIn("SUPPORT_FAQ_CREATED", actions)
        self.assertIn("SUPPORT_FAQ_UPDATED", actions)
        self.assertIn("SUPPORT_FAQ_DELETED", actions)

    def test_non_admin_cannot_access_admin_support_endpoints(self):
        self.client.force_authenticate(user=self.user)

        notice_response = self.client.get("/api/v1/admin/support/notices")
        faq_response = self.client.get("/api/v1/admin/support/faqs")

        self.assertEqual(notice_response.status_code, 403)
        self.assertEqual(faq_response.status_code, 403)
