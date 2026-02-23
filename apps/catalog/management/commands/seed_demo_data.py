from __future__ import annotations

import base64
import re
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.catalog.models import (
    BrandPageSetting,
    BrandStorySection,
    Category,
    HomeBanner,
    Product,
    ProductBadge,
    ProductDetailImage,
    ProductDetailMeta,
    ProductImage,
    ProductOption,
)
from apps.accounts.models import (
    DepositTransaction,
    OneToOneInquiry,
    PointTransaction,
    RecentViewedProduct,
    UserCoupon,
    WishlistItem,
)
from apps.orders.models import Order, OrderItem, ReturnRequest, SettlementRecord
from apps.payments.models import PaymentTransaction
from apps.reviews.models import Review, ReviewImage

User = get_user_model()

PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+Z4QAAAAASUVORK5CYII="
)

PRODUCTS = [
    {
        "id": 1,
        "name": "데일리 멀티비타민 밸런스",
        "one_line": "하루 한 정으로 균형 잡힌 비타민 케어",
        "badges": ["베스트셀러", "할인"],
        "price": 28900,
        "original_price": 36000,
        "rating": 4.9,
        "reviews": 1224,
        "stock": 87,
        "popular_score": 98,
        "release_date": "2026-01-26",
        "description": "13종 비타민과 미네랄을 한 번에 담은 베스트 데일리 포뮬러",
        "intake": "1일 1회, 1정을 식후에 섭취",
        "target": "활력 저하/면역 관리가 필요한 성인",
        "ingredients": ["비타민B군", "비타민C", "아연", "셀렌"],
        "cautions": ["특정 성분 알레르기 체질은 원료 확인", "과다 섭취 금지"],
        "faq": [
            {"q": "공복에 먹어도 되나요?", "a": "속이 민감한 경우 식후 섭취를 권장합니다."},
            {"q": "다른 영양제와 함께 먹어도 되나요?", "a": "중복 성분 함량을 확인한 뒤 섭취하세요."},
        ],
    },
    {
        "id": 2,
        "name": "오메가3 퓨어 알티지",
        "one_line": "고순도 오메가3로 혈행과 눈 건강 관리",
        "badges": ["HOT", "할인"],
        "price": 35900,
        "original_price": 45000,
        "rating": 4.8,
        "reviews": 842,
        "stock": 26,
        "popular_score": 95,
        "release_date": "2026-02-03",
        "description": "고순도 rTG 오메가3로 혈행과 눈 건강까지 동시 케어",
        "intake": "1일 1회, 2캡슐을 충분한 물과 함께 섭취",
        "target": "장시간 모니터 사용/혈행 관리가 필요한 분",
        "ingredients": ["EPA", "DHA", "비타민E"],
        "cautions": ["혈액응고 억제제 복용 시 전문가 상담", "직사광선을 피해 보관"],
        "faq": [
            {"q": "비린내가 강한가요?", "a": "탈취 공정으로 비린맛을 최소화했습니다."},
            {"q": "언제 먹는 게 좋나요?", "a": "식사 중 또는 식후 섭취를 권장합니다."},
        ],
    },
    {
        "id": 3,
        "name": "프로바이오틱스 100억",
        "one_line": "코팅 유산균으로 편안한 장 컨디션",
        "badges": ["베스트셀러"],
        "price": 24900,
        "original_price": 32000,
        "rating": 4.7,
        "reviews": 1035,
        "stock": 138,
        "popular_score": 96,
        "release_date": "2025-12-20",
        "description": "장까지 살아가는 코팅 기술을 적용한 유산균 19종 배합",
        "intake": "1일 1회, 1포를 물 없이 섭취",
        "target": "장 컨디션/배변 리듬 관리가 필요한 분",
        "ingredients": ["프로바이오틱스 19종", "프리바이오틱스", "아연"],
        "cautions": ["개봉 후 즉시 섭취", "고온다습한 환경 보관 금지"],
        "faq": [
            {"q": "아이도 먹을 수 있나요?", "a": "연령별 권장량이 달라 제품 라벨을 확인하세요."},
            {"q": "항생제와 같이 먹어도 되나요?", "a": "간격을 두고 섭취하는 것을 권장합니다."},
        ],
    },
    {
        "id": 4,
        "name": "콜라겐 글로우 샷",
        "one_line": "저분자 콜라겐 이너뷰티 루틴",
        "badges": ["HOT"],
        "price": 39900,
        "original_price": 49000,
        "rating": 4.8,
        "reviews": 691,
        "stock": 54,
        "popular_score": 92,
        "release_date": "2026-01-11",
        "description": "저분자 피쉬콜라겐과 비오틴으로 완성한 이너뷰티 루틴",
        "intake": "1일 1회, 1병을 냉장 보관 후 섭취",
        "target": "피부 탄력/보습 관리가 필요한 분",
        "ingredients": ["피쉬콜라겐", "히알루론산", "비오틴"],
        "cautions": ["어류 알레르기 체질 주의", "개봉 후 냉장 보관"],
        "faq": [
            {"q": "언제 섭취하면 좋나요?", "a": "저녁 루틴 전후 섭취를 많이 선택합니다."},
            {"q": "맛이 어떤가요?", "a": "상큼한 베리 블렌드 맛입니다."},
        ],
    },
    {
        "id": 5,
        "name": "마그네슘 나이트 릴렉스",
        "one_line": "밤 루틴에 맞춘 릴렉스 포뮬러",
        "badges": ["할인"],
        "price": 21900,
        "original_price": 28000,
        "rating": 4.6,
        "reviews": 407,
        "stock": 61,
        "popular_score": 84,
        "release_date": "2025-10-10",
        "description": "긴장 완화 루틴에 맞춘 마그네슘+테아닌 배합",
        "intake": "1일 1회, 취침 1시간 전 1정을 섭취",
        "target": "저녁 긴장 완화/수면 루틴이 필요한 분",
        "ingredients": ["마그네슘", "L-테아닌", "비타민B6"],
        "cautions": ["권장량 초과 섭취 금지", "임산부는 전문가 상담"],
        "faq": [
            {"q": "아침에 먹어도 되나요?", "a": "수면 루틴 제품이라 저녁 섭취가 더 적합합니다."},
            {"q": "얼마나 먹어야 체감되나요?", "a": "개인차가 있어 2~4주 꾸준한 섭취를 권장합니다."},
        ],
    },
    {
        "id": 6,
        "name": "루테인 맥스 아이케어",
        "one_line": "디지털 피로를 위한 데일리 아이케어",
        "badges": ["할인", "HOT"],
        "price": 32900,
        "original_price": 41000,
        "rating": 4.7,
        "reviews": 556,
        "stock": 43,
        "popular_score": 89,
        "release_date": "2025-11-18",
        "description": "루테인+지아잔틴으로 눈 피로 관리를 돕는 아이케어 포뮬러",
        "intake": "1일 1회, 1캡슐을 식후 섭취",
        "target": "디지털 기기 사용량이 많은 직장인",
        "ingredients": ["루테인", "지아잔틴", "비타민A"],
        "cautions": ["흡연자는 전문가 상담 권장", "어린이 손이 닿지 않는 곳 보관"],
        "faq": [
            {"q": "렌즈 착용자도 먹어도 되나요?", "a": "렌즈 착용 여부와 무관하게 섭취 가능합니다."},
            {"q": "눈 건조에도 도움 되나요?", "a": "개인차가 있으며 수분 섭취를 함께 권장합니다."},
        ],
    },
]

