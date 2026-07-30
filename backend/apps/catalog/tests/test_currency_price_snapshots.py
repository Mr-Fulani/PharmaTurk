from decimal import Decimal

import pytest

from apps.catalog.currency_models import ServicePrice
from apps.catalog.currency_price_snapshots import (
    price_with_pair_margin,
    refresh_usdt_price_snapshots,
)
from apps.catalog.models import Service
from apps.catalog.utils.currency_converter import currency_converter


def test_snapshot_without_active_pair_margin_equals_converted_price():
    assert price_with_pair_margin(Decimal("245.63"), "TRY", "RUB", {}) == Decimal("245.63")


def test_snapshot_applies_only_matching_currency_pair_margin():
    margins = {"TRY-RUB": Decimal("5"), "USD-RUB": Decimal("20")}

    assert price_with_pair_margin(Decimal("245.63"), "TRY", "RUB", margins) == Decimal("257.91")
    assert price_with_pair_margin(Decimal("3.21"), "TRY", "USD", margins) == Decimal("3.21")


def test_snapshot_zero_margin_removes_old_stored_markup():
    # Старое значение 282.47 в расчёт не передаётся: источником является 245.63.
    assert price_with_pair_margin(Decimal("245.63"), "TRY", "RUB", {"TRY-RUB": 0}) == Decimal("245.63")


@pytest.mark.django_db
def test_usdt_snapshot_refresh_replaces_price_from_old_markup(monkeypatch):
    service = Service.objects.create(
        name="USDT snapshot",
        slug="usdt-snapshot",
        price=None,
        currency="TRY",
    )
    price = ServicePrice.objects.create(
        service=service,
        base_currency="TRY",
        base_price=Decimal("10000"),
        usdt_price=Decimal("217.61"),
        usdt_price_with_margin=Decimal("217.61"),
    )

    monkeypatch.setattr(
        currency_converter,
        "convert_to_multiple_currencies",
        lambda amount, base_currency, targets, apply_margin: {
            target: {
                "original_price": amount,
                "converted_price": Decimal("221.83"),
                "price_with_margin": Decimal("221.83"),
            }
            for target in targets
        },
    )

    result = refresh_usdt_price_snapshots()

    price.refresh_from_db()
    assert price.usdt_price == Decimal("221.83")
    assert price.usdt_price_with_margin == Decimal("221.83")
    assert result["services"] == 1
    assert result["errors"] == 0
