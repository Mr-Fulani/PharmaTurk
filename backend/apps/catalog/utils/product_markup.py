from decimal import Decimal, ROUND_HALF_UP
import logging

from django.core.exceptions import ObjectDoesNotExist


logger = logging.getLogger(__name__)


def get_category_markup(category):
    """Nearest positive category/ancestor markup, or None when unspecified.

    Zero retains its existing meaning: inherit/fall back, not an explicit
    zero-price-markup override. Django's relation cache is reused within a
    response; no process-wide cache can hide later administrator changes.
    """
    visited = set()
    while category is not None:
        pk = getattr(category, "pk", None)
        identity = ("pk", pk) if pk is not None else ("object", id(category))
        if identity in visited:
            logger.warning("Category markup hierarchy contains a cycle at category %s", pk)
            return None
        visited.add(identity)
        margin = getattr(category, "margin_percent", None)
        if margin is not None and Decimal(str(margin)) > 0:
            return Decimal(str(margin))
        try:
            category = getattr(category, "parent", None)
        except ObjectDoesNotExist:
            logger.warning("Category markup parent no longer exists for category %s", pk)
            return None
    return None


def get_effective_product_markup(product):
    """Бренд → категория → ближайший заданный предок → глобальная наценка."""
    brand = getattr(product, "brand", None)
    brand_margin = getattr(brand, "margin_percent", None) if brand else None
    if brand_margin is not None and Decimal(str(brand_margin)) > 0:
        return Decimal(str(brand_margin)), "brand"

    category_margin = get_category_markup(getattr(product, "category", None))
    if category_margin is not None:
        # Preserve the public API's existing source vocabulary.
        return category_margin, "category"

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
