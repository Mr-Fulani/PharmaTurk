from decimal import Decimal, ROUND_HALF_UP


def get_effective_product_markup(product):
    """Возвращает процент по приоритету бренд → категория → глобальная."""
    brand = getattr(product, "brand", None)
    brand_margin = getattr(brand, "margin_percent", None) if brand else None
    if brand_margin is not None and Decimal(str(brand_margin)) > 0:
        return Decimal(str(brand_margin)), "brand"

    category = getattr(product, "category", None)
    category_margin = getattr(category, "margin_percent", None) if category else None
    if category_margin is not None and Decimal(str(category_margin)) > 0:
        return Decimal(str(category_margin)), "category"

    from apps.catalog.currency_models import GlobalCurrencySettings

    global_margin = Decimal(str(GlobalCurrencySettings.load().default_margin_percentage))
    if global_margin > 0:
        return global_margin, "global"
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
