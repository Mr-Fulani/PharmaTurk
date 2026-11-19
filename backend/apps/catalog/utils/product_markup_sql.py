"""Товарная наценка как выражение SQL — чтобы фильтр «цена от — до» сравнивал с ценой,
которую видит покупатель. Повторяет правило apps.catalog.utils.product_markup:
бренд → категория (шкала или процент) → ближайший предок → глобальная настройка.
"""

from decimal import Decimal

from django.core.exceptions import FieldDoesNotExist
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Value, When
from django.db.models.functions import Greatest

from .markup_scale import scale_floors

FACTOR = DecimalField(max_digits=20, decimal_places=8)
HUNDRED = Decimal("100")
OTHER_CURRENCIES = ("RUB", "USD", "EUR", "KZT", "USDT")


def _has_field(model, name):
    try:
        model._meta.get_field(name)
        return True
    except FieldDoesNotExist:
        return False


def _fixed(percent):
    return Value(Decimal("1") + Decimal(str(percent)) / HUNDRED, output_field=FACTOR)


def _scale(steps, fallback_percent):
    """Множитель по шкале: max(1 + процент ступени, планка / цена в лирах)."""
    whens = []
    for start, percent, floor in reversed(scale_floors(steps)):
        factor = _fixed(percent)
        if floor > 0:
            factor = Greatest(
                factor,
                ExpressionWrapper(
                    Value(floor, output_field=FACTOR) / F("_markup_price_try"), output_field=FACTOR
                ),
            )
        if start > 0:
            whens.append(When(_markup_price_try__gte=start, then=factor))
        else:
            whens.append(When(_markup_price_try__gt=0, then=factor))
    # нет цены или курса к лире — действует процент
    return Case(*whens, default=_fixed(fallback_percent), output_field=FACTOR)


def _price_in_try():
    from .currency_converter import currency_converter

    whens = [When(currency="TRY", then=F("price"))]
    for currency in OTHER_CURRENCIES:
        try:
            _original, rate, _with_margin = currency_converter.convert_price(
                Decimal("1"), currency, "TRY", apply_margin=False
            )
        except Exception:
            continue
        whens.append(
            When(
                currency=currency,
                then=ExpressionWrapper(
                    F("price") * Value(Decimal(str(rate)), output_field=FACTOR), output_field=FACTOR
                ),
            )
        )
    return Case(*whens, default=None, output_field=FACTOR)


def _category_groups(scales, scales_allowed):
    """{(процент или None, id шкалы или None): [id категорий]} — как resolve_markup_rule."""
    from apps.catalog.models import Category

    rows = {
        pk: (parent_id, margin, scale_id)
        for pk, parent_id, margin, scale_id in Category.objects.values_list(
            "id", "parent_id", "margin_percent", "markup_scale_id"
        )
    }
    groups = {}
    for pk in rows:
        percent = scale_id = None
        node, visited = pk, set()
        while node in rows and node not in visited:
            visited.add(node)
            parent_id, margin, own_scale = rows[node]
            if scales_allowed and scale_id is None and own_scale in scales and scales[own_scale][1]:
                scale_id = own_scale
            if margin is not None and margin > 0:
                percent = margin
                break
            node = parent_id
        if percent is not None or scale_id is not None:
            groups.setdefault((percent, scale_id), []).append(pk)
    return groups


def annotate_markup_factor(queryset):
    """Добавляет `_markup_factor` — на сколько умножается цена товарной наценкой."""
    from apps.catalog.currency_models import GlobalCurrencySettings, load_markup_scales

    model = queryset.model
    settings = GlobalCurrencySettings.load()
    global_percent = Decimal(str(settings.default_margin_percentage))
    global_percent = global_percent if global_percent > 0 else Decimal("0")

    is_service = model.__name__ == "Service"
    domain_type = getattr(model, "_domain_product_type", "")
    can_scale = not is_service and _has_field(model, "price") and _has_field(model, "currency")
    has_category = _has_field(model, "category")

    scales = load_markup_scales() if can_scale else {}
    global_scale = scales.get(getattr(settings, "markup_scale_id", None)) if can_scale else None
    if global_scale and not global_scale[1]:
        global_scale = None
    groups = _category_groups(scales, can_scale) if has_category else {}
    uses_scale = bool(global_scale) or any(scale_id for _percent, scale_id in groups)
    if uses_scale:
        queryset = queryset.annotate(_markup_price_try=_price_in_try())

    whens = []
    if _has_field(model, "brand"):
        whens.append(
            When(
                brand__margin_percent__gt=0,
                then=ExpressionWrapper(
                    Value(Decimal("1"), output_field=FACTOR) + F("brand__margin_percent") / HUNDRED,
                    output_field=FACTOR,
                ),
            )
        )
    for (percent, scale_id), category_ids in groups.items():
        fallback = percent if percent is not None else global_percent
        factor = _scale(scales[scale_id][1], fallback) if scale_id else _fixed(fallback)
        whens.append(When(category_id__in=category_ids, then=factor))

    # глобальная шкала не действует на лекарства
    default = _fixed(global_percent)
    if global_scale and domain_type != "medicines":
        default = _scale(global_scale[1], global_percent)
        if _has_field(model, "product_type"):
            whens.append(When(product_type="medicines", then=_fixed(global_percent)))
    return queryset.annotate(_markup_factor=Case(*whens, default=default, output_field=FACTOR))
