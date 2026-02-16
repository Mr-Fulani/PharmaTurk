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

from apps.catalog.models import (
    ClothingVariant,
    ShoeVariant,
    FurnitureVariant,
    JewelryVariant,
    BookVariant,
)
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


def _serialize_translations_qs(translations) -> List[Dict[str, Any]]:
    if not translations:
        return []
    try:
        items = translations.all()
    except Exception:
        return []
    return [
        {
            "locale": translation.locale,
            "name": translation.name,
            "description": getattr(translation, "description", ""),
        }
        for translation in items
    ]


def _resolve_variant_translations(product) -> List[Dict[str, Any]]:
    if not product:
        return []
    ext = getattr(product, "external_data", {}) or {}
    source_variant_id = ext.get("source_variant_id")
    source_variant_slug = ext.get("source_variant_slug")
    if not source_variant_id and not source_variant_slug:
        return []
    product_type = getattr(product, "product_type", None)
    model_map = {
        "clothing": ClothingVariant,
        "shoes": ShoeVariant,
        "furniture": FurnitureVariant,
        "jewelry": JewelryVariant,
        "books": BookVariant,
    }
    model = model_map.get(product_type)
    if not model:
        return []
    qs = model.objects.all()
    if source_variant_id:
        qs = qs.filter(id=source_variant_id)
    elif source_variant_slug:
        qs = qs.filter(slug=source_variant_slug)
    variant = qs.select_related("product").first()
    if not variant:
        return []
    base_product = getattr(variant, "product", None)
    translations = _serialize_translations_qs(getattr(base_product, "translations", None))
    if translations:
        return translations
    name_en = getattr(variant, "name_en", "")
    if name_en:
        return [{"locale": "en", "name": name_en, "description": ""}]
    return []


def _serialize_product_translations(product) -> List[Dict[str, Any]]:
    if not product:
        return []
    translations = _serialize_translations_qs(getattr(product, "translations", None))
    if translations:
        return translations
    return _resolve_variant_translations(product)


# TODO: Функционал чеков временно отключен. Будет доработан позже.
def build_order_receipt_payload(order: Order) -> Dict[str, Any]:
    """Формирует структуру данных для отображения/отправки чека."""
    issued_at = timezone.now()
    currency = order.currency or "USD"

    items = [
        {
            "id": item.id,
            "product_name": item.product_name,
            "product_translations": _serialize_product_translations(item.product),
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


RECEIPT_LABELS = {
    "ru": {
        "title": "Чек заказа №",
        "issued": "Выдан",
        "created": "Заказ создан",
        "customer": "Покупатель",
        "seller": "Продавец",
        "product": "Товар",
        "qty": "Кол-во",
        "price": "Цена",
        "total_col": "Сумма",
        "shipping": "Доставка",
        "payment": "Оплата",
        "status": "Статус",
        "items_total": "Сумма товаров",
        "discount": "Скидка",
        "total": "Итого",
        "footer": "Если у вас остались вопросы, просто ответьте на это письмо или напишите нам на",
        "thanks": "Благодарим за заказ!",
    },
    "en": {
        "title": "Order receipt #",
        "issued": "Issued",
        "created": "Order created",
        "customer": "Customer",
        "seller": "Seller",
        "product": "Product",
        "qty": "Qty",
        "price": "Price",
        "total_col": "Total",
        "shipping": "Shipping",
        "payment": "Payment",
        "status": "Status",
        "items_total": "Items total",
        "discount": "Discount",
        "total": "Total",
        "footer": "If you have any questions, simply reply to this email or contact us at",
        "thanks": "Thank you for your order!",
    },
}


# TODO: Функционал чеков временно отключен. Будет доработан позже.
def render_receipt_html(
    order: Order, receipt: Dict[str, Any] | None = None, locale: str = "ru"
) -> str:
    """Рендерит HTML-версию чека на указанном языке."""
    payload = receipt or build_order_receipt_payload(order)
    loc = "en" if (locale or "").strip().lower() == "en" else "ru"
    labels = RECEIPT_LABELS.get(loc, RECEIPT_LABELS["ru"])
    context = {
        "order": order,
        "receipt": payload,
        "labels": labels,
        "lang": loc,
    }
    return render_to_string("emails/order_receipt.html", context)
