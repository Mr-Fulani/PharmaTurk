"""Immutable cart and supplier snapshots consumed by checkout."""

from __future__ import annotations

import hashlib
import json

from django.conf import settings

from .cart_source_verification import CartSourceOfferPolicy
from .models import Cart, CartItem


def checkout_cart_fingerprint(cart: Cart, items: list[CartItem]) -> str:
    """Return a stable fingerprint for every value consumed by checkout.

    Supplier identity is included for audit safety, while observed price and
    stock remain owned by ``CartItem``. Datetimes and decimals are serialized
    as strings so the digest is deterministic across unlocked and locked reads.
    """

    item_payload = []
    for item in sorted(items, key=lambda candidate: candidate.pk):
        offer = item.source_offer if item.source_offer_id else None
        item_payload.append(
            {
                "id": item.pk,
                "product_id": item.product_id,
                "chosen_size": item.chosen_size,
                "quantity": item.quantity,
                "price": str(item.price),
                "currency": item.currency,
                "source_offer_id": item.source_offer_id,
                "verification_status": item.verification_status,
                "source_checked_at": (
                    item.source_checked_at.isoformat()
                    if item.source_checked_at
                    else None
                ),
                "source_availability_status": item.source_availability_status,
                "observed_source_price": (
                    str(item.observed_source_price)
                    if item.observed_source_price is not None
                    else None
                ),
                "observed_source_currency": item.observed_source_currency,
                "observed_public_price": (
                    str(item.observed_public_price)
                    if item.observed_public_price is not None
                    else None
                ),
                "observed_public_currency": item.observed_public_currency,
                "observed_stock_precision": item.observed_stock_precision,
                "observed_stock_quantity": item.observed_stock_quantity,
                "verified_quantity": item.verified_quantity,
                "verification_issues": item.verification_issues,
                "price_change_state": item.price_change_state,
                "price_acknowledged_at": (
                    item.price_acknowledged_at.isoformat()
                    if item.price_acknowledged_at
                    else None
                ),
                "price_acknowledged_value": (
                    str(item.price_acknowledged_value)
                    if item.price_acknowledged_value is not None
                    else None
                ),
                "price_acknowledged_currency": (
                    item.price_acknowledged_currency
                ),
                "updated_at": item.updated_at.isoformat(),
                "offer_identity": (
                    {
                        "parser_key": offer.parser_key,
                        "canonical_url": offer.canonical_url,
                        "external_product_id": offer.external_product_id,
                        "external_sku": offer.external_sku,
                        "variant_key": offer.variant_key,
                        "size_key": offer.size_key,
                        "selected_options": offer.selected_options,
                        "updated_at": offer.updated_at.isoformat(),
                    }
                    if offer is not None
                    else None
                ),
            }
        )
    payload = {
        "cart_id": cart.pk,
        "currency": cart.currency,
        "promo_code_id": cart.promo_code_id,
        "updated_at": cart.updated_at.isoformat(),
        "items": item_payload,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def order_item_source_snapshot(item: CartItem) -> dict:
    """Copy server-owned supplier identity and observation to an order line."""

    offer = item.source_offer if item.source_offer_id else None
    if offer is None:
        return {
            # Supplements remain payable without a stock adapter by explicit
            # policy. Keep the fulfilment exception visible to administrators.
            "supplier_confirmation_required": (
                CartSourceOfferPolicy.availability_is_informational(
                    item.product
                )
            ),
        }
    selected_options = dict(offer.selected_options or {})
    if offer.parser_key == "akakce" and isinstance(
        offer.response_metadata,
        dict,
    ):
        metadata = offer.response_metadata
        seller_name = str(metadata.get("seller_name") or "").strip()
        seller_url = str(metadata.get("seller_url") or "").strip()
        if seller_name and seller_url:
            # Retain the exact procurement seller selected by the live cart
            # observation in the existing immutable JSON snapshot.
            selected_options["procurement_offer"] = {
                "seller_name": seller_name[:200],
                "seller_url": seller_url[:2000],
                "market_product_name": str(
                    metadata.get("market_product_name") or ""
                )[:500],
                "market_product_id": str(
                    metadata.get("market_product_id") or ""
                )[:100],
            }
    reservation_capable = {
        str(source).strip().casefold()
        for source in getattr(
            settings,
            "SOURCE_OFFER_RESERVATION_CAPABLE_SOURCES",
            [],
        )
        if str(source).strip()
    }
    return {
        "source_parser": offer.parser_key,
        "source_domain": offer.source_domain,
        "source_url": offer.canonical_url,
        "source_external_product_id": offer.external_product_id,
        "source_external_sku": offer.external_sku,
        "source_variant_key": offer.variant_key,
        "source_size_key": offer.size_key,
        "source_selected_options": selected_options,
        "source_price": (
            item.observed_source_price
            if item.observed_source_price is not None
            else offer.source_price
        ),
        "source_currency": (
            item.observed_source_currency or offer.source_currency
        ),
        "source_availability_status": (
            item.source_availability_status or offer.availability_status
        ),
        "source_stock_precision": (
            item.observed_stock_precision or offer.stock_precision
        ),
        "source_stock_quantity": item.observed_stock_quantity,
        "source_checked_at": item.source_checked_at,
        "supplier_confirmation_required": (
            CartSourceOfferPolicy.availability_is_informational(item.product)
            or offer.parser_key not in reservation_capable
        ),
    }
