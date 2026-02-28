from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import Product, ProductDetailMeta, ProductOption


class AdminProductPackageOptionsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="admin-product@test.local",
            password="pass1234",
            is_staff=True,
            is_superuser=True,
            admin_role=User.AdminRole.SUPER_ADMIN,
            name="상품관리자",
        )
        self.client.force_authenticate(user=self.admin)

    def test_admin_create_product_with_four_package_options(self):
        payload = {
            "name": "패키지 테스트 상품",
            "price": 30000,
            "original_price": 36000,
            "stock": 50,
            "package_options": [
                {
                    "duration_months": 1,
                    "name": "1개월분",
                    "benefit_label": "제품 상세선택",
                    "price": 30000,
                    "stock": 50,
                    "is_active": True,
                },
                {
                    "duration_months": 2,
                    "name": "2개월분 (1+1)",
                    "benefit_label": "1+1",
                    "price": 55200,
                    "stock": 40,
                    "is_active": True,
                },
                {
                    "duration_months": 3,
                    "name": "3개월분 (2+1)",
                    "benefit_label": "2+1",
                    "price": 77400,
                    "stock": 30,
                    "is_active": True,
                },
                {
                    "duration_months": 6,
                    "name": "6개월분 (4+2)",
                    "benefit_label": "4+2",
                    "price": 144000,
                    "stock": 20,
                    "is_active": True,
                },
            ],
        }

        response = self.client.post("/api/v1/admin/products/manage", payload, format="json")

        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        package_options = data["package_options"]
        self.assertEqual(len(package_options), 4)
        self.assertEqual([row["duration_months"] for row in package_options], [1, 2, 3, 6])

        product = Product.objects.get(id=data["id"])
        options = ProductOption.objects.filter(product=product, duration_months__isnull=False).order_by("duration_months")
        self.assertEqual(options.count(), 4)
        self.assertEqual([row.duration_months for row in options], [1, 2, 3, 6])
        self.assertEqual(options.get(duration_months=2).benefit_label, "1+1")

    def test_product_detail_meta_returns_package_options(self):
        product = Product.objects.create(
            name="상세 옵션 상품",
            one_line="옵션 확인",
            description="옵션 노출 테스트",
            intake="하루 1회",
            target="성인",
            price=24000,
            original_price=30000,
            stock=25,
            is_active=True,
        )
        ProductDetailMeta.objects.create(product=product, options_label="상품구성")
        ProductOption.objects.create(
            product=product,
            duration_months=1,
            benefit_label="제품 상세선택",
            name="1개월분",
            price=24000,
            stock=25,
            is_active=True,
        )
        ProductOption.objects.create(
            product=product,
            duration_months=2,
            benefit_label="1+1",
            name="2개월분 (1+1)",
            price=44160,
            stock=20,
            is_active=True,
        )
        ProductOption.objects.create(
            product=product,
            duration_months=3,
            benefit_label="2+1",
            name="3개월분 (2+1)",
            price=61920,
            stock=18,
            is_active=True,
        )
        ProductOption.objects.create(
            product=product,
            duration_months=6,
            benefit_label="4+2",
            name="6개월분 (4+2)",
            price=115200,
            stock=12,
            is_active=True,
        )

        response = self.client.get(f"/api/v1/products/{product.id}/detail-meta")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["options_label"], "상품구성")
        self.assertEqual([row["duration_months"] for row in data["options"]], [1, 2, 3, 6])

    def test_stock_only_update_syncs_derived_package_option_stock(self):
        create_response = self.client.post(
            "/api/v1/admin/products/manage",
            {
                "name": "재고 동기화 상품",
                "price": 29000,
                "original_price": 34000,
                "stock": 12,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        product_id = create_response.data["data"]["id"]

        patch_response = self.client.patch(
            f"/api/v1/admin/products/manage/{product_id}",
            {"stock": 37},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)

        stocks = list(
            ProductOption.objects.filter(product_id=product_id, duration_months__isnull=False)
            .order_by("duration_months")
            .values_list("stock", flat=True)
        )
        self.assertEqual(stocks, [37, 37, 37, 37])

    def test_stock_only_update_keeps_custom_package_option_stock(self):
        create_response = self.client.post(
            "/api/v1/admin/products/manage",
            {
                "name": "커스텀 재고 상품",
                "price": 30000,
                "original_price": 36000,
                "stock": 50,
                "package_options": [
                    {
                        "duration_months": 1,
                        "name": "1개월분",
                        "benefit_label": "제품 상세선택",
                        "price": 30000,
                        "stock": 50,
                        "is_active": True,
                    },
                    {
                        "duration_months": 2,
                        "name": "2개월분 (1+1)",
                        "benefit_label": "1+1",
                        "price": 55200,
                        "stock": 40,
                        "is_active": True,
                    },
                    {
                        "duration_months": 3,
                        "name": "3개월분 (2+1)",
                        "benefit_label": "2+1",
                        "price": 77400,
                        "stock": 30,
                        "is_active": True,
                    },
                    {
                        "duration_months": 6,
                        "name": "6개월분 (4+2)",
                        "benefit_label": "4+2",
                        "price": 144000,
                        "stock": 20,
                        "is_active": True,
                    },
                ],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        product_id = create_response.data["data"]["id"]

        patch_response = self.client.patch(
            f"/api/v1/admin/products/manage/{product_id}",
            {"stock": 99},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)

        stocks = list(
            ProductOption.objects.filter(product_id=product_id, duration_months__isnull=False)
            .order_by("duration_months")
            .values_list("stock", flat=True)
        )
        self.assertEqual(stocks, [50, 40, 30, 20])