PRODUCT_DETAIL_META = {
    1: {
        "coupon_text": "10% 추가 할인쿠폰",
        "shipping_fee": 3000,
        "free_shipping_threshold": 50000,
        "interest_free_text": "무이자 할부 혜택 제공",
        "purchase_types": ["1회구매", "정기배송 할인"],
        "subscription_benefit": "정기배송 선택 시 5% 추가 할인",
        "options_label": "상품구성",
        "options": [
            {"name": "30일팩 (3병) 샷잔 미포함", "price": 25900, "stock": 50},
            {"name": "60일팩 (6병) 샷잔 포함", "price": 48900, "stock": 20},
            {"name": "90일팩 (9병) 샷잔 포함", "price": 69900, "stock": 10},
            {"name": "스타터키트 (1병+샷잔)", "price": 12900, "stock": 30},
        ],
        "add_ons": [
            {"id": "gift-card", "name": "복 메시지 카드", "price": 1000},
            {"id": "shopping-bag", "name": "쇼핑백", "price": 2000},
            {"id": "shot-glass", "name": "굿모닝 샷잔", "price": 3000},
            {"id": "message-charm", "name": "메시지 참", "price": 1000},
        ],
        "today_ship_text": "오늘출발 상품 · 오후 2시 이전 결제 시 당일 발송",
        "inquiry_count": 561,
        "detail_image_count": 4,
    },
    2: {
        "coupon_text": "5% 추가 할인쿠폰",
        "shipping_fee": 3000,
        "free_shipping_threshold": 50000,
        "interest_free_text": "카드사별 무이자 할부 안내",
        "purchase_types": ["1회구매", "정기배송 할인"],
        "subscription_benefit": "정기배송 선택 시 3% 할인",
        "options_label": "상품구성",
        "options": [
            {"name": "1개월분 (60캡슐)", "price": 35900, "stock": 20},
            {"name": "2개월분 (120캡슐)", "price": 67900, "stock": 15},
            {"name": "3개월분 (180캡슐)", "price": 95900, "stock": 8},
        ],
        "add_ons": [
            {"id": "gift-card", "name": "복 메시지 카드", "price": 1000},
            {"id": "shopping-bag", "name": "쇼핑백", "price": 2000},
        ],
        "today_ship_text": "오늘출발 상품 · 오후 3시 이전 결제 시 당일 발송",
        "inquiry_count": 128,
        "detail_image_count": 4,
    },
}

