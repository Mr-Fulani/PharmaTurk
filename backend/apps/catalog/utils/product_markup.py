from decimal import Decimal, ROUND_HALF_UP


def get_effective_product_markup(product):
    """Возвращает (процент, источник) с приоритетом бренд → категория."""
    brand = getattr(product, "brand", None)
    brand_margin = getattr(brand, "margin_percent", None) if brand else None
    if brand_margin is not None and Decimal(str(brand_margin)) > 0:
        return Decimal(str(brand_margin)), "brand"

    category = getattr(product, "category", None)
    category_margin = getattr(category, "margin_percent", None) if category else None
    if category_margin is not None and Decimal(str(category_margin)) > 0:
        return Decimal(str(category_margin)), "category"
    return Decimal("0"), None


def apply_product_markup(amount, product):
    """Накладывает товарную наценку поверх уже рассчитанной публичной цены."""
    if amount is None:
        return None
    margin, _ = get_effective_product_markup(product)
    value = Decimal(str(amount))
    if margin <= 0:
        return value
    return (value * (Decimal("1") + margin / Decimal("100"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
