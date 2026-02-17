from __future__ import annotations

from apps.orders.models import Order


def apply_order_payment_approval(order: Order) -> None:
    """Approve payment and deduct stock once for unpaid orders."""
    if order.status != Order.Status.PAID:
        for item in order.items.select_related("product", "product_option"):
            product = item.product
            option = item.product_option
            if product and product.stock < item.quantity:
                raise ValueError(f"재고가 부족합니다. ({product.name})")
            if option and option.stock < item.quantity:
                raise ValueError(f"재고가 부족합니다. ({option.name})")

        for item in order.items.select_related("product", "product_option"):
            product = item.product
            option = item.product_option
            if product:
                product.stock -= item.quantity
                product.save(update_fields=["stock", "updated_at"])
            if option:
                option.stock -= item.quantity
                option.save(update_fields=["stock"])

    order.status = Order.Status.PAID
    order.payment_status = Order.PaymentStatus.APPROVED
    order.save(update_fields=["status", "payment_status", "updated_at"])
