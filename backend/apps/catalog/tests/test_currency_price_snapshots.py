from decimal import Decimal

from apps.catalog.currency_price_snapshots import price_with_pair_margin


def test_snapshot_without_active_pair_margin_equals_converted_price():
    assert price_with_pair_margin(Decimal("245.63"), "TRY", "RUB", {}) == Decimal("245.63")


def test_snapshot_applies_only_matching_currency_pair_margin():
    margins = {"TRY-RUB": Decimal("5"), "USD-RUB": Decimal("20")}

    assert price_with_pair_margin(Decimal("245.63"), "TRY", "RUB", margins) == Decimal("257.91")
    assert price_with_pair_margin(Decimal("3.21"), "TRY", "USD", margins) == Decimal("3.21")


def test_snapshot_zero_margin_removes_old_stored_markup():
    # Старое значение 282.47 в расчёт не передаётся: источником является 245.63.
    assert price_with_pair_margin(Decimal("245.63"), "TRY", "RUB", {"TRY-RUB": 0}) == Decimal("245.63")
