"""
Утилиты для формирования и отправки чеков по заказам.

TODO: Функционал чеков временно отключен. Будет доработан позже.
Включает: формирование чека, отправку по email, интеграцию с админкой.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from apps.users.models import UserAddress

from .models import Order


def _decimal(value: Decimal | None) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(value or 0)


def _format_address(address: UserAddress | None, fallback: str = "") -> str:
    if not address:
        return fallback

    parts: List[str] = [
        address.country,
        address.region,
        address.city,
        f"{address.street} {address.house}".strip(),
    ]

    if address.apartment:
        parts.append(f"{address.apartment}")
    if address.entrance:
        parts.append(f"подъезд {address.entrance}")
    if address.floor:
        parts.append(f"этаж {address.floor}")

    return ", ".join(part for part in parts if part)


# TODO: Функционал чеков временно отключен. Будет доработан позже.
def build_order_receipt_payload(order: Order) -> Dict[str, Any]:
    """Формирует структуру данных для отображения/отправки чека."""
    issued_at = timezone.now()
    currency = order.currency or "USD"

    items = [
        {
            "id": item.id,
            "product_name": item.product_name,
            "quantity": item.quantity,
            "price": _decimal(item.price),
            "total": _decimal(item.total),
            "currency": currency,
        }
        for item in order.items.all()
    ]

    subtotal = _decimal(order.subtotal_amount)
    shipping = _decimal(order.shipping_amount)
    discount = _decimal(order.discount_amount)
    total = _decimal(order.total_amount or (subtotal + shipping - discount))

    seller = {
        "name": getattr(settings, "COMPANY_NAME", "PharmaTurk"),
        "email": getattr(settings, "COMPANY_SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL),
        "phone": getattr(settings, "COMPANY_SUPPORT_PHONE", ""),
        "address": getattr(settings, "COMPANY_ADDRESS", ""),
        "site": getattr(settings, "COMPANY_SITE_URL", "https://pharmaturk.ru"),
    }

    customer = {
        "name": order.contact_name,
        "phone": order.contact_phone,
        "email": order.contact_email or (order.user.email if order.user else ""),
    }

    shipping_info = {
        "method": order.shipping_method or "-",
        "address": order.shipping_address_text
        or _format_address(order.shipping_address),
    }

    payment = {
        "method": order.payment_method or "-",
        "status": order.payment_status or "unpaid",
    }

    totals = {
        "items": subtotal,
        "shipping": shipping,
        "discount": discount,
        "total": total,
        "currency": currency,
    }

    meta = {
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "issued_at": issued_at,
        "receipt_number": f"RC-{order.number}",
        "comment": order.comment or "",
    }

    return {
        "number": order.number,
        "status": order.status,
        "currency": currency,
        "items": items,
        "seller": seller,
        "customer": customer,
        "shipping": shipping_info,
        "payment": payment,
        "totals": totals,
        "meta": meta,
        "issued_at": issued_at,
        "promo_code": order.promo_code.code if order.promo_code else None,
    }


# TODO: Функционал чеков временно отключен. Будет доработан позже.
def render_receipt_html(order: Order, receipt: Dict[str, Any] | None = None) -> str:
    """Рендерит HTML-версию чека."""
    payload = receipt or build_order_receipt_payload(order)
    context = {
        "order": order,
        "receipt": payload,
    }
    return render_to_string("emails/order_receipt.html", context)


