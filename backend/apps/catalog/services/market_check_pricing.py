"""Public display pricing for on-demand source observations.

Market-check services deliberately persist and expose the unmodified source price.
This module adds a separate display price that follows the same conversion and
markup rules as ordinary catalog serializers. Keeping both values prevents a UI
refresh from replacing a converted public price with the raw supplier currency.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from apps.catalog.utils.currency_converter import currency_converter
from apps.catalog.utils.product_markup import (
    apply_product_markup,
    get_effective_product_markup,
)

logger = logging.getLogger(__name__)

SUPPORTED_CURRENCIES = frozenset(currency_converter.get_supported_currencies())


def _requested_currency(request) -> str:
    explicit = request.headers.get("X-Currency") or request.query_params.get("currency")
    if explicit:
        normalized = str(explicit).strip().upper()
        if normalized in SUPPORTED_CURRENCIES:
            return normalized

    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        normalized = str(getattr(user, "currency", "") or "").strip().upper()
        if normalized in SUPPORTED_CURRENCIES:
            return normalized

    language = str(getattr(request, "LANGUAGE_CODE", "") or "").lower()
    return "USD" if language.startswith("en") else "RUB"


def attach_public_market_price(
    payload: dict[str, Any],
    *,
    product,
    request,
) -> dict[str, Any]:
    """Attach converted public pricing while retaining ``price`` as source truth."""

    raw_price = payload.get("price")
    if not isinstance(raw_price, dict) or raw_price.get("amount") is None:
        return payload

    source_currency = str(raw_price.get("currency") or "TRY").strip().upper()
    target_currency = _requested_currency(request)
    try:
        source_amount = Decimal(str(raw_price["amount"]))
        if not source_amount.is_finite() or source_amount <= 0:
            raise InvalidOperation("market price must be positive and finite")
        _original, _converted, with_pair_margin = currency_converter.convert_price(
            source_amount,
            source_currency,
            target_currency,
            apply_margin=True,
        )
        display_amount = Decimal(str(apply_product_markup(with_pair_margin, product))).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        pair_margin = currency_converter.get_margin_rate(source_currency, target_currency)
        product_markup, product_markup_source = get_effective_product_markup(product)
    except Exception:
        # A market observation remains useful even when a rate/config dependency is
        # temporarily unavailable. The client can fall back to the raw source price.
        logger.exception(
            "market_check_public_price_failed",
            extra={
                "product_id": getattr(product, "pk", None),
                "source_currency": source_currency,
                "target_currency": target_currency,
            },
        )
        return payload

    payload["display_price"] = {
        "amount": str(display_amount),
        "currency": target_currency,
    }
    payload["price_calculation"] = {
        "source_currency": source_currency,
        "target_currency": target_currency,
        "currency_pair_margin_percent": str(Decimal(str(pair_margin))),
        "product_markup_percent": str(Decimal(str(product_markup))),
        "product_markup_source": product_markup_source,
    }
    return payload
