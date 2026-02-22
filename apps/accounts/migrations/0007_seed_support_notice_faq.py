from __future__ import annotations

from django.db import migrations
from django.utils import timezone


NOTICE_SEED_ROWS = [
    {
        "title": "주문 폭주로 인한 배송 지연 안내",
        "content": "현재 주문량 증가로 일부 지역 배송이 1~2일 지연될 수 있습니다. 순차 출고 중이며 출고 즉시 송장정보를 안내드립니다.",
        "is_pinned": True,
        "is_active": True,
    },
    {
        "title": "계좌이체 입금 확인 시간 안내",
        "content": "계좌이체 주문은 평일 09:00~18:00 사이 순차 확인됩니다. 확인 완료 시 결제완료로 자동 전환됩니다.",
        "is_pinned": True,
        "is_active": True,
    },
    {
        "title": "취소/환불 처리 기준 안내",
        "content": "상품 출고 전 주문은 즉시 취소 가능하며, 출고 후에는 반품 접수 후 검수 완료 시 환불 처리됩니다.",
        "is_pinned": False,
        "is_active": True,
    },
    {
        "title": "고객센터 운영시간 변경 안내",
        "content": "고객지원 운영시간은 평일 10:00~17:00이며 점심시간(12:30~13:30)에는 상담이 제한됩니다.",
        "is_pinned": False,
        "is_active": True,
    },
]


FAQ_SEED_ROWS = [
    {
        "category": "주문/결제",
        "question": "주문 후 결제 방법을 변경할 수 있나요?",
        "answer": "주문 완료 후 결제수단 변경은 불가합니다. 기존 주문을 취소 후 다시 주문해 주세요.",
        "sort_order": 10,
        "is_active": True,
    },
    {
        "category": "주문/결제",
        "question": "계좌이체 입금 후 언제 결제완료 처리되나요?",
        "answer": "영업시간 내에는 순차적으로 확인되며, 일반적으로 1시간 이내 결제완료 처리됩니다.",
        "sort_order": 20,
        "is_active": True,
    },
    {
        "category": "배송",
        "question": "배송 조회는 어디서 확인하나요?",
        "answer": "마이페이지 주문내역에서 주문 상세를 열면 배송상태와 송장번호를 확인할 수 있습니다.",
        "sort_order": 10,
        "is_active": True,
    },
    {
        "category": "배송",
        "question": "배송지를 변경하고 싶어요.",
        "answer": "출고 전 상태에서만 변경 가능합니다. 고객지원 Q&A 또는 관리자 문의를 통해 요청해 주세요.",
        "sort_order": 20,
        "is_active": True,
    },
    {
        "category": "교환/환불",
        "question": "환불은 언제 완료되나요?",
        "answer": "반품 상품 검수 완료 후 1~3영업일 내 환불이 진행됩니다.",
        "sort_order": 10,
        "is_active": True,
    },
    {
        "category": "교환/환불",
        "question": "단순변심 반품이 가능한가요?",
        "answer": "수령 후 7일 이내 미개봉 상품에 한해 가능하며, 반품 배송비는 고객 부담입니다.",
        "sort_order": 20,
        "is_active": True,
    },
    {
        "category": "회원",
        "question": "회원정보는 어디서 수정하나요?",
        "answer": "로그인 후 마이페이지 > 회원정보수정에서 연락처, 주소, 수신동의를 변경할 수 있습니다.",
        "sort_order": 10,
        "is_active": True,
    },
]


def seed_support_content(apps, schema_editor):
    del schema_editor
    SupportNotice = apps.get_model("accounts", "SupportNotice")
    SupportFaq = apps.get_model("accounts", "SupportFaq")

    now = timezone.now()
    for row in NOTICE_SEED_ROWS:
        SupportNotice.objects.get_or_create(
            title=row["title"],
            defaults={
                "content": row["content"],
                "is_pinned": row["is_pinned"],
                "is_active": row["is_active"],
                "published_at": now,
            },
        )

    for row in FAQ_SEED_ROWS:
        SupportFaq.objects.get_or_create(
            category=row["category"],
            question=row["question"],
            defaults={
                "answer": row["answer"],
                "sort_order": row["sort_order"],
                "is_active": row["is_active"],
            },
        )


def unseed_support_content(apps, schema_editor):
    del schema_editor
    SupportNotice = apps.get_model("accounts", "SupportNotice")
    SupportFaq = apps.get_model("accounts", "SupportFaq")

    SupportNotice.objects.filter(title__in=[row["title"] for row in NOTICE_SEED_ROWS]).delete()
    for row in FAQ_SEED_ROWS:
        SupportFaq.objects.filter(category=row["category"], question=row["question"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_supportfaq_supportnotice"),
    ]

    operations = [
        migrations.RunPython(seed_support_content, unseed_support_content),
    ]
