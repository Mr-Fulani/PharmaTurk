"""Shared display counters; live brand metadata is deliberately not cached."""
import logging

from django.core.cache import cache
from django.db.models import Count

from .models import Product
from .querysets import non_public_shadow_product_q

logger = logging.getLogger(__name__)
CACHE_KEY = "catalog:brand-product-counts:v1"
# Beat refreshes every minute. Keep the last good snapshot through a short
# worker outage instead of making visitors recompute it at every expiry.
CACHE_TTL_SECONDS = 15 * 60


# {product_type: {brand_id: total}} для count_scope=filtered без категорий:
# точный запрос по типу детоастит external_data всех товаров типа (бренды
# медикаментов — ~7 с), а планировщик не берёт частичный индекс.
TYPE_CACHE_KEY = "catalog:brand-type-product-counts:v1"


def _public_products():
    return Product.objects.filter(
        brand_id__isnull=False, is_active=True, is_available=True,
    ).exclude(non_public_shadow_product_q())


def calculate_brand_product_counts():
    """Use the same visibility rules as the exact uncached brand counters."""
    return dict(
        _public_products().order_by().values("brand_id")
        .annotate(total=Count("id")).values_list("brand_id", "total")
    )


def calculate_brand_type_product_counts():
    """Те же правила видимости, разбивка по типу товара — одним запросом."""
    counts = {}
    rows = (
        _public_products().order_by().values("product_type", "brand_id")
        .annotate(total=Count("id")).values_list("product_type", "brand_id", "total")
    )
    for product_type, brand_id, total in rows:
        counts.setdefault(product_type, {})[brand_id] = total
    return counts


def _sum_type_counts(type_counts):
    counts = {}
    for by_brand in type_counts.values():
        for brand_id, total in by_brand.items():
            counts[brand_id] = counts.get(brand_id, 0) + total
    return counts


def refresh_brand_product_counts():
    type_counts = calculate_brand_type_product_counts()
    counts = _sum_type_counts(type_counts)
    # Publish only a complete successful calculation. A failed SQL query must
    # leave the previous snapshot intact.
    cache.set_many(
        {CACHE_KEY: counts, TYPE_CACHE_KEY: type_counts},
        timeout=CACHE_TTL_SECONDS,
    )
    return counts


def get_brand_product_counts():
    try:
        counts = cache.get(CACHE_KEY)
    except Exception:
        logger.exception("Brand counter cache unavailable; using exact counts")
        return calculate_brand_product_counts()
    if counts is not None:
        return counts
    # Cold start/eviction: preserve correct counts and ranking. Deployment
    # prewarms this key; subsequent refreshes happen in the worker, not HTTP.
    counts = calculate_brand_product_counts()
    try:
        cache.set(CACHE_KEY, counts, timeout=CACHE_TTL_SECONDS)
    except Exception:
        logger.exception("Could not cache brand counters")
    return counts


def get_brand_type_product_counts(product_type):
    """Счётчики брендов внутри типа товара из снимка (см. TYPE_CACHE_KEY)."""
    try:
        type_counts = cache.get(TYPE_CACHE_KEY)
    except Exception:
        logger.exception("Brand counter cache unavailable; using exact counts")
        type_counts = None
    if type_counts is None:
        # Холодный старт: одна полная выборка дешевле той же выборки по каждому типу.
        type_counts = calculate_brand_type_product_counts()
        try:
            cache.set(TYPE_CACHE_KEY, type_counts, timeout=CACHE_TTL_SECONDS)
        except Exception:
            logger.exception("Could not cache brand counters")
    return type_counts.get(product_type, {})
