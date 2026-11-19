from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import logging

from django.core.exceptions import ObjectDoesNotExist


from .markup_scale import apply_scale


logger = logging.getLogger(__name__)

# «Цена источника не передана» — берётся цена самого товара.
PRODUCT_PRICE = object()


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


def _price_in_try(price, currency):
    """Цена источника в лирах для выбора ступени; None — если перевести нельзя."""
    if price is None:
        return None
    try:
        amount = Decimal(str(price))
        currency = (currency or "").upper()
        if amount <= 0 or not currency:
            return None
        if currency == "TRY":
            return amount
        from .currency_converter import currency_converter

        _original, converted, _with_margin = currency_converter.convert_price(
            amount, currency, "TRY", apply_margin=False
        )
        return Decimal(str(converted))
    except Exception:
        logger.warning("Markup scale: %s %s is not convertible to TRY", price, currency)
        return None


@dataclass(frozen=True)
class MarkupResult:
    percent: Decimal
    source: str | None  # brand / category / global
    scale_name: str = ""
    scale: object = None  # ScaleResult, если сработала шкала


@dataclass(frozen=True)
class MarkupRule:
    """Правило наценки товара: считается один раз, применяется к любой цене источника."""

    percent: Decimal  # фиксированный процент — действует без шкалы и когда шкала неприменима
    source: str | None
    scale_source: str | None = None
    scale_name: str = ""
    steps: tuple = ()

    def resolve(self, base_price, base_currency):
        if self.steps:
            scale = apply_scale(self.steps, _price_in_try(base_price, base_currency))
            if scale is not None:
                return MarkupResult(scale.percent, self.scale_source, self.scale_name, scale)
        return MarkupResult(self.percent, self.source)


def _product_kind(product):
    return (
        getattr(product, "product_type", None)
        or getattr(product, "_domain_product_type", None)
        or type(product).__name__.lower()
    )


def resolve_markup_rule(product):
    """Бренд → категория → ближайший заданный предок → глобальная настройка.

    На уровне категории и в глобальной настройке вместо процента может стоять шкала.
    Услуги под шкалу не идут; лекарства не идут под глобальную шкалу — только под ту,
    что выбрана у их категории. Фиксированный процент находится всегда: он действует,
    когда шкала неприменима (нет цены источника или курса к лире).
    """
    brand = getattr(product, "brand", None)
    brand_margin = getattr(brand, "margin_percent", None) if brand else None
    if brand_margin is not None and Decimal(str(brand_margin)) > 0:
        return MarkupRule(Decimal(str(brand_margin)), "brand")

    kind = _product_kind(product)
    scales_allowed = kind not in ("service", "services") and type(product).__name__ != "Service"
    scale_id = scale_source = None

    category = getattr(product, "category", None)
    visited = set()
    while category is not None:
        pk = getattr(category, "pk", None)
        identity = ("pk", pk) if pk is not None else ("object", id(category))
        if identity in visited:
            logger.warning("Category markup hierarchy contains a cycle at category %s", pk)
            break
        visited.add(identity)
        if scales_allowed and scale_id is None and getattr(category, "markup_scale_id", None):
            scale_id, scale_source = category.markup_scale_id, "category"
        margin = getattr(category, "margin_percent", None)
        if margin is not None and Decimal(str(margin)) > 0:
            # Preserve the public API's existing source vocabulary.
            return _with_scale(Decimal(str(margin)), "category", scale_id, scale_source)
        try:
            category = getattr(category, "parent", None)
        except ObjectDoesNotExist:
            logger.warning("Category markup parent no longer exists for category %s", pk)
            break

    from apps.catalog.currency_models import GlobalCurrencySettings

    settings = GlobalCurrencySettings.load()
    if scales_allowed and scale_id is None and kind not in ("medicines", "medicineproduct"):
        global_scale = getattr(settings, "markup_scale_id", None)
        if global_scale:
            scale_id, scale_source = global_scale, "global"
    global_margin = Decimal(str(settings.default_margin_percentage))
    if global_margin > 0:
        return _with_scale(global_margin, "global", scale_id, scale_source)
    return _with_scale(Decimal("0"), None, scale_id, scale_source)


def _with_scale(percent, source, scale_id, scale_source):
    if scale_id:
        from apps.catalog.currency_models import load_markup_scales

        scale = load_markup_scales().get(scale_id)
        if scale and scale[1]:
            return MarkupRule(percent, source, scale_source, scale[0], scale[1])
    return MarkupRule(percent, source)


def explain_product_markup(product, base_price=PRODUCT_PRICE, base_currency=None):
    """Наценка с подробностями. base_price — цена источника, от которой выбирается ступень
    шкалы: число (валюта — base_currency или валюта товара) либо функция, возвращающая
    (цена, валюта); она вызывается, только если у товара действует шкала."""
    rule = resolve_markup_rule(product)
    if not rule.steps:
        return MarkupResult(rule.percent, rule.source)
    if base_price is PRODUCT_PRICE:
        base_price, base_currency = getattr(product, "price", None), None
    elif callable(base_price):
        base_price, base_currency = base_price()
    return rule.resolve(base_price, base_currency or getattr(product, "currency", None))


def get_effective_product_markup(product, base_price=PRODUCT_PRICE, base_currency=None):
    """Процент наценки и его уровень. base_price — цена источника (вариант, новая цена
    поставщика); без неё берётся цена самого товара. От неё зависит только шкала."""
    result = explain_product_markup(product, base_price, base_currency)
    return result.percent, result.source


def apply_product_markup(amount, product, base_price=PRODUCT_PRICE, base_currency=None):
    """Накладывает товарную наценку поверх уже рассчитанной публичной цены."""
    if amount is None:
        return None
    margin, _ = get_effective_product_markup(product, base_price, base_currency)
    return apply_markup_percent(amount, margin)


def apply_markup_percent(amount, margin):
    """Цена с наценкой margin %; без наценки — исходная сумма."""
    value = Decimal(str(amount))
    if margin <= 0:
        return value
    return (value * (Decimal("1") + margin / Decimal("100"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
