"""Ручные действия из окна проверки (TD-044, шаг 3): принять цену IlacFiyati, сменить наличие.

Ничего не меняется без нажатия человека: окно проверки только предлагает кнопку, затем страница
подтверждения «было → станет» и POST. Цена берётся из подписанной записи проверки (не из формы
и не новым запросом к источнику) и живёт час. Запись — через MedicineProduct.save(): он
синхронизирует Product, а Product.save() пересчитывает цены в валютах — тем же путём цену меняет
админка и проверка цены на витрине. Цену склада не принимаем: это его прайс, база цены — IlacFiyati.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import MedicineProduct, PriceHistory

from .sources.base import ERROR, fmt_date, fmt_price

PRICE_SALT = "drug_check.accept_price"
PRICE_OFFER_MAX_AGE = 60 * 60  # секунд: дольше — проверить заново
PRICE_HISTORY_SOURCE = "drug_check_manual"


def money(value: Decimal | None, currency: str) -> str:
    if value is None:
        return "нет"
    text = fmt_price(value)
    return text if (currency or "TRY").upper() == "TRY" else text.replace(" TL", f" {currency.upper()}")


def _ilacfiyati(report):
    return next((r for r in report.results if r.key == "ilacfiyati"), None)


def price_action(report) -> dict:
    """{"offer": {...} | None, "note": "..."} для окна проверки."""
    medicine = report.medicine
    if medicine is None:
        return {"offer": None, "note": ""}
    if medicine.is_hospital:
        return {"offer": None, "note": "Больничный препарат («цена по запросу») — цену не принимаем."}
    result = _ilacfiyati(report)
    if result is None or result.level == ERROR or result.price is None:
        return {"offer": None, "note": "Цену IlacFiyati получить не удалось — принимать нечего."}
    currency = (result.currency or "TRY").upper()
    if medicine.price is not None and Decimal(str(medicine.price)) == result.price and (
        (medicine.currency or "").upper() == currency
    ):
        return {"offer": None, "note": "Наша цена совпадает с IlacFiyati — менять нечего."}
    payload = {
        "m": medicine.pk,
        "p": str(result.price),
        "c": currency,
        "d": result.price_date.isoformat() if result.price_date else "",
        "u": result.url,
        "t": timezone.now().isoformat(),
    }
    offer = read_offer(signing.dumps(payload, salt=PRICE_SALT), medicine.pk)
    return {"offer": offer, "note": ""}


def read_offer(token: str, medicine_id: int) -> dict | None:
    """Подписанная цена из проверки этого лекарства или None (подделка, чужое, устарело)."""
    try:
        payload = signing.loads(token or "", salt=PRICE_SALT, max_age=PRICE_OFFER_MAX_AGE)
        price = Decimal(payload["p"]).quantize(Decimal("0.01"))
    except (signing.BadSignature, KeyError, TypeError, InvalidOperation):
        return None
    if payload.get("m") != medicine_id or price <= 0:
        return None
    price_date = date.fromisoformat(payload["d"]) if payload.get("d") else None
    return {
        "token": token,
        "price": price,
        "currency": str(payload.get("c") or "TRY").upper()[:5],
        "price_date": price_date,
        "url": payload.get("u", ""),
        "checked_at": payload.get("t", ""),
        "label": f"{money(price, payload.get('c') or 'TRY')} (IlacFiyati"
        + (f", цена от {fmt_date(price_date)})" if price_date else ")"),
    }


def availability_action(report) -> dict | None:
    medicine = report.medicine
    if medicine is None:
        return None
    to = not medicine.is_available
    return {
        "to": "1" if to else "0",
        "label": "Отметить: в наличии" if to else "Отметить: нет в наличии",
        "hint": "; ".join(r.short for r in report.results if r.short),
    }


def availability_label(value: bool) -> str:
    return "в наличии" if value else "нет в наличии"


def apply_price(medicine_id: int, offer: dict) -> tuple[MedicineProduct, Decimal | None, str] | None:
    """Пишет цену; (лекарство, прежняя цена, прежняя валюта) или None, если менять нельзя/нечего."""
    with transaction.atomic():
        medicine = MedicineProduct.objects.select_for_update().get(pk=medicine_id)
        old_price, old_currency = medicine.price, (medicine.currency or "")
        if medicine.is_hospital or (old_price == offer["price"] and old_currency.upper() == offer["currency"]):
            return None
        # Цены лекарств регулируются: прежняя цена — не «старая цена со скидкой».
        medicine.old_price = None
        medicine.price = offer["price"]
        medicine.currency = offer["currency"]
        medicine.save()  # синхронизирует Product, тот пересчитывает цены в валютах
        if medicine.base_product_id:
            PriceHistory.objects.create(
                product_id=medicine.base_product_id,
                price=offer["price"],
                currency=offer["currency"],
                source=PRICE_HISTORY_SOURCE,
            )
    return medicine, old_price, old_currency


def apply_availability(medicine_id: int, to: bool) -> MedicineProduct | None:
    with transaction.atomic():
        medicine = MedicineProduct.objects.select_for_update().get(pk=medicine_id)
        if medicine.is_available == to:
            return None
        medicine.is_available = to
        medicine.save()  # синхронизирует наличие в Product
    return medicine