HOME_BANNERS = [
    {
        "subtitle": "SAUSALITO WELLNESS",
        "title": "하루 루틴의 시작",
        "description": "매일 가볍게 시작하는 소살리토 데일리 밸런스 셀렉션",
        "cta_text": "자세히 보기",
        "link_url": "/pages/detail.html?id=1",
    },
    {
        "subtitle": "TRENDING ITEM",
        "title": "오메가3 집중 케어",
        "description": "바쁜 일상 속 혈행과 눈 건강을 동시에 챙겨보세요",
        "cta_text": "상품 보러가기",
        "link_url": "/pages/detail.html?id=2",
    },
    {
        "subtitle": "BEST REVIEWED",
        "title": "베스트 리뷰 제품",
        "description": "재구매가 많은 시그니처 제품들을 지금 만나보세요",
        "cta_text": "베스트 보기",
        "link_url": "#bestReview",
    },
    {
        "subtitle": "NEW ARRIVAL",
        "title": "새롭게 선보이는 루틴",
        "description": "신제품으로 나에게 맞는 웰니스 루틴을 업데이트하세요",
        "cta_text": "신제품 보러가기",
        "link_url": "/pages/detail.html?id=4",
    },
]

BRAND_PAGE_HERO = {
    "hero_eyebrow": "ABOUT SAUSALITO",
    "hero_title": "건강한 아침을 설계하는 브랜드",
    "hero_description": (
        "소살리토는 매일의 루틴을 더 쉽게, 더 투명하게 만들기 위해 시작되었습니다. "
        "좋은 성분과 명확한 기준으로 고객의 일상을 오래 함께합니다."
    ),
}

BRAND_STORY_SECTIONS = [
    {
        "eyebrow": "01 BRAND PHILOSOPHY",
        "title": "좋은 성분을 쉽게 고르는 기준",
        "description": "불필요한 성분은 덜고 핵심만 담아 누구나 이해하기 쉬운 선택 기준을 제공합니다.",
    },
    {
        "eyebrow": "02 PRODUCT STANDARD",
        "title": "원료부터 포장까지 투명한 관리",
        "description": "원료 수급, 제조 공정, 품질 검증 결과를 고객이 확인할 수 있도록 꾸준히 공개합니다.",
    },
    {
        "eyebrow": "03 DAILY ROUTINE",
        "title": "바쁜 일상에 맞춘 실천 가능한 루틴",
        "description": "아침/저녁 루틴에 맞는 조합으로 복잡함을 줄이고 꾸준함을 높이는 제품 경험을 설계합니다.",
    },
]

SEED_REVIEWS = [
    {"product_id": 1, "user": "김**", "score": 5, "text": "한 달째 먹고 있는데 오전 집중력이 좋아졌어요.", "date": "2026.02.10", "helpful": 31},
    {"product_id": 2, "user": "이**", "score": 5, "text": "비린맛이 거의 없어서 꾸준히 먹기 편해요.", "date": "2026.02.08", "helpful": 19},
    {"product_id": 3, "user": "박**", "score": 4, "text": "아침 공복에 먹고 장 컨디션이 안정적입니다.", "date": "2026.02.07", "helpful": 22},
    {"product_id": 4, "user": "정**", "score": 5, "text": "맛이 괜찮고 휴대하기도 좋아서 출근길에 챙겨요.", "date": "2026.02.04", "helpful": 15},
    {"product_id": 5, "user": "최**", "score": 4, "text": "잠들기 전에 먹으면 루틴이 안정적으로 잡히는 느낌이에요.", "date": "2026.02.03", "helpful": 9},
    {"product_id": 6, "user": "윤**", "score": 5, "text": "장시간 모니터 볼 때 눈 피로가 덜한 것 같아요.", "date": "2026.01.29", "helpful": 17},
]

REVIEW_USERS = ["김**", "이**", "박**", "정**", "최**", "윤**", "장**", "한**", "서**", "문**"]
REVIEW_TEXTS = [
    "재구매 의사 있어요. 루틴으로 먹기 편합니다.",
    "패키지가 깔끔해서 선물용으로도 괜찮아요.",
    "맛과 향이 부담 없어서 꾸준히 먹고 있어요.",
    "한 달 정도 복용했는데 만족도가 높습니다.",
    "배송이 빨랐고 포장 상태도 좋았습니다.",
    "가격대비 구성 좋아서 가족과 같이 먹어요.",
]

BADGE_MAP = {
    "HOT": ProductBadge.BadgeType.HOT,
    "베스트셀러": ProductBadge.BadgeType.BESTSELLER,
    "할인": ProductBadge.BadgeType.DISCOUNT,
}
PACKAGE_MONTHS = (1, 2, 3, 6)
PACKAGE_NAME_MAP = {
    1: "1개월분",
    2: "2개월분 (1+1)",
    3: "3개월분 (2+1)",
    6: "6개월분 (4+2)",
}
PACKAGE_BENEFIT_MAP = {
    1: "제품 상세선택",
    2: "1+1",
    3: "2+1",
    6: "4+2",
}
PACKAGE_DISCOUNT_RATE_MAP = {
    1: 0,
    2: 8,
    3: 14,
    6: 20,
}
PACKAGE_MONTH_PATTERN = re.compile(r"(\d+)\s*개월")


