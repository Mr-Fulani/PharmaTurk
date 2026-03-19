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
from django.core.files.base import ContentFile  # noqa: F401 – kept for potential future use

import boto3
from apps.catalog.utils.r2_utils import get_r2_client, get_r2_path

from apps.catalog.models import (
    ClothingVariant,
    ShoeVariant,
    FurnitureVariant,
    JewelryVariant,
    BookVariant,
)
from apps.users.models import UserAddress

from .models import Order


SHIPPING_METHOD_TRANSLATIONS = {
    "ru": {
        "air": "Авиадоставка",
        "sea": "Морская доставка",
        "ground": "Наземная доставка",
        "pickup": "Самовывоз",
    },
    "en": {
        "air": "Air Delivery",
        "sea": "Sea Delivery",
        "ground": "Ground Delivery",
        "pickup": "Pickup",
    }
}

PAYMENT_METHOD_TRANSLATIONS = {
    "ru": {
        "cod": "Наложенный платеж (при получении)",
        "card": "Банковской картой",
        "crypto": "Криптовалюта",
    },
    "en": {
        "cod": "Cash on Delivery",
        "card": "Bank Card",
        "crypto": "Cryptocurrency",
    }
}

PAYMENT_STATUS_TRANSLATIONS = {
    "ru": {
        "unpaid": "Не оплачено",
        "pending": "В ожидании оплаты",
        "paid": "Оплачено",
        "failed": "Ошибка оплаты",
        "expired": "Просрочено",
        "canceled": "Отменено",
    },
    "en": {
        "unpaid": "Unpaid",
        "pending": "Pending",
        "paid": "Paid",
        "failed": "Failed",
        "expired": "Expired",
        "canceled": "Canceled",
    }
}


def get_order_customer_email(order: Order) -> str | None:
    # Основной источник email покупателя — contact_email из формы
    email = (getattr(order, "contact_email", "") or "").strip()
    if email:
        return email

    # Если контактный email не указан, берём email пользователя, но не для админов/сотрудников
    user = getattr(order, "user", None)
    if not user:
        return None
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return None

    return (getattr(user, "email", "") or "").strip() or None


def translate_method(method: str | None, dict_map: Dict[str, Dict[str, str]], locale: str) -> str:
    if not method:
        return "-"
    m = method.strip().lower()
    loc = "en" if locale == "en" else "ru"
    return dict_map.get(loc, {}).get(m, method)


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
def build_order_receipt_payload(order: Order, locale: str = 'ru') -> Dict[str, Any]:
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
    # Добавляем ссылки соцсетей из FooterSettings
    try:
        from apps.settings.models import FooterSettings
        fs = FooterSettings.objects.first()
        if fs:
            seller["telegram_url"] = getattr(fs, "telegram_url", "") or ""
            seller["whatsapp_url"] = getattr(fs, "whatsapp_url", "") or ""
            seller["instagram_url"] = getattr(fs, "instagram_url", "") or ""
            if getattr(fs, "phone", ""):
                seller["phone"] = fs.phone
            if getattr(fs, "email", ""):
                seller["email"] = fs.email
    except Exception:
        pass

    customer = {
        "name": order.contact_name,
        "phone": order.contact_phone,
        "email": order.contact_email or (order.user.email if order.user else ""),
    }

    shipping_info = {
        "method": translate_method(order.shipping_method, SHIPPING_METHOD_TRANSLATIONS, locale),
        "address": order.shipping_address_text
        or _format_address(order.shipping_address),
    }

    payment = {
        "method": translate_method(order.payment_method, PAYMENT_METHOD_TRANSLATIONS, locale),
        "status": translate_method(order.payment_status or "unpaid", PAYMENT_STATUS_TRANSLATIONS, locale),
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
def get_receipt_filename(order: Order) -> str:
    """Имя файла чека с данными клиента для ясности: receipt_ДАТА_НОМЕР_ИМЯ.pdf"""
    date_str = (order.created_at or timezone.now()).strftime('%Y%m%d')
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (order.contact_name or "client"))[:20]
    return f"receipt_{date_str}_{order.number}_{safe_name}.pdf"


def render_receipt_html(
    order: Order, receipt: Dict[str, Any] | None = None, locale: str = "ru"
) -> str:
    """Рендерит HTML-версию чека на указанном языке."""
    loc = "en" if (locale or "").strip().lower() == "en" else "ru"
    payload = receipt or build_order_receipt_payload(order, locale=loc)
    labels = RECEIPT_LABELS.get(loc, RECEIPT_LABELS["ru"])
    context = {
        "order": order,
        "receipt": payload,
        "labels": labels,
        "lang": loc,
    }
    return render_to_string("emails/order_receipt.html", context)


def generate_and_save_receipt(order: Order, locale: str = "ru") -> tuple[str | None, bytes | None]:
    """Генерирует PDF-версию чека и сохраняет её в Cloudflare R2 (или ином S3-хранилище).
    Возвращает (URL чека на CDN, сырые байты PDF).
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        if not settings.R2_CONFIG.get("endpoint_url") or not settings.R2_CONFIG.get("bucket_name"):
            return None, None
        html_string = render_receipt_html(order, locale=locale)
        from weasyprint import HTML  # lazy import — требует системных библиотек Pango/Cairo
        pdf_file = HTML(string=html_string).write_pdf()

        # Настраиваем boto3 клиент для работы с R2
        file_key = get_r2_path(f"receipts/{order.number}.pdf")
        s3 = get_r2_client()
        bucket_name = settings.R2_CONFIG['bucket_name']

        # Загружаем PDF в бакет
        s3.put_object(
            Bucket=bucket_name,
            Key=file_key,
            Body=pdf_file,
            ContentType='application/pdf',
            ContentDisposition=f'inline; filename="{get_receipt_filename(order)}"',
        )

        cdn_url = settings.AI_R2_SETTINGS.get('cdn_url', '').rstrip('/')
        if not cdn_url:
            cdn_url = f"{settings.R2_CONFIG['endpoint_url']}/{bucket_name}"

        receipt_url = f"{cdn_url}/{file_key}"
        
        # Сохраняем URL в заказ
        order.receipt_url = receipt_url
        order.save(update_fields=['receipt_url'])

        return receipt_url, pdf_file

    except Exception as e:
        import traceback
        logger.error(f"CRITICAL ERROR generating/saving receipt for order {order.number}: {str(e)}")
        logger.error(traceback.format_exc())
        return None, None
