"""Cart policy for one saved supplier offer.

The module owns source-offer selection and interpretation for cart mutations. It
does not create or update Cart/CartItem rows and is never called by GET serializers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from django.conf import settings

from apps.catalog.models import (
    BookVariant,
    ClothingVariant,
    FurnitureVariant,
    JewelryVariant,
    Product,
    ProductSourceOffer,
    ShoeVariant,
)
from apps.catalog.utils.currency_converter import currency_converter
from apps.catalog.utils.product_markup import apply_product_markup
from apps.catalog.services.source_offer_verification import SourceOfferVerificationService
from apps.orders.models import CartItem
from apps.scrapers.base.offers import (
    OfferAvailability,
    OfferCheckError,
    OfferCheckErrorCode,
    OfferCheckResult,
    OfferStockPrecision,
)

logger = logging.getLogger(__name__)
MONEY_QUANTUM = Decimal("0.01")
REFERENCE_PRICE_ONLY_SOURCES = frozenset({"ilacfiyati"})


@dataclass(frozen=True)
class CartOfferDecision:
    offer: ProductSourceOffer | None
    result: OfferCheckResult
    verification_status: str
    issues: tuple[str, ...]
    payable: bool
    public_price: Decimal | None
    public_currency: str
    price_change_state: str
    price_acknowledged: bool = False

    @property
    def observed_stock_quantity(self) -> int | None:
        return self.result.stock_quantity

    def cart_item_values(self, *, verified_quantity: int) -> dict[str, Any]:
        """Return a persistence snapshot without mutating a CartItem."""
        return {
            "source_offer_id": self.offer.pk if self.offer is not None else None,
            "verification_status": self.verification_status,
            "source_checked_at": self.result.checked_at,
            "source_availability_status": self.result.availability_status.value,
            "observed_source_price": self.result.source_price,
            "observed_source_currency": self.result.source_currency,
            "observed_public_price": self.public_price,
            "observed_public_currency": (
                self.public_currency if self.public_price is not None else ""
            ),
            "observed_stock_precision": self.result.stock_precision.value,
            "observed_stock_quantity": self.result.stock_quantity,
            "verified_quantity": verified_quantity,
            "verification_issues": list(self.issues),
            "price_change_state": self.price_change_state,
        }


class CartSourceOfferPolicy:
    """Select and check the exact server-owned offer for a cart mutation."""

    VARIANT_MODELS = {
        "clothing": ClothingVariant,
        "shoes": ShoeVariant,
        "furniture": FurnitureVariant,
        "jewelry": JewelryVariant,
        "books": BookVariant,
    }

    def __init__(self, verifier: SourceOfferVerificationService | None = None):
        self.verifier = verifier or SourceOfferVerificationService()

    @staticmethod
    def enforcement_enabled() -> bool:
        return bool(getattr(settings, "SOURCE_OFFER_CART_ENFORCEMENT_ENABLED", False))

    @classmethod
    def requires_verified_offer(cls, product: Product) -> bool:
        if not cls.enforcement_enabled():
            return False
        required_types = {
            str(value or "").strip().casefold().replace("-", "_")
            for value in getattr(
                settings,
                "SOURCE_OFFER_CART_REQUIRED_PRODUCT_TYPES",
                ["supplements"],
            )
            if str(value or "").strip()
        }
        product_type = str(product.product_type or "").strip().casefold().replace("-", "_")
        return product_type in required_types

    @staticmethod
    def _allowed_adapter_sources(product: Product) -> set[str] | None:
        product_type = str(product.product_type or "").strip().casefold().replace("-", "_")
        if product_type != "supplements":
            return None
        return {
            str(value or "").strip().casefold()
            for value in getattr(settings, "SUPPLEMENT_STOCK_ADAPTER_SOURCES", [])
            if str(value or "").strip()
        } - REFERENCE_PRICE_ONLY_SOURCES

    @classmethod
    def _variant_key(cls, product: Product) -> tuple[str, bool]:
        external = product.external_data if isinstance(product.external_data, dict) else {}
        explicit_key = str(external.get("source_offer_variant_key") or "").strip()
        if explicit_key:
            return explicit_key, True

        raw_variant_id = external.get("source_variant_id")
        if raw_variant_id in (None, ""):
            return "", False
        model = cls.VARIANT_MODELS.get(str(product.product_type or "").casefold())
        if model is None:
            return "", True
        try:
            variant_key = (
                model.objects.filter(pk=raw_variant_id)
                .values_list("external_id", flat=True)
                .first()
            )
        except (TypeError, ValueError):
            variant_key = None
        return str(variant_key or "").strip(), True

    def select_offer(
        self,
        *,
        product: Product,
        chosen_size: str = "",
    ) -> ProductSourceOffer | None:
        """Return one exact, enabled offer without accepting client source identity."""
        if not self.enforcement_enabled():
            return None

        external = product.external_data if isinstance(product.external_data, dict) else {}
        raw_source_product_id = external.get("source_offer_product_id") or product.pk
        try:
            source_product_id = int(raw_source_product_id)
        except (TypeError, ValueError):
            return None

        candidates = ProductSourceOffer.objects.filter(
            product_id=source_product_id,
            is_active=True,
        )
        allowed_adapter_sources = self._allowed_adapter_sources(product)
        if allowed_adapter_sources is not None:
            if not allowed_adapter_sources:
                return None
            candidates = candidates.filter(parser_key__in=allowed_adapter_sources)
        parser_hint = str(external.get("source_parser") or "").strip().casefold()
        if parser_hint and (
            allowed_adapter_sources is None or parser_hint in allowed_adapter_sources
        ):
            candidates = candidates.filter(parser_key=parser_hint)

        size_key = str(chosen_size or "").strip()
        if size_key:
            candidates = candidates.filter(size_key__iexact=size_key)
        else:
            candidates = candidates.filter(size_key="")

        variant_key, variant_expected = self._variant_key(product)
        if variant_key:
            candidates = candidates.filter(variant_key=variant_key)
        elif variant_expected and candidates.exclude(variant_key="").exists():
            # A shadow variant without recoverable supplier identity must never
            # fall back to another color/option of the same source product.
            return None

        for offer in candidates.order_by("priority", "-last_successful_check_at", "pk"):
            if self.verifier.is_enabled_for(offer.parser_key):
                return offer
        return None

    @staticmethod
    def _missing_required_offer_decision(*, target_currency: str) -> CartOfferDecision:
        result = OfferCheckResult(
            availability_status=OfferAvailability.UNSUPPORTED,
            stock_precision=OfferStockPrecision.UNKNOWN,
            canonical_url="",
            error=OfferCheckError(
                code=OfferCheckErrorCode.UNSUPPORTED,
                message="No trusted live stock adapter is configured for this product",
                retryable=False,
            ),
            response_metadata={"reason": "trusted_stock_adapter_missing"},
        )
        return CartOfferDecision(
            offer=None,
            result=result,
            verification_status=CartItem.VerificationStatus.UNSUPPORTED,
            issues=(CartItem.VerificationIssue.VERIFICATION_UNSUPPORTED,),
            payable=False,
            public_price=None,
            public_currency=str(target_currency or "RUB").strip().upper(),
            price_change_state=CartItem.PriceChangeState.NONE,
        )

    @staticmethod
    def _money(value: Any) -> Decimal | None:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not amount.is_finite() or amount < 0:
            return None
        return amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)

    @classmethod
    def _public_price_from_source(
        cls,
        *,
        product: Product,
        source_price: Decimal,
        source_currency: str,
        target_currency: str,
    ) -> Decimal | None:
        try:
            _, _, price_with_margin = currency_converter.convert_price(
                source_price,
                source_currency,
                target_currency,
                apply_margin=True,
            )
            public_price = apply_product_markup(price_with_margin, product)
            return cls._money(public_price)
        except Exception:
            logger.exception(
                "cart_source_price_conversion_failed",
                extra={
                    "product_id": product.pk,
                    "source_currency": source_currency,
                    "target_currency": target_currency,
                },
            )
            return None

    @staticmethod
    def _error_decision(
        *,
        offer: ProductSourceOffer,
        result: OfferCheckResult,
        target_currency: str,
    ) -> CartOfferDecision:
        error_code = result.error.code if result.error else None
        if result.availability_status in {
            OfferAvailability.OUT_OF_STOCK,
            OfferAvailability.DISCONTINUED,
        } or error_code in {
            OfferCheckErrorCode.NOT_FOUND,
            OfferCheckErrorCode.GONE,
            OfferCheckErrorCode.OPTION_NOT_FOUND,
        }:
            status = CartItem.VerificationStatus.BLOCKED
            issue = CartItem.VerificationIssue.SOURCE_OUT_OF_STOCK
        elif result.availability_status == OfferAvailability.UNSUPPORTED or error_code in {
            OfferCheckErrorCode.UNSUPPORTED,
            OfferCheckErrorCode.DISABLED,
        }:
            status = CartItem.VerificationStatus.UNSUPPORTED
            issue = CartItem.VerificationIssue.VERIFICATION_UNSUPPORTED
        else:
            status = CartItem.VerificationStatus.RETRYABLE_ERROR
            issue = CartItem.VerificationIssue.SOURCE_UNREACHABLE
        return CartOfferDecision(
            offer=offer,
            result=result,
            verification_status=status,
            issues=(issue,),
            payable=False,
            public_price=None,
            public_currency=target_currency,
            price_change_state=CartItem.PriceChangeState.NONE,
        )

    def evaluate(
        self,
        *,
        product: Product,
        chosen_size: str,
        quantity: int,
        target_currency: str,
        baseline_public_price: Decimal,
        acknowledged_price: Decimal | None = None,
        acknowledged_currency: str = "",
        force: bool = False,
    ) -> CartOfferDecision | None:
        """Check one exact offer and return a mutation decision without cart writes."""
        offer = self.select_offer(product=product, chosen_size=chosen_size)
        if offer is None:
            if self.requires_verified_offer(product):
                return self._missing_required_offer_decision(
                    target_currency=target_currency,
                )
            return None

        currency = str(target_currency or "RUB").strip().upper()
        result = self.verifier.verify(offer, force=force)
        if result.error is not None or result.availability_status in {
            OfferAvailability.OUT_OF_STOCK,
            OfferAvailability.DISCONTINUED,
            OfferAvailability.SOURCE_UNREACHABLE,
            OfferAvailability.UNSUPPORTED,
            OfferAvailability.UNKNOWN,
        }:
            return self._error_decision(
                offer=offer,
                result=result,
                target_currency=currency,
            )

        issues: list[str] = []
        payable = True
        if (
            result.stock_precision == OfferStockPrecision.EXACT
            and result.stock_quantity is not None
            and quantity > result.stock_quantity
        ):
            issues.append(CartItem.VerificationIssue.SOURCE_QUANTITY_CHANGED)
            payable = False

        public_price = self._public_price_from_source(
            product=product,
            source_price=result.source_price,
            source_currency=result.source_currency,
            target_currency=currency,
        )
        if public_price is None:
            return CartOfferDecision(
                offer=offer,
                result=result,
                verification_status=CartItem.VerificationStatus.RETRYABLE_ERROR,
                issues=(CartItem.VerificationIssue.SOURCE_UNREACHABLE,),
                payable=False,
                public_price=None,
                public_currency=currency,
                price_change_state=CartItem.PriceChangeState.NONE,
            )

        baseline = self._money(baseline_public_price)
        price_change_state = CartItem.PriceChangeState.NONE
        price_acknowledged = False
        if baseline is not None and public_price != baseline:
            issues.append(CartItem.VerificationIssue.SOURCE_PRICE_CHANGED)
            if public_price > baseline:
                price_change_state = CartItem.PriceChangeState.INCREASED
                acknowledged = self._money(acknowledged_price)
                price_acknowledged = (
                    acknowledged == public_price
                    and str(acknowledged_currency or "").strip().upper() == currency
                )
                if not price_acknowledged:
                    payable = False
            else:
                price_change_state = CartItem.PriceChangeState.DECREASED

        return CartOfferDecision(
            offer=offer,
            result=result,
            verification_status=(
                CartItem.VerificationStatus.VERIFIED
                if payable
                else CartItem.VerificationStatus.BLOCKED
            ),
            issues=tuple(dict.fromkeys(issues)),
            payable=payable,
            public_price=public_price,
            public_currency=currency,
            price_change_state=price_change_state,
            price_acknowledged=price_acknowledged,
        )
