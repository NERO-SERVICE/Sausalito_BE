from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, User
from apps.catalog.models import Product
from apps.orders.models import Order, OrderItem
from apps.payments.models import BankTransferAccountConfig, BankTransferRequest, PaymentTransaction


class BankTransferPaymentFlowTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            email="bank-user@test.local",
            password="pass1234",
            name="입금고객",
            phone="01077779999",
        )
        self.admin = User.objects.create_user(
            email="ops-admin@test.local",
            password="pass1234",
            is_staff=True,
            admin_role=User.AdminRole.OPS,
            name="운영관리자",
        )

        self.product = Product.objects.create(
            name="입금테스트 상품",
            one_line="입금테스트",
            description="상세 설명",
            intake="하루 1회",
            target="성인",
            price=20000,
            original_price=23000,
            stock=15,
            is_active=True,
        )

        self.order = Order.objects.create(
            user=self.customer,
            status=Order.Status.PENDING,
            payment_status=Order.PaymentStatus.UNPAID,
            shipping_status=Order.ShippingStatus.READY,
            subtotal_amount=20000,
            shipping_fee=3000,
            discount_amount=0,
            total_amount=23000,
            recipient="입금고객",
            phone="01077779999",
            postal_code="04524",
            road_address="서울시 중구 을지로 100",
            jibun_address="서울 중구 을지로동",
            detail_address="101호",
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_option=None,
            product_id_snapshot=self.product.id,
            product_name_snapshot=self.product.name,
            option_name_snapshot="",
            unit_price=self.product.price,
            quantity=2,
            line_total=self.product.price * 2,
        )

    def test_public_bank_transfer_account_info_is_loaded_from_server_config(self):
        BankTransferAccountConfig.objects.create(
            singleton_key=1,
            bank_name="신한은행",
            bank_account_no="110-555-012345",
            account_holder="소살리토",
            guide_message="입금 후 관리자 확인이 완료되면 결제완료 처리됩니다.",
            verification_notice="입금자명은 주문자명과 동일하게 입력해 주세요.",
            cash_receipt_guide="결제완료 후 마이페이지 또는 고객센터에서 현금영수증 발급을 요청할 수 있습니다.",
            business_name="주식회사 네로",
            business_no="123-45-67890",
            ecommerce_no="2026-서울마포-0001",
            support_phone="1588-1234",
            support_email="cs@nero.ai.kr",
            support_hours="평일 10:00 - 18:00 / 점심 12:30 - 13:30",
        )

        response = self.client.get("/api/v1/payments/bank-transfer/account-info")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["bank_name"], "신한은행")
        self.assertEqual(data["bank_account_no"], "110-555-012345")
        self.assertEqual(data["account_holder"], "소살리토")
        self.assertEqual(data["guide_message"], "입금 후 관리자 확인이 완료되면 결제완료 처리됩니다.")
        self.assertEqual(data["verification_notice"], "입금자명은 주문자명과 동일하게 입력해 주세요.")
        self.assertEqual(
            data["cash_receipt_guide"],
            "결제완료 후 마이페이지 또는 고객센터에서 현금영수증 발급을 요청할 수 있습니다.",
        )
        self.assertEqual(data["business_info"]["name"], "주식회사 네로")
        self.assertEqual(data["business_info"]["business_no"], "123-45-67890")
        self.assertEqual(data["business_info"]["ecommerce_no"], "2026-서울마포-0001")
        self.assertEqual(data["support_info"]["phone"], "1588-1234")
        self.assertEqual(data["support_info"]["email"], "cs@nero.ai.kr")
        self.assertEqual(data["support_info"]["hours"], "평일 10:00 - 18:00 / 점심 12:30 - 13:30")

    def test_bank_transfer_request_uses_server_managed_account(self):
        BankTransferAccountConfig.objects.create(
            singleton_key=1,
            bank_name="신한은행",
            bank_account_no="110-555-012345",
            account_holder="소살리토",
        )

        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            "/api/v1/payments/bank-transfer/requests",
            {
                "order_no": self.order.order_no,
                "depositor_name": "홍길동",
                "depositor_phone": "01012341234",
                "transfer_note": "테스트 입금",
                "idempotency_key": "bank-transfer-config-1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        transfer = BankTransferRequest.objects.get(id=response.data["data"]["id"])
        self.assertEqual(transfer.bank_name, "신한은행")
        self.assertEqual(transfer.bank_account_no, "110-555-012345")
        self.assertEqual(transfer.account_holder, "소살리토")

    def test_admin_can_update_bank_transfer_account_config(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            "/api/v1/admin/bank-transfer/account-info",
            {
                "bank_name": "신한은행",
                "bank_account_no": "110-555-012345",
                "account_holder": "소살리토",
                "guide_message": "입금 후 관리자 확인이 완료되면 결제완료 처리됩니다.",
                "verification_notice": "입금자명은 주문자명과 동일하게 입력해 주세요.",
                "cash_receipt_guide": "결제완료 후 마이페이지 또는 고객센터에서 현금영수증 발급을 요청할 수 있습니다.",
                "business_name": "주식회사 네로",
                "business_no": "123-45-67890",
                "ecommerce_no": "2026-서울마포-0001",
                "support_phone": "1588-1234",
                "support_email": "cs@nero.ai.kr",
                "support_hours": "평일 10:00 - 18:00 / 점심 12:30 - 13:30",
                "idempotency_key": "bank-account-config-update-1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        row = BankTransferAccountConfig.objects.get(singleton_key=1)
        self.assertEqual(row.bank_name, "신한은행")
        self.assertEqual(row.bank_account_no, "110-555-012345")
        self.assertEqual(row.account_holder, "소살리토")
        self.assertEqual(row.business_name, "주식회사 네로")
        self.assertEqual(row.business_no, "123-45-67890")

    def test_customer_can_create_bank_transfer_request(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            "/api/v1/payments/bank-transfer/requests",
            {
                "order_no": self.order.order_no,
                "depositor_name": "홍길동",
                "depositor_phone": "01012341234",
                "transfer_note": "금일 오후 입금 예정",
                "idempotency_key": "bank-transfer-create-1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(BankTransferRequest.objects.count(), 1)

        transfer = BankTransferRequest.objects.first()
        assert transfer is not None
        self.assertEqual(transfer.order_id, self.order.id)
        self.assertEqual(transfer.status, BankTransferRequest.Status.REQUESTED)
        self.assertEqual(transfer.transfer_amount, self.order.total_amount)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.READY)

    def test_admin_approve_bank_transfer_updates_order_and_stock(self):
        transfer = BankTransferRequest.objects.create(
            order=self.order,
            user=self.customer,
            depositor_name="홍길동",
            depositor_phone="01012341234",
            transfer_amount=self.order.total_amount,
            bank_name="신한은행",
            bank_account_no="110-555-012345",
            account_holder="소살리토",
            transfer_note="입금완료",
            status=BankTransferRequest.Status.REQUESTED,
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"/api/v1/admin/bank-transfers/{transfer.id}",
            {
                "status": BankTransferRequest.Status.APPROVED,
                "admin_memo": "입금 내역 확인 완료",
                "idempotency_key": "bank-transfer-approve-1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, BankTransferRequest.Status.APPROVED)
        self.assertEqual(transfer.approved_by_id, self.admin.id)
        self.assertTrue(transfer.approved_at is not None)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.APPROVED)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 13)

        self.assertTrue(
            PaymentTransaction.objects.filter(
                order=self.order,
                provider=PaymentTransaction.Provider.BANK_TRANSFER,
                status=PaymentTransaction.Status.APPROVED,
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action="BANK_TRANSFER_APPROVED",
                target_type="BankTransferRequest",
                target_id=str(transfer.id),
                actor_admin=self.admin,
            ).exists()
        )

    def test_admin_bank_transfer_action_is_idempotent(self):
        transfer = BankTransferRequest.objects.create(
            order=self.order,
            user=self.customer,
            depositor_name="홍길동",
            transfer_amount=self.order.total_amount,
            bank_name="신한은행",
            bank_account_no="110-555-012345",
            account_holder="소살리토",
            status=BankTransferRequest.Status.REQUESTED,
        )
        self.client.force_authenticate(user=self.admin)

        payload = {
            "status": BankTransferRequest.Status.APPROVED,
            "idempotency_key": "bank-transfer-approve-duplicate-1",
        }
        first = self.client.patch(f"/api/v1/admin/bank-transfers/{transfer.id}", payload, format="json")
        second = self.client.patch(f"/api/v1/admin/bank-transfers/{transfer.id}", payload, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            AuditLog.objects.filter(
                action="BANK_TRANSFER_APPROVED",
                target_type="BankTransferRequest",
                target_id=str(transfer.id),
            ).count(),
            1,
        )

    def test_naverpay_endpoints_are_not_available(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            "/api/v1/payments/naverpay/ready",
            {
                "order_no": self.order.order_no,
                "return_url": "http://localhost:5173/pages/checkout.html",
                "cancel_url": "http://localhost:5173/pages/checkout.html",
                "fail_url": "http://localhost:5173/pages/checkout.html",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)