def make_placeholder_file(name: str) -> ContentFile:
    return ContentFile(PLACEHOLDER_PNG, name=name)


def parse_review_datetime(date_text: str) -> datetime:
    dt = datetime.strptime(date_text, "%Y.%m.%d")
    return timezone.make_aware(dt)


def extract_package_duration_months(name: str) -> int | None:
    match = PACKAGE_MONTH_PATTERN.search(str(name or ""))
    if not match:
        return None
    try:
        duration_months = int(match.group(1))
    except (TypeError, ValueError):
        return None
    return duration_months if duration_months in PACKAGE_MONTHS else None


def build_default_package_price(base_price: int, duration_months: int) -> int:
    safe_base_price = max(int(base_price or 0), 0)
    discount_rate = int(PACKAGE_DISCOUNT_RATE_MAP.get(duration_months, 0))
    return int(round((safe_base_price * duration_months) * (100 - discount_rate) / 100))


def build_default_package_option(duration_months: int, base_price: int, base_stock: int) -> dict:
    return {
        "duration_months": duration_months,
        "name": PACKAGE_NAME_MAP[duration_months],
        "benefit_label": PACKAGE_BENEFIT_MAP[duration_months],
        "price": build_default_package_price(base_price, duration_months),
        "stock": max(int(base_stock or 0), 0),
        "is_active": True,
    }


def normalize_seed_product_options(raw_options: list[dict] | None, *, base_price: int, base_stock: int) -> list[dict]:
    option_map: dict[int, dict] = {}
    for raw in raw_options or []:
        duration_months = raw.get("duration_months")
        if duration_months in {None, ""}:
            duration_months = extract_package_duration_months(raw.get("name", ""))
        try:
            duration_months = int(duration_months)
        except (TypeError, ValueError):
            continue
        if duration_months not in PACKAGE_MONTHS or duration_months in option_map:
            continue

        default_row = build_default_package_option(duration_months, base_price, base_stock)
        option_map[duration_months] = {
            "duration_months": duration_months,
            "name": str(raw.get("name", "")).strip() or default_row["name"],
            "benefit_label": str(raw.get("benefit_label", "")).strip() or default_row["benefit_label"],
            "price": max(int(raw.get("price", default_row["price"]) or 0), 0),
            "stock": max(int(raw.get("stock", base_stock) or 0), 0),
            "is_active": bool(raw.get("is_active", True)),
        }

    for duration_months in PACKAGE_MONTHS:
        if duration_months not in option_map:
            option_map[duration_months] = build_default_package_option(duration_months, base_price, base_stock)

    return [option_map[duration_months] for duration_months in PACKAGE_MONTHS]


def generate_bulk_reviews() -> list[dict]:
    rows: list[dict] = []
    base_date = timezone.make_aware(datetime(2026, 2, 16))

    for product_index, product in enumerate(PRODUCTS):
        for review_index in range(20):
            score = [5, 5, 4, 5, 4][review_index % 5]
            created_at = base_date - timedelta(days=review_index + product_index * 3)
            rows.append(
                {
                    "product_id": product["id"],
                    "user": REVIEW_USERS[(review_index + product_index) % len(REVIEW_USERS)],
                    "score": score,
                    "text": f"{REVIEW_TEXTS[(review_index + product['id']) % len(REVIEW_TEXTS)]} ({product['name']})",
                    "created_at": created_at,
                    "helpful": 3 + ((review_index * 7 + product["id"]) % 42),
                    "use_image": review_index % 4 == 0,
                }
            )

    return rows


