"""Read-only projection of fresh supplier availability into public catalog output."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.catalog.models import Product, ProductSourceOffer
from apps.catalog.services.source_offer_verification import manual_only_source_keys


@dataclass(frozen=True)
class CatalogAvailabilityProjection:
    availability_status: str
    is_available: bool


def _stale_seconds() -> int:
    try:
        value = int(getattr(settings, "SOURCE_OFFER_BACKGROUND_STALE_SECONDS", 900))
    except (TypeError, ValueError):
        value = 900
    return max(60, min(value, 86400))


def _enabled_sources() -> set[str]:
    return {
        str(value or "").strip().casefold()
        for value in (getattr(settings, "SOURCE_OFFER_VERIFICATION_SOURCES", []) or [])
        if str(value or "").strip()
    }


def _source_product(product_like, *, allow_queries: bool) -> Product | None:
    if isinstance(product_like, Product):
        product = product_like
    else:
        product = getattr(product_like, "base_product", None)
    if not isinstance(product, Product):
        return None

    external = product.external_data if isinstance(product.external_data, dict) else {}
    raw_source_product_id = external.get("source_offer_product_id")
    if raw_source_product_id in (None, "", product.pk):
        return product
    try:
        source_product_id = int(raw_source_product_id)
    except (TypeError, ValueError):
        return product
    if not allow_queries:
        return None
    return Product.objects.filter(pk=source_product_id).first()


def _active_offers(
    product: Product,
    *,
    allow_queries: bool,
) -> list[ProductSourceOffer]:
    prefetched = getattr(product, "_prefetched_objects_cache", {}).get("source_offers")
    if prefetched is None:
        if not allow_queries:
            return []
        offers = list(product.source_offers.filter(is_active=True))
    else:
        offers = [offer for offer in prefetched if offer.is_active]
    manual_only = manual_only_source_keys()
    offers = [offer for offer in offers if offer.parser_key.casefold() not in manual_only]
    allowed = _enabled_sources()
    if allowed:
        offers = [offer for offer in offers if offer.parser_key.casefold() in allowed]
    return offers


def resolve_source_offer_catalog_availability(
    product_like,
    *,
    now=None,
    allow_queries: bool = True,
) -> CatalogAvailabilityProjection | None:
    """Return a conservative product-level projection from fresh offer rows.

    One fresh sellable offer is enough to mark a product available. Marking it
    unavailable requires every enabled active offer to have a fresh, conclusive
    out-of-stock/discontinued result. Transient supplier failures therefore never
    hide a product from the storefront.
    """

    if not bool(getattr(settings, "SOURCE_OFFER_CATALOG_PROJECTION_ENABLED", False)):
        return None
    if not bool(getattr(settings, "SOURCE_OFFER_VERIFICATION_ENABLED", False)):
        return None

    product = _source_product(product_like, allow_queries=allow_queries)
    if product is None:
        return None
    offers = _active_offers(product, allow_queries=allow_queries)
    if not offers:
        return None

    cutoff = (now or timezone.now()) - timedelta(seconds=_stale_seconds())
    fresh = [
        offer
        for offer in offers
        if offer.last_checked_at is not None and offer.last_checked_at >= cutoff
    ]
    sellable = {
        ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        ProductSourceOffer.AvailabilityStatus.LIMITED,
    }
    unavailable = {
        ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK,
        ProductSourceOffer.AvailabilityStatus.DISCONTINUED,
    }

    if any(offer.availability_status in sellable for offer in fresh):
        return CatalogAvailabilityProjection(
            availability_status="in_stock",
            is_available=True,
        )

    # Stale, unknown, unsupported or unreachable options prevent a destructive
    # unavailable projection; checkout remains the authoritative final gate.
    if len(fresh) != len(offers) or any(
        offer.availability_status not in unavailable for offer in fresh
    ):
        return None

    status = (
        "discontinued"
        if all(
            offer.availability_status == ProductSourceOffer.AvailabilityStatus.DISCONTINUED
            for offer in fresh
        )
        else "out_of_stock"
    )
    return CatalogAvailabilityProjection(
        availability_status=status,
        is_available=False,
    )


def apply_source_offer_catalog_projection(data: dict, instance, context) -> dict:
    """Apply projection only to detail responses, never to list serialization."""

    view = context.get("view") if isinstance(context, dict) else None
    explicitly_enabled = bool(
        isinstance(context, dict) and context.get("source_offer_catalog_projection")
    )
    if not explicitly_enabled and getattr(view, "action", None) != "retrieve":
        return data

    projection = resolve_source_offer_catalog_availability(instance)
    if projection is not None:
        # Supplier availability may further restrict the storefront, but it must
        # never undo a manual/merchandising is_available=False decision.
        if projection.is_available and data.get("is_available") is False:
            return data
        data["availability_status"] = projection.availability_status
        data["is_available"] = projection.is_available
    return data
