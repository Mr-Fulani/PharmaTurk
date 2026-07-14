"""Синхронизация сохранённых цен с текущими маржами валютных пар."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction


CURRENCIES = ("RUB", "USD", "KZT", "EUR", "TRY", "USDT")


def price_with_pair_margin(converted_price, base_currency, target_currency, margins):
    if converted_price is None:
        return None
    pair = f"{(base_currency or '').upper()}-{target_currency.upper()}"
    margin = Decimal(str(margins.get(pair, 0)))
    value = Decimal(str(converted_price))
    return (value * (Decimal("1") + margin / Decimal("100"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def refresh_currency_margin_snapshots(*, batch_size=500):
    """Обновляет только колонки `*_with_margin`, не меняя курсы и базовые цены."""
    from apps.catalog.currency_models import (
        MarginSettings,
        ProductPrice,
        ProductVariantPrice,
        ServicePrice,
    )
    from apps.catalog.models import Product

    margins = dict(
        MarginSettings.objects.filter(is_active=True).values_list(
            "currency_pair", "margin_percentage"
        )
    )
    counts = {}

    def refresh_model(model, label):
        pending = []
        fields = [f"{currency.lower()}_price_with_margin" for currency in CURRENCIES]
        for row in model.objects.all().iterator(chunk_size=batch_size):
            for currency in CURRENCIES:
                raw = getattr(row, f"{currency.lower()}_price")
                setattr(
                    row,
                    f"{currency.lower()}_price_with_margin",
                    price_with_pair_margin(raw, row.base_currency, currency, margins),
                )
            pending.append(row)
            if len(pending) >= batch_size:
                model.objects.bulk_update(pending, fields, batch_size=batch_size)
                pending.clear()
        if pending:
            model.objects.bulk_update(pending, fields, batch_size=batch_size)
        counts[label] = model.objects.count()

    with transaction.atomic():
        refresh_model(ProductPrice, "products")
        refresh_model(ProductVariantPrice, "variants")
        refresh_model(ServicePrice, "services")
        products = [
            Product(
                pk=price.product_id,
                final_price_rub=price.rub_price_with_margin,
                final_price_usd=price.usd_price_with_margin,
            )
            for price in ProductPrice.objects.only(
                "product_id", "rub_price_with_margin", "usd_price_with_margin"
            ).iterator(chunk_size=batch_size)
        ]
        Product.objects.bulk_update(
            products, ["final_price_rub", "final_price_usd"], batch_size=batch_size
        )

    return counts
