from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, IdempotencyRecord, User
from apps.orders.models import Order, ReturnRequest, SettlementRecord


class AdminSecurityTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.super_admin = User.objects.create_user(
            email="super-admin@test.local",
            password="pass1234",
            is_staff=True,
            is_superuser=True,
            admin_role=User.AdminRole.SUPER_ADMIN,
            name="슈퍼관리자",
        )
        self.ops_admin = User.objects.create_user(
            email="ops-admin@test.local",
            password="pass1234",
            is_staff=True,
            admin_role=User.AdminRole.OPS,
            name="운영관리자",
        )
        self.finance_admin = User.objects.create_user(
            email="finance-admin@test.local",
            password="pass1234",
            is_staff=True,
            admin_role=User.AdminRole.FINANCE,
            name="정산관리자",
        )
        self.customer = User.objects.create_user(
            email="customer@test.local",
            password="pass1234",
            name="고객테스트",
        )

        self.order = Order.objects.create(
            user=self.customer,
            status=Order.Status.PAID,
            payment_status=Order.PaymentStatus.APPROVED,
            shipping_status=Order.ShippingStatus.READY,
            subtotal_amount=10000,
            shipping_fee=3000,
            discount_amount=0,
            total_amount=13000,
            recipient="홍길동",
            phone="01012345678",
            postal_code="04524",
            road_address="서울특별시 중구 세종대로 110",
            jibun_address="서울 중구 태평로1가 31",
            detail_address="201호",
        )

        self.return_request = ReturnRequest.objects.create(
            order=self.order,
            user=self.customer,
            status=ReturnRequest.Status.REFUNDING,
            reason_title="불량",
            requested_amount=5000,
            approved_amount=5000,
        )

        self.settlement = SettlementRecord.objects.create(
            order=self.order,
            status=SettlementRecord.Status.PENDING,
            gross_amount=self.order.total_amount,
            discount_amount=self.order.discount_amount,
            shipping_fee=self.order.shipping_fee,
            pg_fee=400,
            platform_fee=1000,
            return_deduction=0,
            settlement_amount=11600,
        )

    def test_ops_cannot_update_settlement(self):
        self.client.force_authenticate(user=self.ops_admin)

        response = self.client.patch(
            f"/api/v1/admin/settlements/{self.settlement.id}",
            {"status": SettlementRecord.Status.SCHEDULED},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_finance_refund_is_idempotent(self):
        self.client.force_authenticate(user=self.finance_admin)

        payload = {
            "status": ReturnRequest.Status.REFUNDED,
            "approved_amount": 5000,
            "idempotency_key": "refund-idempotency-key-1",
        }
        first = self.client.patch(
            f"/api/v1/admin/returns/{self.return_request.id}",
            payload,
            format="json",
        )
        second = self.client.patch(
            f"/api/v1/admin/returns/{self.return_request.id}",
            payload,
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        self.return_request.refresh_from_db()
        self.assertEqual(self.return_request.status, ReturnRequest.Status.REFUNDED)
        self.assertTrue(self.return_request.refunded_at is not None)

        self.assertEqual(IdempotencyRecord.objects.filter(key="refund-idempotency-key-1").count(), 1)
        self.assertEqual(
            AuditLog.objects.filter(
                action="REFUND_EXECUTED",
                target_type="ReturnRequest",
                target_id=str(self.return_request.id),
            ).count(),
            1,
        )

    def test_order_list_masks_pii_for_ops(self):
        self.client.force_authenticate(user=self.ops_admin)

        response = self.client.get("/api/v1/admin/orders")
        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        self.assertTrue(rows)

        first = rows[0]
        self.assertNotEqual(first["phone"], self.order.phone)
        self.assertIn("****", first["phone"])
        self.assertNotEqual(first["road_address"], self.order.road_address)
        self.assertIn("payment_method", first)
        self.assertIn("latest_payment_provider", first)

    def test_order_list_full_pii_for_finance_and_logs_view(self):
        self.client.force_authenticate(user=self.finance_admin)

        response = self.client.get("/api/v1/admin/orders")
        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        self.assertTrue(rows)

        first = rows[0]
        self.assertEqual(first["phone"], self.order.phone)
        self.assertEqual(first["road_address"], self.order.road_address)
        self.assertTrue(
            AuditLog.objects.filter(
                action="PII_FULL_VIEW",
                target_type="Order",
                actor_admin=self.finance_admin,
            ).exists()
        )

    def test_shipping_transition_is_validated(self):
        self.client.force_authenticate(user=self.ops_admin)

        response = self.client.patch(
            f"/api/v1/admin/orders/{self.order.order_no}",
            {
                "shipping_status": Order.ShippingStatus.DELIVERED,
                "idempotency_key": "order-transition-invalid-1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.shipping_status, Order.ShippingStatus.READY)

    def test_super_admin_can_change_admin_role_with_audit_log(self):
        target_staff = User.objects.create_user(
            email="target-admin@test.local",
            password="pass1234",
            is_staff=True,
            admin_role=User.AdminRole.OPS,
            name="대상관리자",
        )
        self.client.force_authenticate(user=self.super_admin)

        response = self.client.patch(
            f"/api/v1/admin/users/manage/{target_staff.id}",
            {
                "admin_role": User.AdminRole.FINANCE,
                "idempotency_key": "admin-role-change-1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        target_staff.refresh_from_db()
        self.assertEqual(target_staff.admin_role, User.AdminRole.FINANCE)
        self.assertTrue(
            AuditLog.objects.filter(
                action="ADMIN_ROLE_CHANGED",
                target_type="User",
                target_id=str(target_staff.id),
                actor_admin=self.super_admin,
            ).exists()
        )
