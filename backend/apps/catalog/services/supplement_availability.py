"""Sale capability boundary for supplement products.

IlacFiyati supplies a reference retail price but no warehouse or shop inventory.
This module never performs network I/O and never treats catalog defaults as stock.
It only exposes whether a separate, explicitly enabled ProductSourceOffer adapter is
available; the actual check still happens in cart and checkout preflight.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from apps.catalog.models import ProductSourceOffer, SupplementProduct
from apps.catalog.services.source_offer_verification import SourceOfferVerificationService

REFERENCE_PRICE_ONLY_SOURCES = frozenset({"ilacfiyati"})


@dataclass(frozen=True)
class SupplementSaleCapability:
    purchase_mode: str
    can_add_to_cart: bool
    availability_verification: str


class SupplementAvailabilityService:
    """Resolve stock-adapter capability without contacting a supplier."""

    def __init__(self, verifier: SourceOfferVerificationService | None = None):
        self.verifier = verifier or SourceOfferVerificationService()

    @staticmethod
    def _configured_sources() -> set[str]:
        return {
            str(value or "").strip().casefold()
            for value in getattr(settings, "SUPPLEMENT_STOCK_ADAPTER_SOURCES", [])
            if str(value or "").strip()
        } - REFERENCE_PRICE_ONLY_SOURCES

    @staticmethod
    def _active_offers(supplement: SupplementProduct) -> list[ProductSourceOffer]:
        base_product = supplement.base_product
        if base_product is None:
            return []
        prefetched = getattr(base_product, "_prefetched_objects_cache", {}).get("source_offers")
        if prefetched is not None:
            return [offer for offer in prefetched if offer.is_active]
        return list(base_product.source_offers.filter(is_active=True))

    def capability(self, supplement: SupplementProduct) -> SupplementSaleCapability:
        if not bool(getattr(settings, "SOURCE_OFFER_CART_ENFORCEMENT_ENABLED", False)):
            return SupplementSaleCapability(
                purchase_mode="catalog_sale",
                can_add_to_cart=True,
                availability_verification="catalog",
            )

        allowed_sources = self._configured_sources()
        if allowed_sources:
            for offer in self._active_offers(supplement):
                parser_key = str(offer.parser_key or "").strip().casefold()
                if parser_key in allowed_sources and self.verifier.supports_offer(offer):
                    return SupplementSaleCapability(
                        purchase_mode="verified_sale",
                        can_add_to_cart=True,
                        availability_verification="live_on_cart",
                    )

        return SupplementSaleCapability(
            purchase_mode="pending_confirmation",
            can_add_to_cart=True,
            availability_verification="manual_before_payment",
        )