class Command(BaseCommand):
    help = "Seed sausalito demo data (products, banners, reviews, demo users)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="기존 데이터를 삭제하고 다시 시드합니다.")
        parser.add_argument(
            "--with-placeholder-images",
            action="store_true",
            help="투명 placeholder 이미지(더미)를 함께 생성합니다.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        with_placeholder_images = options["with_placeholder_images"]

        if options["reset"]:
            self.stdout.write("기존 데이터를 정리합니다...")
            PaymentTransaction.objects.all().delete()
            SettlementRecord.objects.all().delete()
            ReturnRequest.objects.all().delete()
            Order.objects.all().delete()
            OneToOneInquiry.objects.all().delete()
            RecentViewedProduct.objects.all().delete()
            WishlistItem.objects.all().delete()
            UserCoupon.objects.all().delete()
            DepositTransaction.objects.all().delete()
            PointTransaction.objects.all().delete()
            ReviewImage.objects.all().delete()
            Review.objects.all().delete()
            ProductOption.objects.all().delete()
            ProductBadge.objects.all().delete()
            ProductImage.objects.all().delete()
            ProductDetailImage.objects.all().delete()
            ProductDetailMeta.objects.all().delete()
            BrandStorySection.objects.all().delete()
            BrandPageSetting.objects.all().delete()
            HomeBanner.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()

            for folder in ["products", "product-details", "banners", "reviews"]:
                shutil.rmtree(Path(settings.MEDIA_ROOT) / folder, ignore_errors=True)

        category, _ = Category.objects.get_or_create(name="웰니스", slug="wellness")

        demo_user, created = User.objects.get_or_create(
            email="demo@sausalito.com",
            defaults={"username": "demo", "name": "데모유저"},
        )
        demo_user.set_password("demo1234")
        demo_user.save(update_fields=["password"])

        admin_user, admin_created = User.objects.get_or_create(
            email="admin@sausalito.com",
            defaults={
                "username": "admin",
                "name": "관리자",
                "is_staff": True,
                "is_superuser": True,
                "admin_role": User.AdminRole.SUPER_ADMIN,
            },
        )
        admin_user.set_password("admin1234")
        if admin_created:
            admin_user.save(update_fields=["password"])
        elif not admin_user.is_staff or not admin_user.is_superuser or admin_user.admin_role != User.AdminRole.SUPER_ADMIN:
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.admin_role = User.AdminRole.SUPER_ADMIN
            admin_user.save(update_fields=["password", "is_staff", "is_superuser", "admin_role"])
        else:
            admin_user.save(update_fields=["password"])

        role_staff_defaults = [
            ("ops@sausalito.com", "운영관리자", User.AdminRole.OPS),
            ("cs@sausalito.com", "CS관리자", User.AdminRole.CS),
            ("finance@sausalito.com", "정산관리자", User.AdminRole.FINANCE),
            ("warehouse@sausalito.com", "물류관리자", User.AdminRole.WAREHOUSE),
            ("marketing@sausalito.com", "마케팅관리자", User.AdminRole.MARKETING),
            ("readonly@sausalito.com", "읽기전용관리자", User.AdminRole.READ_ONLY),
        ]
        for email, name, role in role_staff_defaults:
            staff_user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email.split("@")[0],
                    "name": name,
                    "is_staff": True,
                    "is_superuser": False,
                    "admin_role": role,
                },
            )
            staff_user.name = name
            staff_user.is_staff = True
            staff_user.is_superuser = False
            staff_user.admin_role = role
            staff_user.set_password("admin1234")
            staff_user.save(update_fields=["name", "is_staff", "is_superuser", "admin_role", "password"])

        product_map: dict[int, Product] = {}
        for row in PRODUCTS:
            product, _ = Product.objects.update_or_create(
                id=row["id"],
                defaults={
                    "category": category,
                    "name": row["name"],
                    "one_line": row["one_line"],
                    "description": row["description"],
                    "intake": row["intake"],
                    "target": row["target"],
                    "ingredients": row["ingredients"],
                    "cautions": row["cautions"],
                    "faq": row["faq"],
                    "price": row["price"],
                    "original_price": row["original_price"],
                    "stock": row["stock"],
                    "popular_score": row["popular_score"],
                    "release_date": row["release_date"],
                    "rating_avg": row["rating"],
                    "review_count": row["reviews"],
                    "is_active": True,
                },
            )
            product_map[product.id] = product

            product.images.all().delete()
            if with_placeholder_images:
                ProductImage.objects.create(
                    product=product,
                    image=make_placeholder_file(f"product_{product.id}_thumb.png"),
                    sort_order=0,
                    is_thumbnail=True,
                )

            product.badges.all().delete()
            for badge_text in row["badges"]:
                badge_type = BADGE_MAP.get(badge_text)
                if badge_type:
                    ProductBadge.objects.create(product=product, badge_type=badge_type)

            product.options.all().delete()
            detail_meta_input = PRODUCT_DETAIL_META.get(product.id)
            normalized_options = normalize_seed_product_options(
                detail_meta_input.get("options", []) if detail_meta_input else None,
                base_price=int(product.price or 0),
                base_stock=int(product.stock or 0),
            )
            for option in normalized_options:
                ProductOption.objects.create(
                    product=product,
                    duration_months=option["duration_months"],
                    benefit_label=option["benefit_label"],
                    name=option["name"],
                    price=option["price"],
                    stock=option.get("stock", product.stock),
                    is_active=bool(option.get("is_active", True)),
                )

            meta_defaults = {
                "coupon_text": "신규회원 쿠폰 적용 가능",
                "shipping_fee": 3000,
                "free_shipping_threshold": 50000,
                "interest_free_text": "카드 무이자 할부 안내",
                "purchase_types": ["1회구매", "정기배송 할인"],
                "subscription_benefit": "정기배송 선택 시 3% 할인",
                "options_label": "상품구성",
                "add_ons": [{"id": "gift-card", "name": "메시지 카드", "price": 1000}],
                "today_ship_text": "오늘출발 상품 · 마감 시간 전 주문 시 당일 발송",
                "inquiry_count": 24,
            }
            meta_defaults.update({k: v for k, v in (detail_meta_input or {}).items() if k not in {"options", "detail_image_count"}})
            detail_meta, _ = ProductDetailMeta.objects.update_or_create(product=product, defaults=meta_defaults)

            detail_meta.images.all().delete()
            detail_image_count = int((detail_meta_input or {}).get("detail_image_count", 0))
            if with_placeholder_images:
                for idx in range(detail_image_count):
                    ProductDetailImage.objects.create(
                        detail_meta=detail_meta,
                        image=make_placeholder_file(f"product_{product.id}_detail_{idx + 1}.png"),
                        sort_order=idx,
                    )

        HomeBanner.objects.all().delete()
        for idx, banner in enumerate(HOME_BANNERS):
            HomeBanner.objects.create(
                sort_order=idx,
                is_active=True,
                subtitle=banner["subtitle"],
                title=banner["title"],
                description=banner["description"],
                cta_text=banner["cta_text"],
                link_url=banner["link_url"],
                image=make_placeholder_file(f"banner_{idx + 1}.png") if with_placeholder_images else None,
            )

        BrandPageSetting.objects.update_or_create(
            id=1,
            defaults={
                "hero_eyebrow": BRAND_PAGE_HERO["hero_eyebrow"],
                "hero_title": BRAND_PAGE_HERO["hero_title"],
                "hero_description": BRAND_PAGE_HERO["hero_description"],
            },
        )

        BrandStorySection.objects.all().delete()
        for idx, section in enumerate(BRAND_STORY_SECTIONS):
            BrandStorySection.objects.create(
                eyebrow=section["eyebrow"],
                title=section["title"],
                description=section["description"],
                image_alt=f"브랜드 스토리 이미지 {idx + 1}",
                sort_order=idx,
                is_active=True,
                image=make_placeholder_file(f"brand_story_{idx + 1}.png") if with_placeholder_images else None,
            )

        Review.objects.all().delete()

        user_cache = {"demo@sausalito.com": demo_user}

        def get_review_user(masked_name: str):
            email = f"reviewer_{masked_name[0]}{ord(masked_name[0])}@sausalito.local"
            user = user_cache.get(email)
            if user:
                return user
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": f"reviewer_{uuid.uuid4().hex[:8]}",
                    "name": masked_name,
                },
            )
            if not user.has_usable_password():
                user.set_password(uuid.uuid4().hex)
                user.save(update_fields=["password"])
            user_cache[email] = user
            return user

        review_rows = []
        for base in SEED_REVIEWS:
            review_rows.append(
                {
                    "product_id": base["product_id"],
                    "user": base["user"],
                    "score": base["score"],
                    "text": base["text"],
                    "created_at": parse_review_datetime(base["date"]),
                    "helpful": base["helpful"],
                    "use_image": False,
                }
            )
        review_rows.extend(generate_bulk_reviews())

        image_counter = 1
        for row in review_rows:
            product = product_map[row["product_id"]]
            user = get_review_user(row["user"])
            review = Review.objects.create(
                product=product,
                user=user,
                score=row["score"],
                title="만족합니다",
                content=row["text"],
                helpful_count=row["helpful"],
                status=Review.Status.VISIBLE,
                created_at=row["created_at"],
                updated_at=row["created_at"],
            )

            if with_placeholder_images and row["use_image"]:
                ReviewImage.objects.create(
                    review=review,
                    image=make_placeholder_file(f"review_{image_counter}.png"),
                    sort_order=0,
                )
                image_counter += 1

        for product in product_map.values():
            summary = product.reviews.filter(status=Review.Status.VISIBLE).aggregate(avg=Avg("score"), cnt=Count("id"))
            product.rating_avg = summary["avg"] or 0
            product.review_count = summary["cnt"] or 0
            product.save(update_fields=["rating_avg", "review_count", "updated_at"])

        demo_order_rows = [
            {
                "order_no": "SAUDEMO20260217001",
                "product_id": 1,
                "quantity": 2,
                "status": Order.Status.PAID,
                "payment_status": Order.PaymentStatus.APPROVED,
                "shipping_status": Order.ShippingStatus.READY,
                "courier_name": "",
                "tracking_no": "",
                "invoice_issued_at": None,
                "shipped_at": None,
                "delivered_at": None,
            },
            {
                "order_no": "SAUDEMO20260217002",
                "product_id": 2,
                "quantity": 1,
                "status": Order.Status.PAID,
                "payment_status": Order.PaymentStatus.APPROVED,
                "shipping_status": Order.ShippingStatus.SHIPPED,
                "courier_name": "CJ대한통운",
                "tracking_no": "629500001234",
                "invoice_issued_at": timezone.now() - timedelta(days=1, hours=4),
                "shipped_at": timezone.now() - timedelta(days=1, hours=3),
                "delivered_at": None,
            },
            {
                "order_no": "SAUDEMO20260217003",
                "product_id": 4,
                "quantity": 1,
                "status": Order.Status.PAID,
                "payment_status": Order.PaymentStatus.APPROVED,
                "shipping_status": Order.ShippingStatus.DELIVERED,
                "courier_name": "한진택배",
                "tracking_no": "812345678901",
                "invoice_issued_at": timezone.now() - timedelta(days=4),
                "shipped_at": timezone.now() - timedelta(days=3, hours=20),
                "delivered_at": timezone.now() - timedelta(days=2, hours=6),
            },
        ]

        order_map = {}
        for row in demo_order_rows:
            product = product_map.get(row["product_id"])
            if not product:
                continue

            subtotal = product.price * row["quantity"]
            shipping_fee = settings.DEFAULT_SHIPPING_FEE if subtotal < settings.FREE_SHIPPING_THRESHOLD else 0
            total = subtotal + shipping_fee

            order, _ = Order.objects.update_or_create(
                order_no=row["order_no"],
                defaults={
                    "user": demo_user,
                    "status": row["status"],
                    "payment_status": row["payment_status"],
                    "shipping_status": row["shipping_status"],
                    "subtotal_amount": subtotal,
                    "shipping_fee": shipping_fee,
                    "discount_amount": 0,
                    "total_amount": total,
                    "recipient": "데모유저",
                    "phone": "010-1111-2222",
                    "postal_code": "04524",
                    "road_address": "서울특별시 중구 세종대로 110",
                    "detail_address": "201호",
                    "courier_name": row["courier_name"],
                    "tracking_no": row["tracking_no"],
                    "invoice_issued_at": row["invoice_issued_at"],
                    "shipped_at": row["shipped_at"],
                    "delivered_at": row["delivered_at"],
                },
            )

            OrderItem.objects.filter(order=order).delete()
            OrderItem.objects.create(
                order=order,
                product=product,
                product_option=None,
                product_id_snapshot=product.id,
                product_name_snapshot=product.name,
                option_name_snapshot="",
                unit_price=product.price,
                quantity=row["quantity"],
                line_total=product.price * row["quantity"],
            )

            PaymentTransaction.objects.filter(order=order).delete()
            PaymentTransaction.objects.create(
                order=order,
                provider=PaymentTransaction.Provider.BANK_TRANSFER,
                status=PaymentTransaction.Status.APPROVED,
                payment_key=f"SEED-{order.order_no}",
                approved_at=timezone.now() - timedelta(days=1),
                raw_request_json={"seed": True},
                raw_response_json={"seed": True},
            )
            order_map[order.order_no] = order

        for order in order_map.values():
            pg_fee = int(round(order.total_amount * 0.033))
            platform_fee = int(round(order.total_amount * 0.08))
            SettlementRecord.objects.update_or_create(
                order=order,
                defaults={
                    "status": SettlementRecord.Status.PENDING,
                    "gross_amount": order.total_amount,
                    "discount_amount": order.discount_amount,
                    "shipping_fee": order.shipping_fee,
                    "pg_fee": pg_fee,
                    "platform_fee": platform_fee,
                    "return_deduction": 0,
                    "settlement_amount": order.total_amount - pg_fee - platform_fee,
                    "expected_payout_date": timezone.localdate(order.created_at + timedelta(days=3)),
                },
            )

        order_for_open_return = order_map.get("SAUDEMO20260217002")
        if order_for_open_return:
            ReturnRequest.objects.update_or_create(
                order=order_for_open_return,
                reason_title="배송 지연으로 인한 반품 요청",
                defaults={
                    "user": demo_user,
                    "status": ReturnRequest.Status.REQUESTED,
                    "reason_detail": "출고 예정일을 넘겨 빠른 환불을 요청합니다.",
                    "requested_amount": order_for_open_return.total_amount,
                    "approved_amount": 0,
                },
            )
            SettlementRecord.objects.filter(order=order_for_open_return).update(status=SettlementRecord.Status.HOLD)

        order_for_refund = order_map.get("SAUDEMO20260217003")
        if order_for_refund:
            refund_amount = min(12000, int(order_for_refund.total_amount))
            ReturnRequest.objects.update_or_create(
                order=order_for_refund,
                reason_title="일부 상품 파손으로 부분 환불",
                defaults={
                    "user": demo_user,
                    "status": ReturnRequest.Status.REFUNDED,
                    "reason_detail": "배송 중 파손이 확인되어 부분 환불 처리되었습니다.",
                    "requested_amount": refund_amount,
                    "approved_amount": refund_amount,
                    "approved_at": timezone.now() - timedelta(days=2),
                    "refunded_at": timezone.now() - timedelta(days=1, hours=8),
                    "closed_at": timezone.now() - timedelta(days=1, hours=8),
                    "admin_note": "고객 동의 하에 부분 환불 완료",
                },
            )
            settlement = SettlementRecord.objects.filter(order=order_for_refund).first()
            if settlement:
                settlement.return_deduction = refund_amount
                settlement.settlement_amount = settlement.gross_amount - settlement.pg_fee - settlement.platform_fee - refund_amount
                settlement.status = SettlementRecord.Status.SCHEDULED
                settlement.save(update_fields=["return_deduction", "settlement_amount", "status", "updated_at"])

        order_for_paid_settlement = order_map.get("SAUDEMO20260217001")
        if order_for_paid_settlement:
            settlement = SettlementRecord.objects.filter(order=order_for_paid_settlement).first()
            if settlement:
                settlement.status = SettlementRecord.Status.PAID
                settlement.paid_at = timezone.now() - timedelta(hours=10)
                settlement.save(update_fields=["status", "paid_at", "updated_at"])

        point_samples = [
            ("EARN", 3000, "신규 가입 적립금"),
            ("EARN", 1200, "리뷰 작성 적립"),
            ("USE", -800, "주문 시 적립금 사용"),
        ]
        point_balance = 0
        for tx_type, amount, desc in point_samples:
            point_balance += amount
            PointTransaction.objects.create(
                user=demo_user,
                tx_type=tx_type,
                amount=amount,
                balance_after=point_balance,
                description=desc,
            )

        deposit_samples = [
            ("CHARGE", 20000, "예치금 충전"),
            ("USE", -5000, "주문 결제 사용"),
            ("REFUND", 2000, "부분 환불"),
        ]
        deposit_balance = 0
        for tx_type, amount, desc in deposit_samples:
            deposit_balance += amount
            DepositTransaction.objects.create(
                user=demo_user,
                tx_type=tx_type,
                amount=amount,
                balance_after=deposit_balance,
                description=desc,
            )

        UserCoupon.objects.update_or_create(
            user=demo_user,
            code="WELCOME10",
            defaults={
                "name": "신규회원 10% 쿠폰",
                "discount_amount": 3000,
                "min_order_amount": 20000,
                "is_used": False,
                "used_at": None,
            },
        )
        UserCoupon.objects.update_or_create(
            user=demo_user,
            code="RUNNER5000",
            defaults={
                "name": "러너 특가 5,000원 쿠폰",
                "discount_amount": 5000,
                "min_order_amount": 50000,
                "is_used": False,
                "used_at": None,
            },
        )

        for product_id in [1, 2, 4]:
            product = product_map.get(product_id)
            if product:
                WishlistItem.objects.get_or_create(user=demo_user, product=product)

        now = timezone.now()
        for offset, product_id in enumerate([3, 1, 2, 5]):
            product = product_map.get(product_id)
            if not product:
                continue
            row, _ = RecentViewedProduct.objects.update_or_create(
                user=demo_user,
                product=product,
            )
            row.viewed_at = now - timedelta(hours=offset * 3)
            row.save(update_fields=["viewed_at"])

        OneToOneInquiry.objects.update_or_create(
            user=demo_user,
            title="배송 상태가 궁금합니다.",
            defaults={
                "content": "주문한 상품의 현재 배송 단계를 확인하고 싶습니다.",
                "category": OneToOneInquiry.Category.DELIVERY,
                "priority": OneToOneInquiry.Priority.HIGH,
                "status": OneToOneInquiry.Status.OPEN,
                "assigned_admin": admin_user,
                "sla_due_at": timezone.now() + timedelta(hours=4),
            },
        )
        OneToOneInquiry.objects.update_or_create(
            user=demo_user,
            title="부분 환불 처리 일정 문의",
            defaults={
                "content": "부분 환불 건이 카드사에 반영되는 예상 일정을 알고 싶습니다.",
                "category": OneToOneInquiry.Category.RETURN_REFUND,
                "priority": OneToOneInquiry.Priority.NORMAL,
                "status": OneToOneInquiry.Status.ANSWERED,
                "assigned_admin": admin_user,
                "answer": "카드사 정책에 따라 영업일 기준 3~5일 내 반영됩니다.",
                "first_response_at": timezone.now() - timedelta(days=1),
                "answered_at": timezone.now() - timedelta(days=1),
                "internal_note": "환불 처리 완료 건 안내",
            },
        )
        OneToOneInquiry.objects.update_or_create(
            user=demo_user,
            title="상품 성분 문의",
            defaults={
                "content": "오메가3 제품에 알레르기 유발 성분이 포함되어 있는지 궁금합니다.",
                "category": OneToOneInquiry.Category.PRODUCT,
                "priority": OneToOneInquiry.Priority.LOW,
                "status": OneToOneInquiry.Status.CLOSED,
                "assigned_admin": admin_user,
                "answer": "알레르기 유발 가능 원료는 라벨 하단을 확인해 주세요.",
                "first_response_at": timezone.now() - timedelta(days=3),
                "answered_at": timezone.now() - timedelta(days=3),
                "resolved_at": timezone.now() - timedelta(days=2, hours=20),
            },
        )

        self.stdout.write(self.style.SUCCESS("데모 데이터 시드가 완료되었습니다."))
        self.stdout.write("- 로그인 계정: demo@sausalito.com / demo1234")
        self.stdout.write("- 관리자 계정: admin@sausalito.com / admin1234")
