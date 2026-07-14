"""Расчёт доставки в USD с обратной совместимостью со старыми тарифами."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from apps.catalog.currency_models import GlobalCurrencySettings, ProductPrice, ProductVariantPrice


METHODS = ("air", "sea", "ground")
ZERO = Decimal("0")


def _decimal(value, default=ZERO) -> Decimal:
    if value is None:
        return Decimal(str(default))
    return Decimal(str(value))


def resolve_category_shipping_rule(category):
    """Возвращает ближайшую категорию с явным правилом доставки."""
    seen = set()
    current = category
    while current is not None:
        key = getattr(current, "pk", None)
        key = key if key is not None else id(current)
        if key in seen:
            break
        seen.add(key)
        if getattr(current, "shipping_calculation", "inherit") != "inherit":
            return current
        current = getattr(current, "parent", None)
    return None


def _explicit_cost(variant_price, price_info, attr):
    for source in (variant_price, price_info):
        if source is not None:
            value = getattr(source, attr, None)
            if value is not None:
                return _decimal(value)
    return None


def _category_or_global_base(rule, global_settings, method):
    if rule is not None:
        value = getattr(rule, f"{method}_shipping_cost_usd", None)
        if value is not None:
            return _decimal(value)
    return _decimal(getattr(global_settings, f"default_{method}_shipping_usd"))


def resolve_shipping_costs_usd(
    variant_price: Optional["ProductVariantPrice"],
    price_info: Optional["ProductPrice"],
    global_settings: "GlobalCurrencySettings",
    category=None,
) -> Tuple[Decimal, Decimal, Decimal]:
    """Фиксированная база: вариант → товар → категория → глобальные настройки."""
    rule = resolve_category_shipping_rule(category)
    values = []
    for method in METHODS:
        explicit = _explicit_cost(variant_price, price_info, f"{method}_shipping_cost")
        values.append(explicit if explicit is not None else _category_or_global_base(rule, global_settings, method))
    return tuple(values)


def _weight_kg(product) -> Decimal:
    value = getattr(product, "weight_value", None)
    if value is None:
        return ZERO
    units = (getattr(product, "weight_unit", "g") or "g").lower()
    factors = {"g": Decimal("0.001"), "kg": Decimal("1"), "lb": Decimal("0.45359237"), "oz": Decimal("0.028349523125")}
    return _decimal(value) * factors.get(units, Decimal("0.001"))


def _dimensions_cm(product):
    raw = [getattr(product, name, None) for name in ("length", "width", "height")]
    if any(value is None for value in raw):
        return None
    units = (getattr(product, "dimensions_unit", "cm") or "cm").lower()
    factors = {"mm": Decimal("0.1"), "cm": Decimal("1"), "m": Decimal("100"), "in": Decimal("2.54")}
    factor = factors.get(units, Decimal("1"))
    return tuple(_decimal(value) * factor for value in raw)


def _volume_m3(product) -> Decimal:
    dimensions = _dimensions_cm(product)
    if not dimensions:
        return ZERO
    length, width, height = dimensions
    return length * width * height / Decimal("1000000")


def _chargeable_weight_kg(product, global_settings) -> Decimal:
    actual = _weight_kg(product)
    dimensions = _dimensions_cm(product)
    if not dimensions:
        return actual
    divisor = _decimal(getattr(global_settings, "shipping_volumetric_divisor", 5000), 5000)
    volumetric = dimensions[0] * dimensions[1] * dimensions[2] / divisor
    return max(actual, volumetric)


def calculate_item_shipping_costs_usd(product, quantity, variant_price, price_info, global_settings):
    """Считает строку корзины; старые явные тарифы всегда остаются фиксированными за единицу."""
    quantity = max(int(quantity or 0), 0)
    rule = resolve_category_shipping_rule(getattr(product, "category", None))
    mode = getattr(rule, "shipping_calculation", "fixed") if rule else "fixed"
    result = {}

    for method in METHODS:
        explicit = _explicit_cost(variant_price, price_info, f"{method}_shipping_cost")
        if explicit is not None:
            result[method] = explicit * quantity
            continue

        base = _category_or_global_base(rule, global_settings, method)
        if mode == "weight":
            rate = _decimal(getattr(rule, f"{method}_shipping_rate_per_kg_usd", None))
            result[method] = (base + rate * _chargeable_weight_kg(product, global_settings)) * quantity
        elif mode == "volume":
            rate = _decimal(getattr(rule, f"{method}_shipping_rate_per_m3_usd", None))
            result[method] = (base + rate * _volume_m3(product)) * quantity
        else:
            result[method] = base * quantity

    return result


def product_shipping_requires_quote(product) -> bool:
    """Явное правило категории перекрывает старый furniture-fallback."""
    rule = resolve_category_shipping_rule(getattr(product, "category", None))
    if rule is not None:
        return getattr(rule, "shipping_calculation", None) == "quote"
    return getattr(product, "product_type", None) == "furniture"


def product_is_free_shipping_eligible(product) -> bool:
    rule = resolve_category_shipping_rule(getattr(product, "category", None))
    return True if rule is None else bool(getattr(rule, "free_shipping_eligible", True))
