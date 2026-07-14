from decimal import Decimal
from types import SimpleNamespace

from apps.orders.shipping_pricing import (
    calculate_item_shipping_costs_usd,
    product_is_free_shipping_eligible,
    product_shipping_requires_quote,
    resolve_shipping_costs_usd,
)
from apps.orders.serializers import CartItemSerializer, CartSerializer


def obj(**kwargs):
    return SimpleNamespace(**kwargs)


def globals_(**overrides):
    values = {
        "default_air_shipping_usd": Decimal("7"),
        "default_sea_shipping_usd": Decimal("5"),
        "default_ground_shipping_usd": Decimal("4"),
        "shipping_volumetric_divisor": 5000,
    }
    values.update(overrides)
    return obj(**values)


def category(mode="inherit", parent=None, **overrides):
    values = {
        "pk": object(),
        "shipping_calculation": mode,
        "parent": parent,
        "free_shipping_eligible": True,
    }
    for method in ("air", "sea", "ground"):
        values[f"{method}_shipping_cost_usd"] = None
        values[f"{method}_shipping_rate_per_kg_usd"] = None
        values[f"{method}_shipping_rate_per_m3_usd"] = None
    values.update(overrides)
    return obj(**values)


def product(category_=None, **overrides):
    values = {
        "category": category_,
        "product_type": "clothing",
        "weight_value": None,
        "weight_unit": "g",
        "length": None,
        "width": None,
        "height": None,
        "dimensions_unit": "cm",
    }
    values.update(overrides)
    return obj(**values)


def test_legacy_cart_keeps_global_fixed_cost_per_unit():
    costs = calculate_item_shipping_costs_usd(product(), 3, None, None, globals_())
    assert costs == {"air": Decimal("21"), "sea": Decimal("15"), "ground": Decimal("12")}


def test_zero_variant_override_wins_over_product_category_and_global():
    rule = category("fixed", air_shipping_cost_usd=Decimal("6"))
    product_price = obj(air_shipping_cost=Decimal("3"), sea_shipping_cost=None, ground_shipping_cost=None)
    variant_price = obj(air_shipping_cost=Decimal("0"), sea_shipping_cost=None, ground_shipping_cost=None)
    costs = resolve_shipping_costs_usd(variant_price, product_price, globals_(), rule)
    assert costs == (Decimal("0"), Decimal("5"), Decimal("4"))


def test_child_category_inherits_nearest_explicit_rule():
    parent = category("fixed", ground_shipping_cost_usd=Decimal("12"))
    child = category("inherit", parent=parent)
    costs = calculate_item_shipping_costs_usd(product(child), 2, None, None, globals_())
    assert costs["ground"] == Decimal("24")


def test_weight_mode_uses_greater_of_actual_and_volumetric_weight():
    rule = category(
        "weight",
        air_shipping_cost_usd=Decimal("2"),
        air_shipping_rate_per_kg_usd=Decimal("3"),
    )
    item = product(
        rule,
        weight_value=Decimal("1"),
        weight_unit="kg",
        length=Decimal("50"),
        width=Decimal("40"),
        height=Decimal("30"),
    )
    # 60 000 см³ / 5 000 = 12 кг; (2 + 3×12) × 2 единицы.
    costs = calculate_item_shipping_costs_usd(item, 2, None, None, globals_())
    assert costs["air"] == Decimal("76")


def test_weight_mode_falls_back_to_base_when_measurements_are_missing():
    rule = category("weight", sea_shipping_cost_usd=Decimal("8"), sea_shipping_rate_per_kg_usd=Decimal("20"))
    costs = calculate_item_shipping_costs_usd(product(rule), 2, None, None, globals_())
    assert costs["sea"] == Decimal("16")


def test_volume_mode_converts_metres_to_cubic_metres():
    rule = category("volume", ground_shipping_cost_usd=Decimal("10"), ground_shipping_rate_per_m3_usd=Decimal("50"))
    item = product(rule, length=Decimal("2"), width=Decimal("1"), height=Decimal("0.5"), dimensions_unit="m")
    costs = calculate_item_shipping_costs_usd(item, 1, None, None, globals_())
    assert costs["ground"] == Decimal("60")


def test_quote_and_free_shipping_flags_follow_inherited_rule():
    rule = category("quote", free_shipping_eligible=False)
    child = category("inherit", parent=rule)
    item = product(child, product_type="medicines")
    assert product_shipping_requires_quote(item) is True
    assert product_is_free_shipping_eligible(item) is False


def test_furniture_stays_quote_by_default_but_explicit_category_can_enable_calculation():
    assert product_shipping_requires_quote(product(product_type="furniture")) is True
    assert product_shipping_requires_quote(product(category("volume"), product_type="furniture")) is False


def test_cart_subtotal_is_sum_of_the_same_public_prices_as_cart_lines(monkeypatch):
    items = [obj(quantity=1, price=Decimal("11.74")), obj(quantity=2, price=Decimal("1"))]
    cart = obj(items=obj(all=lambda: items))
    public_prices = iter((Decimal("13.50"), Decimal("2.25")))
    monkeypatch.setattr(CartItemSerializer, "get_price", lambda self, item: next(public_prices))

    assert CartSerializer().get_total_amount(cart) == 18.0
