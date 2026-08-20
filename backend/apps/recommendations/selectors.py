"""Canonical publication policy for products exposed by recommendations."""

from __future__ import annotations


def public_recommendation_products():
    """Return products eligible for every public recommendation surface.

    Recommendation candidates have historically been limited to available
    products by the Qdrant payload filter.  Enforce the same rule against the
    authoritative database and additionally require the catalog publication
    flag, so stale vector payloads cannot republish a withdrawn product.
    """
    from apps.catalog.models import Product

    return Product.objects.filter(is_active=True, is_available=True)


def is_public_recommendation_product(product) -> bool:
    """In-memory equivalent used as a final guard before vector upserts."""
    return bool(
        getattr(product, "is_active", False)
        and getattr(product, "is_available", False)
    )
