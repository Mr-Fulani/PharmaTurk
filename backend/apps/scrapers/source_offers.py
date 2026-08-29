"""Idempotent dual-write from full scraper results to ProductSourceOffer.

This module records observations only. It never changes Product price/stock and is
not used by cart/checkout readers until the later verification phases are enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product, ProductSourceOffer
from apps.scrapers.base.scraper import ScrapedProduct

# These parsers expose availability but currently synthesize a numeric stock value.
# Only IKEA's normalized positive stock comes from an actual supplier quantity.
EXACT_STOCK_SOURCES = frozenset({"ikea"})
# These sources publish reference/catalog information, not supplier availability.
# ScrapedProduct defaults from them must never become a buyable stock observation.
REFERENCE_PRICE_ONLY_SOURCES = frozenset({"ilacfiyati"})


@dataclass(frozen=True)
class SourceOfferSnapshot:
    canonical_url: str
    external_product_id: str
    external_sku: str
    variant_key: str
    size_key: str
    selected_options: dict[str, Any]
    source_price: Decimal | None
    source_currency: str
    availability_status: str
    stock_precision: str
    stock_quantity: int | None
    response_metadata: dict[str, Any]


def _clean(value: Any, max_length: int) -> str:
    return str(value or "").strip()[:max_length]


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount.quantize(Decimal("0.01"))


def _trusted_http_url(*values: Any) -> str:
    for value in values:
        candidate = _clean(value, 2000)
        if not candidate:
            continue
        parsed = urlparse(candidate)
        if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
            return candidate
    return ""


def _stock_observation(
    *,
    parser_key: str,
    is_available: Any,
    raw_quantity: Any,
) -> tuple[str, str, int | None]:
    if parser_key in REFERENCE_PRICE_ONLY_SOURCES:
        return (
            ProductSourceOffer.AvailabilityStatus.UNKNOWN,
            ProductSourceOffer.StockPrecision.UNKNOWN,
            None,
        )

    available = bool(is_available)
    if parser_key in EXACT_STOCK_SOURCES and raw_quantity is not None:
        try:
            quantity = max(int(raw_quantity), 0)
        except (TypeError, ValueError):
            quantity = None
        if quantity is not None:
            status = (
                ProductSourceOffer.AvailabilityStatus.IN_STOCK
                if quantity > 0
                else ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK
            )
            return status, ProductSourceOffer.StockPrecision.EXACT, quantity

    status = (
        ProductSourceOffer.AvailabilityStatus.IN_STOCK
        if available
        else ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK
    )
    return status, ProductSourceOffer.StockPrecision.BOOLEAN, None


def _snapshot(
    *,
    parser_key: str,
    scraped_product: ScrapedProduct,
    row: dict[str, Any],
    variant_key: str = "",
    size_row: dict[str, Any] | None = None,
) -> SourceOfferSnapshot | None:
    size_row = size_row or {}
    canonical_url = _trusted_http_url(
        row.get("external_url"),
        scraped_product.url,
    )
    if not canonical_url:
        return None

    size_key = _clean(size_row.get("size"), 100)
    variant_key = _clean(variant_key, 500)
    external_sku = _clean(
        size_row.get("sku") or row.get("sku") or scraped_product.sku,
        500,
    )
    available = size_row.get("is_available") if size_row else row.get("is_available")
    if available is None:
        available = scraped_product.is_available
    raw_quantity = size_row.get("stock_quantity") if size_row else row.get("stock_quantity")
    if raw_quantity is None and not variant_key:
        raw_quantity = scraped_product.stock_quantity

    availability, precision, quantity = _stock_observation(
        parser_key=parser_key,
        is_available=available,
        raw_quantity=raw_quantity,
    )
    color = _clean(row.get("color"), 100)
    options = {}
    if color:
        options["color"] = color
    if size_key:
        options["size"] = size_key

    raw_availability = size_row.get("availability") or row.get("availability") or ""
    metadata = {"recorded_from": "full_scrape"}
    if parser_key in REFERENCE_PRICE_ONLY_SOURCES:
        metadata.update(
            {
                "availability_evidence": "none",
                "reference_price_only": True,
            }
        )
    if raw_availability:
        metadata["raw_availability"] = _clean(raw_availability, 100)

    return SourceOfferSnapshot(
        canonical_url=canonical_url,
        external_product_id=_clean(scraped_product.external_id, 500),
        external_sku=external_sku,
        variant_key=variant_key,
        size_key=size_key,
        selected_options=options,
        source_price=_decimal(
            row.get("price") if row.get("price") is not None else scraped_product.price
        ),
        source_currency=_clean(
            row.get("currency") or scraped_product.currency,
            10,
        ).upper(),
        availability_status=availability,
        stock_precision=precision,
        stock_quantity=quantity,
        response_metadata=metadata,
    )


def build_source_offer_snapshots(
    scraped_product: ScrapedProduct,
    *,
    parser_key: str | None = None,
) -> list[SourceOfferSnapshot]:
    """Build one snapshot per buyable variant/size without trusting fake quantities."""
    source = _clean(parser_key or scraped_product.source, 100).casefold()
    if not source:
        return []

    attributes = scraped_product.attributes if isinstance(scraped_product.attributes, dict) else {}
    raw_variants = attributes.get("fashion_variants") or attributes.get("furniture_variants")
    snapshots: list[SourceOfferSnapshot] = []

    if isinstance(raw_variants, list) and raw_variants:
        for raw_variant in raw_variants:
            if not isinstance(raw_variant, dict):
                continue
            variant_key = _clean(raw_variant.get("external_id"), 500)
            sizes = raw_variant.get("sizes")
            if isinstance(sizes, list) and sizes:
                for raw_size in sizes:
                    if not isinstance(raw_size, dict):
                        continue
                    snapshot = _snapshot(
                        parser_key=source,
                        scraped_product=scraped_product,
                        row=raw_variant,
                        variant_key=variant_key,
                        size_row=raw_size,
                    )
                    if snapshot is not None:
                        snapshots.append(snapshot)
                continue

            snapshot = _snapshot(
                parser_key=source,
                scraped_product=scraped_product,
                row=raw_variant,
                variant_key=variant_key,
            )
            if snapshot is not None:
                snapshots.append(snapshot)
    else:
        snapshot = _snapshot(
            parser_key=source,
            scraped_product=scraped_product,
            row={
                "external_url": scraped_product.url,
                "sku": scraped_product.sku,
                "price": scraped_product.price,
                "currency": scraped_product.currency,
                "is_available": scraped_product.is_available,
                "stock_quantity": scraped_product.stock_quantity,
            },
        )
        if snapshot is not None:
            snapshots.append(snapshot)

    # Malformed parser payloads must not create duplicate DB writes in one run.
    unique: dict[tuple[str, str, str, str], SourceOfferSnapshot] = {}
    for snapshot in snapshots:
        identity = (
            snapshot.external_sku or snapshot.external_product_id or snapshot.canonical_url,
            snapshot.variant_key,
            snapshot.size_key,
            snapshot.canonical_url,
        )
        unique[identity] = snapshot
    return list(unique.values())


def source_offer_priority(parser_key: str) -> int:
    priorities = getattr(settings, "SOURCE_OFFER_SOURCE_PRIORITIES", {}) or {}
    raw = priorities.get(parser_key, getattr(settings, "SOURCE_OFFER_DEFAULT_PRIORITY", 100))
    try:
        return max(0, min(int(raw), 32767))
    except (TypeError, ValueError):
        return 100


@transaction.atomic
def record_scraped_product_offers(
    *,
    product: Product,
    scraped_product: ScrapedProduct,
    scraper_config: Any = None,
    deactivate_missing: bool = True,
    skip_variant_summaries_with_saved_sizes: bool = False,
) -> list[ProductSourceOffer]:
    """Upsert observations from one complete supplier-product response.

    Catalogue crawls keep the historical ``deactivate_missing=True`` behaviour.
    Demand-driven card refreshes pass ``False``: a single partial/defensive source
    response may reactivate and update observed options, but may never make an
    unobserved colour or size disappear from the public card.
    """
    parser_key = _clean(
        scraped_product.source or getattr(scraper_config, "parser_class", ""),
        100,
    ).casefold()
    snapshots = build_source_offer_snapshots(scraped_product, parser_key=parser_key)
    if not parser_key or not snapshots:
        return []

    if skip_variant_summaries_with_saved_sizes:
        # A defensive/partial fashion response may expose a colour but omit its
        # size selector.  When size-level offers already exist, persisting that
        # response as a new ``size_key=''`` offer creates a second identity for
        # the same variant and cannot safely update any particular size.  Keep
        # the snapshot available to the card reconciler, but do not add a
        # summary offer; cart verification will continue to check the selected
        # saved size directly.
        saved_sized_variant_keys = set(
            ProductSourceOffer.objects.filter(
                product=product,
                parser_key=parser_key,
                is_active=True,
            )
            .exclude(size_key="")
            .values_list("variant_key", flat=True)
        )
        snapshots = [
            snapshot
            for snapshot in snapshots
            if snapshot.size_key
            or not snapshot.variant_key
            or snapshot.variant_key not in saved_sized_variant_keys
        ]
        if not snapshots:
            return []

    observed_at = timezone.now()
    parser_config_payload = {}
    if scraper_config is not None:
        if getattr(scraper_config, "pk", None):
            parser_config_payload["scraper_config_id"] = scraper_config.pk
        if getattr(scraper_config, "parser_class", None):
            parser_config_payload["parser_class"] = _clean(scraper_config.parser_class, 255)

    saved: list[ProductSourceOffer] = []
    seen_offer_keys: set[str] = set()
    priority = source_offer_priority(parser_key)
    for snapshot in snapshots:
        offer_key = ProductSourceOffer.build_offer_key(
            parser_key=parser_key,
            canonical_url=snapshot.canonical_url,
            external_product_id=snapshot.external_product_id,
            external_sku=snapshot.external_sku,
            variant_key=snapshot.variant_key,
            size_key=snapshot.size_key,
        )
        defaults = {
            "parser_config": parser_config_payload,
            "canonical_url": snapshot.canonical_url,
            "external_product_id": snapshot.external_product_id,
            "external_sku": snapshot.external_sku,
            "variant_key": snapshot.variant_key,
            "size_key": snapshot.size_key,
            "selected_options": snapshot.selected_options,
            "source_price": snapshot.source_price,
            "source_currency": snapshot.source_currency,
            "availability_status": snapshot.availability_status,
            "stock_precision": snapshot.stock_precision,
            "stock_quantity": snapshot.stock_quantity,
            "priority": priority,
            "is_active": True,
            "last_checked_at": observed_at,
            "last_successful_check_at": observed_at,
            "last_error_code": "",
            "last_error_message": "",
            "consecutive_failures": 0,
            "response_metadata": snapshot.response_metadata,
        }
        locked_offers = ProductSourceOffer.objects.select_for_update().filter(
            product=product,
            parser_key=parser_key,
        )
        offer = locked_offers.filter(offer_key=offer_key).first()
        if offer is None:
            # Some product APIs omit a size SKU on later responses or replace it
            # while keeping the same buyable option.  Reuse the one unambiguous
            # semantic row so an old OOS offer cannot coexist with a new in-stock
            # offer for the same colour/size.  Multiple matches are deliberately
            # left separate because marketplace sellers may share option labels.
            semantic_matches = list(
                locked_offers.filter(
                    canonical_url=snapshot.canonical_url,
                    external_product_id=snapshot.external_product_id,
                    variant_key=snapshot.variant_key,
                    size_key=snapshot.size_key,
                ).order_by("id")[:2]
            )
            if len(semantic_matches) == 1:
                offer = semantic_matches[0]

            # LCW derives its parent product id from the lowest colour id that
            # is linked at the moment.  That id changes when a colour vanishes,
            # while the concrete variant URL/key/size remain stable.  Reuse the
            # one unambiguous option row so a legitimate group-id drift does
            # not create a parallel set of offers.  Keep this exception narrow:
            # marketplace sources may need external_product_id to distinguish
            # sellers sharing the same option labels.
            if offer is None and parser_key == "lcw":
                lcw_matches = list(
                    locked_offers.filter(
                        canonical_url=snapshot.canonical_url,
                        variant_key=snapshot.variant_key,
                        size_key=snapshot.size_key,
                    ).order_by("id")[:2]
                )
                if len(lcw_matches) == 1:
                    offer = lcw_matches[0]

        if offer is None:
            offer, _ = ProductSourceOffer.objects.update_or_create(
                product=product,
                parser_key=parser_key,
                offer_key=offer_key,
                defaults=defaults,
            )
        else:
            for field, value in defaults.items():
                setattr(offer, field, value)
            # Keep the persisted key stable when only a supplier SKU drifted.
            offer.save()
        saved.append(offer)
        seen_offer_keys.add(offer.offer_key)

    external_product_id = _clean(scraped_product.external_id, 500)
    if deactivate_missing and external_product_id:
        (
            ProductSourceOffer.objects.filter(
                product=product,
                parser_key=parser_key,
                external_product_id=external_product_id,
                is_active=True,
            )
            .exclude(offer_key__in=seen_offer_keys)
            .update(is_active=False)
        )

    return saved
