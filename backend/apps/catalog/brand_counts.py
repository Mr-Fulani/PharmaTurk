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


def calculate_brand_product_counts():
    """Use the same visibility rules as the exact uncached brand counters."""
    products = Product.objects.filter(
        brand_id__isnull=False, is_active=True, is_available=True,
    ).exclude(non_public_shadow_product_q())
    return dict(
        products.order_by().values("brand_id")
        .annotate(total=Count("id")).values_list("brand_id", "total")
    )


def refresh_brand_product_counts():
    counts = calculate_brand_product_counts()
    # Publish only a complete successful calculation. A failed SQL query must
    # leave the previous snapshot intact.
    cache.set(CACHE_KEY, counts, timeout=CACHE_TTL_SECONDS)
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
