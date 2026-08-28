"""Demand-driven discovery of a real market offer for dietary supplements."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ProductSourceOffer, SupplementProduct
from apps.scrapers.base.offers import OfferCheckContext, OfferVerificationError
from apps.scrapers.models import ScraperConfig
from apps.scrapers.parsers.akakce import (
    AkakceParser,
    AkakceProductSnapshot,
    AkakceSearchCandidate,
    akakce_product_match_score,
)

logger = logging.getLogger(__name__)

CACHE_VERSION = "v1"
SOURCE_KEY = "akakce"


def _setting_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _setting_sources(name: str) -> set[str]:
    return {
        str(value or "").strip().casefold()
        for value in (getattr(settings, name, []) or [])
        if str(value or "").strip()
    }


@dataclass(frozen=True)
class SupplementStockDiscoveryResult:
    status: str
    offer: ProductSourceOffer | None = None
    candidate_name: str = ""
    confidence: Decimal | None = None


class SupplementStockDiscoveryError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class SupplementStockDiscoveryService:
    """Attach one trusted Akakce product identity without broad catalogue crawling."""

    @staticmethod
    def is_enabled() -> bool:
        return bool(getattr(settings, "SUPPLEMENT_STOCK_DISCOVERY_ENABLED", False)) and bool(
            getattr(settings, "SOURCE_OFFER_VERIFICATION_ENABLED", False)
        ) and SOURCE_KEY in _setting_sources("SOURCE_OFFER_VERIFICATION_SOURCES") and SOURCE_KEY in _setting_sources(
            "SUPPLEMENT_STOCK_ADAPTER_SOURCES"
        )

    @staticmethod
    def _negative_key(product_id: int) -> str:
        return f"supplement-stock-discovery:{CACHE_VERSION}:negative:{product_id}"

    @staticmethod
    def _active_offer(supplement: SupplementProduct) -> ProductSourceOffer | None:
        if not supplement.base_product_id:
            return None
        return (
            ProductSourceOffer.objects.filter(
                product_id=supplement.base_product_id,
                parser_key=SOURCE_KEY,
                is_active=True,
            )
            .order_by("priority", "pk")
            .first()
        )

    @staticmethod
    def _config() -> ScraperConfig | None:
        return (
            ScraperConfig.objects.filter(
                parser_class__iexact=SOURCE_KEY,
                is_enabled=True,
                status="active",
                use_proxy=True,
            )
            .order_by("priority", "pk")
            .first()
        )

    def needs_discovery(self, supplement: SupplementProduct) -> bool:
        """Cheap guard used by the existing on-demand price-check enqueue path."""

        if not self.is_enabled() or not supplement.base_product_id:
            return False
        if self._active_offer(supplement) is not None or self._config() is None:
            return False
        try:
            return not bool(cache.get(self._negative_key(supplement.base_product_id)))
        except Exception:
            logger.exception(
                "supplement_stock_discovery_cache_get_failed",
                extra={"product_id": supplement.base_product_id},
            )
            # Cache degradation must not turn every fresh reference-price click
            # into an unbounded source crawl.
            return False

    @staticmethod
    def _parser(config: ScraperConfig) -> AkakceParser:
        timeout = _setting_int(
            "SUPPLEMENT_STOCK_DISCOVERY_REQUEST_TIMEOUT_SECONDS",
            12,
            minimum=3,
            maximum=20,
        )
        parser = AkakceParser(
            config.base_url,
            delay_range=(config.delay_min, config.delay_max),
            timeout=timeout,
            max_retries=0,
            use_proxy=True,
            username=config.scraper_username or None,
            password=config.scraper_password or None,
        )
        parser.configure_request_identity(
            user_agent=config.user_agent or None,
            headers=config.headers if isinstance(config.headers, dict) else None,
            cookies=config.cookies if isinstance(config.cookies, dict) else None,
        )
        return parser

    @staticmethod
    def _rank_candidate(
        supplement: SupplementProduct,
        candidates: list[AkakceSearchCandidate],
    ) -> tuple[AkakceSearchCandidate, Decimal] | None:
        ranked = [
            (candidate, score)
            for candidate in candidates
            if (score := akakce_product_match_score(supplement.name, candidate.name)) is not None
        ]
        ranked.sort(key=lambda row: (-row[1], row[0].external_id))
        if not ranked:
            return None
        if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < Decimal("0.0500"):
            return None
        return ranked[0]

    def _remember_negative(self, supplement: SupplementProduct, reason: str, *, retryable: bool) -> None:
        ttl = _setting_int(
            (
                "SUPPLEMENT_STOCK_DISCOVERY_ERROR_TTL_SECONDS"
                if retryable
                else "SUPPLEMENT_STOCK_DISCOVERY_NO_MATCH_TTL_SECONDS"
            ),
            300 if retryable else 21600,
            minimum=60,
            maximum=86400,
        )
        try:
            cache.set(
                self._negative_key(supplement.base_product_id),
                str(reason or "unknown")[:100],
                timeout=ttl,
            )
        except Exception:
            logger.exception(
                "supplement_stock_discovery_cache_set_failed",
                extra={"product_id": supplement.base_product_id},
            )

    @staticmethod
    def _metadata(snapshot: AkakceProductSnapshot, confidence: Decimal) -> dict[str, Any]:
        selected = snapshot.selected_offer
        payload: dict[str, Any] = {
            "marketplace": SOURCE_KEY,
            "market_product_name": snapshot.name,
            "market_product_id": snapshot.external_id,
            "in_stock_seller_count": len(snapshot.offers),
            "availability_evidence": (
                "json_ld_offer_in_stock" if selected is not None else "no_current_seller_offer"
            ),
            "discovery_confidence": str(confidence),
            "discovered_on_demand": True,
        }
        if selected is not None:
            payload.update(
                {
                    "seller_name": selected.seller_name,
                    "seller_url": selected.seller_url,
                }
            )
        return payload

    @staticmethod
    def _persist_offer(
        *,
        supplement: SupplementProduct,
        config: ScraperConfig,
        candidate: AkakceSearchCandidate,
        snapshot: AkakceProductSnapshot,
        confidence: Decimal,
    ) -> ProductSourceOffer:
        now = timezone.now()
        selected = snapshot.selected_offer
        offer_key = ProductSourceOffer.build_offer_key(
            parser_key=SOURCE_KEY,
            canonical_url=snapshot.canonical_url,
            external_product_id=snapshot.external_id,
        )
        values = {
            "parser_config": {
                "parser_class": SOURCE_KEY,
                "scraper_config_id": config.pk,
                "expected_name": supplement.name,
                "matched_name": snapshot.name,
                "mapping_method": "on_demand_title_identity_v1",
            },
            "source_domain": "www.akakce.com",
            "canonical_url": snapshot.canonical_url,
            "external_product_id": snapshot.external_id,
            "external_sku": "",
            "variant_key": "",
            "size_key": "",
            "selected_options": {},
            "source_price": selected.price if selected is not None else None,
            "source_currency": selected.currency if selected is not None else "TRY",
            "availability_status": (
                ProductSourceOffer.AvailabilityStatus.IN_STOCK
                if selected is not None
                else ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK
            ),
            "stock_precision": ProductSourceOffer.StockPrecision.BOOLEAN,
            "stock_quantity": None,
            "priority": 20,
            "is_active": True,
            "last_checked_at": now,
            "last_successful_check_at": now,
            "last_error_code": "",
            "last_error_message": "",
            "consecutive_failures": 0,
            "response_metadata": SupplementStockDiscoveryService._metadata(
                snapshot,
                confidence,
            ),
        }
        with transaction.atomic():
            # Never remap an existing active identity implicitly.  Discovery is
            # idempotent; a deliberate remap remains an operator action.
            existing = (
                ProductSourceOffer.objects.select_for_update()
                .filter(
                    product_id=supplement.base_product_id,
                    parser_key=SOURCE_KEY,
                    is_active=True,
                )
                .order_by("priority", "pk")
                .first()
            )
            if existing is not None:
                return existing
            offer, _ = ProductSourceOffer.objects.update_or_create(
                product_id=supplement.base_product_id,
                parser_key=SOURCE_KEY,
                offer_key=offer_key,
                defaults=values,
            )
        return offer

    def discover(
        self,
        supplement: SupplementProduct,
        *,
        persist: bool = True,
        force: bool = False,
    ) -> SupplementStockDiscoveryResult:
        if not force and not self.is_enabled():
            return SupplementStockDiscoveryResult(status="disabled")
        if not supplement.base_product_id:
            return SupplementStockDiscoveryResult(status="missing_product_identity")
        existing = self._active_offer(supplement)
        if existing is not None:
            return SupplementStockDiscoveryResult(status="existing", offer=existing)

        config = self._config()
        if config is None:
            raise SupplementStockDiscoveryError(
                "source_not_configured",
                "Akakce stock adapter requires an active proxy-enabled ScraperConfig",
                retryable=False,
            )

        try:
            with self._parser(config) as parser:
                candidates = parser.search_products(supplement.name, max_results=5)
                ranked = self._rank_candidate(supplement, candidates)
                if ranked is None:
                    if persist:
                        self._remember_negative(
                            supplement,
                            "no_confident_match",
                            retryable=False,
                        )
                    return SupplementStockDiscoveryResult(status="no_match")
                candidate, confidence = ranked
                context = OfferCheckContext(
                    canonical_url=candidate.url,
                    external_product_id=candidate.external_id,
                    parser_config={"expected_name": supplement.name},
                )
                snapshot = parser.inspect_offer(context)
        except OfferVerificationError as exc:
            if persist:
                self._remember_negative(
                    supplement,
                    exc.error.code.value,
                    retryable=exc.error.retryable,
                )
            raise SupplementStockDiscoveryError(
                exc.error.code.value,
                exc.error.message,
                retryable=exc.error.retryable,
            ) from exc

        if not persist:
            return SupplementStockDiscoveryResult(
                status="matched_dry_run",
                candidate_name=snapshot.name,
                confidence=confidence,
            )
        offer = self._persist_offer(
            supplement=supplement,
            config=config,
            candidate=candidate,
            snapshot=snapshot,
            confidence=confidence,
        )
        try:
            cache.delete(self._negative_key(supplement.base_product_id))
        except Exception:
            logger.exception(
                "supplement_stock_discovery_cache_delete_failed",
                extra={"product_id": supplement.base_product_id},
            )
        logger.info(
            "supplement_stock_offer_discovered",
            extra={
                "product_id": supplement.base_product_id,
                "offer_id": offer.pk,
                "source": SOURCE_KEY,
                "confidence": str(confidence),
                "seller_count": len(snapshot.offers),
            },
        )
        return SupplementStockDiscoveryResult(
            status="created",
            offer=offer,
            candidate_name=snapshot.name,
            confidence=confidence,
        )
