"""
Расчёт доставки для корзины: каскад вариант → товар → глобальные дефолты (USD).
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from apps.catalog.currency_models import GlobalCurrencySettings, ProductPrice, ProductVariantPrice


def resolve_shipping_costs_usd(
    variant_price: Optional["ProductVariantPrice"],
    price_info: Optional["ProductPrice"],
    global_settings: "GlobalCurrencySettings",
) -> Tuple[Decimal, Decimal, Decimal]:
    """По каждому каналу: не-None на варианте, иначе не-None на товаре, иначе глобальный дефолт."""

    def one(
        variant_obj: Optional["ProductVariantPrice"],
        product_obj: Optional["ProductPrice"],
        attr: str,
        default: Decimal,
    ) -> Decimal:
        if variant_obj is not None:
            v = getattr(variant_obj, attr, None)
            if v is not None:
                return Decimal(str(v))
        if product_obj is not None:
            p = getattr(product_obj, attr, None)
            if p is not None:
                return Decimal(str(p))
        return Decimal(str(default))

    gs = global_settings
    air = one(variant_price, price_info, "air_shipping_cost", gs.default_air_shipping_usd)
    sea = one(variant_price, price_info, "sea_shipping_cost", gs.default_sea_shipping_usd)
    ground = one(variant_price, price_info, "ground_shipping_cost", gs.default_ground_shipping_usd)
    return air, sea, ground
