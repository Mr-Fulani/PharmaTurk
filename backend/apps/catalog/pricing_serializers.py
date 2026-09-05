"""Shared public-pricing primitives for catalog serializers."""

import logging
import re
from decimal import Decimal, ROUND_HALF_UP

from .utils.product_markup import get_effective_product_markup


logger = logging.getLogger(__name__)


def preferred_currency(request, default="RUB"):
    """Resolve the storefront currency consistently for catalog payloads."""
    if not request:
        return default
    explicit = request.headers.get("X-Currency") or request.query_params.get("currency")
    if explicit:
        return explicit.upper()
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        user_currency = getattr(user, "currency", None)
        if user_currency:
            return user_currency.upper()
    return {"en": "USD", "ru": "RUB"}.get(
        getattr(request, "LANGUAGE_CODE", None), default
    )


def public_price(amount, from_currency, request, *, currency_resolver=None):
    """Return a public amount with the active currency-pair margin."""
    if amount is None:
        return None, (from_currency or "RUB").upper()
    source = (from_currency or "RUB").upper()
    resolve_currency = currency_resolver or preferred_currency
    target = resolve_currency(request)
    try:
        from .utils.currency_converter import currency_converter

        _, _, with_margin = currency_converter.convert_price(
            Decimal(str(amount)), source, target, apply_margin=True
        )
        return with_margin, target
    except Exception:
        logger.exception("Failed to calculate public price %s %s", amount, source)
        return amount, source


def effective_product_markup(obj):
    return get_effective_product_markup(obj)


def apply_markup_value(value, margin):
    if value is None or margin <= 0:
        return value
    return (Decimal(str(value)) * (Decimal("1") + margin / Decimal("100"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def apply_markup_formatted(value, margin, *, value_transform=None):
    if not value or margin <= 0:
        return value
    match = re.match(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s+([A-Za-z]{3,5})\s*$", str(value))
    if not match:
        return value
    transform = value_transform or apply_markup_value
    amount = transform(match.group(1).replace(",", "."), margin)
    return f"{amount} {match.group(2).upper()}"


def apply_product_markup_to_payload(
    data,
    obj,
    *,
    markup_resolver=None,
    value_transform=None,
    formatted_transform=None,
):
    """Apply product markup after currency conversion across a catalog payload."""
    resolve_markup = markup_resolver or effective_product_markup
    transform_value = value_transform or apply_markup_value
    transform_formatted = formatted_transform or apply_markup_formatted
    margin, source = resolve_markup(obj)
    if margin <= 0:
        data["product_markup_percent"] = Decimal("0")
        data["product_markup_source"] = None
        return data

    for field in ("price", "old_price", "final_price_rub", "final_price_usd"):
        if field in data and data[field] is not None:
            data[field] = transform_value(data[field], margin)
    for field in (
        "price_formatted",
        "old_price_formatted",
        "active_variant_price",
        "active_variant_old_price_formatted",
    ):
        if field in data:
            data[field] = transform_formatted(data[field], margin)

    for collection_name in ("variants", "book_variants"):
        for row in data.get(collection_name) or []:
            for field in ("price", "old_price"):
                if row.get(field) is not None:
                    row[field] = transform_value(row[field], margin)
            for field in ("price_formatted", "old_price_formatted"):
                if field in row:
                    row[field] = transform_formatted(row[field], margin)

    current = data.get("current_price")
    if isinstance(current, dict) and current.get("amount") is not None:
        current["amount"] = transform_value(current["amount"], margin)
        current["formatted"] = f"{current['amount']} {current.get('currency', '')}".strip()
    for price_data in (data.get("prices_in_currencies") or {}).values():
        if isinstance(price_data, dict) and price_data.get("price_with_margin") is not None:
            price_data["price_with_margin"] = transform_value(
                price_data["price_with_margin"], margin
            )
    prices_info = data.get("prices_info")
    if isinstance(prices_info, dict):
        for currency in ("rub", "usd", "kzt", "eur", "try", "usdt"):
            field = f"{currency}_price_with_margin"
            if prices_info.get(field) is not None:
                prices_info[field] = transform_value(prices_info[field], margin)

    data["product_markup_percent"] = margin
    data["product_markup_source"] = source
    return data
