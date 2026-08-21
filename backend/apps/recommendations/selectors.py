"""Canonical publication policy for products exposed by recommendations."""

from __future__ import annotations

from django.db.models import Q


_VARIANT_SHADOW_Q = (
    Q(external_data__has_key="source_variant_id")
    | Q(external_data__has_key="source_variant_slug")
)
_MEDICINE_STUB_Q = (
    Q(product_type="medicines")
    & Q(external_data__has_key="is_stub")
    & Q(external_data__is_stub=True)
)


def public_recommendation_products():
    """Return products eligible for every public recommendation surface.

    Keep this policy aligned with the public ProductViewSet: recommendation
    cards must always resolve to a real public detail page.  In addition to
    active/available flags, exclude legacy per-variant shadow rows and medicine
    stubs that exist only to link analogs in the admin.
    """
    from apps.catalog.models import Product

    return (
        Product.objects.filter(is_active=True, is_available=True)
        .exclude(_VARIANT_SHADOW_Q)
        .exclude(_MEDICINE_STUB_Q)
    )


def is_public_recommendation_product(product) -> bool:
    """In-memory equivalent used as a final guard before vector upserts."""
    external_data = getattr(product, "external_data", None)
    external_data = external_data if isinstance(external_data, dict) else {}
    product_type = str(getattr(product, "product_type", "") or "").strip().lower()

    return bool(
        getattr(product, "is_active", False)
        and getattr(product, "is_available", False)
        and "source_variant_id" not in external_data
        and "source_variant_slug" not in external_data
        and not (
            product_type.replace("-", "_") == "medicines"
            and external_data.get("is_stub") is True
        )
    )
