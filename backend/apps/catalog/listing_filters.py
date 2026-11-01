"""Price and availability filters for the catalog list endpoints."""

from decimal import Decimal

from django.db import models
from django.db.models import Case, F, Q, When
from django.db.models.functions import Coalesce, Least

from .models import Product


def _get_preferred_currency(request) -> str:
    preferred = None
    if request:
        preferred = request.headers.get('X-Currency') or request.query_params.get('currency')
    return (preferred or '').upper()


def _effective_selling_price_expr():
    """Эффективная цена для фильтра: при скидке (old_price > price) — цена со скидкой (min)."""
    return Case(
        When(old_price__isnull=False, old_price__gt=0, then=Least(F('price'), F('old_price'))),
        default=F('price'),
    )


def _resolve_price_filter_expression(queryset, request):
    """Выражение для фильтра по цене: итоговая цена в выбранной валюте (с маржой), fallback — эффективная базовая (со скидкой)."""
    preferred = _get_preferred_currency(request)
    if queryset.model is Product:
        effective = _effective_selling_price_expr()
        if preferred == 'USD':
            return Coalesce(F('final_price_usd'), F('price_info__usd_price_with_margin'), effective)
        if preferred == 'RUB':
            return Coalesce(F('final_price_rub'), F('price_info__rub_price_with_margin'), effective)
        if preferred == 'KZT':
            return Coalesce(F('price_info__kzt_price_with_margin'), effective)
        if preferred == 'EUR':
            return Coalesce(F('price_info__eur_price_with_margin'), effective)
        if preferred == 'TRY':
            return Coalesce(F('price_info__try_price_with_margin'), effective)
    return F('price')


def _parse_decimal(value):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return None


def apply_availability_filter(queryset, request):
    in_stock = request.query_params.get('in_stock')
    is_available = request.query_params.get('is_available')

    if in_stock is not None:
        in_stock_val = str(in_stock).lower() in ('true', '1', 'yes')
        if in_stock_val:
            if hasattr(queryset.model, 'availability_status') and hasattr(queryset.model, 'stock_quantity'):
                # Require is_available=True AND either status=in_stock OR stock_quantity > 0
                queryset = queryset.filter(is_available=True).filter(Q(availability_status='in_stock') | Q(stock_quantity__gt=0))
            else:
                queryset = queryset.filter(is_available=True)
    elif is_available is not None:
        is_avail_val = str(is_available).lower() in ('true', '1', 'yes')
        queryset = queryset.filter(is_available=is_avail_val)

    availability_status = request.query_params.get('availability_status')
    if availability_status and hasattr(queryset.model, 'availability_status'):
        queryset = queryset.filter(availability_status=availability_status)

    return queryset


def apply_price_filter(queryset, request):
    min_price_raw = request.query_params.get('min_price') or request.query_params.get('price_min')
    max_price_raw = request.query_params.get('max_price') or request.query_params.get('price_max')
    min_price = _parse_decimal(min_price_raw)
    max_price = _parse_decimal(max_price_raw)
    if not min_price and not max_price:
        return queryset
    if queryset.model is Product:
        price_expr = _resolve_price_filter_expression(queryset, request)
        queryset = queryset.annotate(_price_filter_value=price_expr)
        if min_price is not None:
            queryset = queryset.filter(_price_filter_value__gte=min_price)
        if max_price is not None:
            queryset = queryset.filter(_price_filter_value__lte=max_price)
        return queryset
    preferred = _get_preferred_currency(request)
    if not preferred or not hasattr(queryset.model, 'currency'):
        if min_price is not None:
            queryset = queryset.filter(price__gte=min_price)
        if max_price is not None:
            queryset = queryset.filter(price__lte=max_price)
        return queryset
    from .utils.currency_converter import currency_converter
    currencies = list(
        queryset.exclude(currency__isnull=True).values_list('currency', flat=True).distinct()
    )
    q = models.Q()
    for currency in currencies:
        currency_code = (currency or '').upper()
        if not currency_code:
            continue
        try:
            if currency_code == preferred:
                rate = Decimal('1')
            else:
                _, converted, _ = currency_converter.convert_price(
                    Decimal('1'), currency_code, preferred, apply_margin=False
                )
                rate = Decimal(str(converted))
            margin_rate = currency_converter._get_margin_rate(currency_code, preferred)
            margin_decimal = Decimal(str(margin_rate))
            denom = rate * (Decimal('1') + margin_decimal / Decimal('100'))
            if denom <= 0:
                continue
            sub = models.Q(currency=currency_code)
            if min_price is not None:
                sub &= models.Q(price__gte=(min_price / denom))
            if max_price is not None:
                sub &= models.Q(price__lte=(max_price / denom))
            q |= sub
        except Exception:
            continue
    if min_price is not None or max_price is not None:
        null_currency = models.Q(currency__isnull=True)
        if min_price is not None:
            null_currency &= models.Q(price__gte=min_price)
        if max_price is not None:
            null_currency &= models.Q(price__lte=max_price)
        q |= null_currency
    if q:
        return queryset.filter(q)
    return queryset
