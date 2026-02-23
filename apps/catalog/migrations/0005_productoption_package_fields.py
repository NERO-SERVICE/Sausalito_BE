from __future__ import annotations

import re

from django.db import migrations, models

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


def _extract_months(name: str) -> int | None:
    match = re.search(r"(\d+)\s*개월", str(name or ""))
    if not match:
        return None
    try:
        month = int(match.group(1))
    except (TypeError, ValueError):
        return None
    return month if month in PACKAGE_MONTHS else None


def _default_price(base_price: int, months: int) -> int:
    safe_base_price = max(int(base_price or 0), 0)
    rate = int(PACKAGE_DISCOUNT_RATE_MAP.get(months, 0))
    return int(round((safe_base_price * months) * (100 - rate) / 100))


def populate_product_option_packages(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    ProductOption = apps.get_model("catalog", "ProductOption")

    for product in Product.objects.all().iterator():
        options = list(ProductOption.objects.filter(product=product).order_by("id"))
        selected_by_month: dict[int, object] = {}

        for option in options:
            month = option.duration_months if option.duration_months in PACKAGE_MONTHS else _extract_months(option.name)
            if month and month not in selected_by_month:
                selected_by_month[month] = option
                updated_fields: list[str] = []
                if option.duration_months != month:
                    option.duration_months = month
                    updated_fields.append("duration_months")
                if not (option.benefit_label or "").strip():
                    option.benefit_label = PACKAGE_BENEFIT_MAP[month]
                    updated_fields.append("benefit_label")
                if updated_fields:
                    option.save(update_fields=updated_fields)
                continue

            if option.duration_months is not None:
                option.duration_months = None
                option.save(update_fields=["duration_months"])

        for month in PACKAGE_MONTHS:
            if month in selected_by_month:
                continue
            ProductOption.objects.create(
                product=product,
                duration_months=month,
                benefit_label=PACKAGE_BENEFIT_MAP[month],
                name=PACKAGE_NAME_MAP[month],
                price=_default_price(product.price, month),
                stock=max(int(product.stock or 0), 0),
                is_active=True,
            )


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_brandpagesetting_brandstorysection"),
    ]

    operations = [
        migrations.AddField(
            model_name="productoption",
            name="duration_months",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="productoption",
            name="benefit_label",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.RunPython(populate_product_option_packages, noop_reverse),
        migrations.AddConstraint(
            model_name="productoption",
            constraint=models.UniqueConstraint(
                condition=models.Q(duration_months__isnull=False),
                fields=("product", "duration_months"),
                name="uniq_product_option_duration_months",
            ),
        ),
    ]
