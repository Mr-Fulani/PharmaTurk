"""Demand-driven refresh of one parsed catalogue card.

The browser may only name a persisted Product.  Supplier URL, parser and options
are resolved from ProductSourceOffer rows written by the catalogue importer.
Network I/O happens before the transaction; validated price/inventory changes are
then committed atomically without running the normal content-import pipeline.
"""

from __future__ import annotations

import logging
import math
import re
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import PriceHistory, Product, ProductSourceOffer
from apps.catalog.services.source_offer_verification import SourceOfferVerificationService
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig
from apps.scrapers.parsers.registry import get_parser
from apps.scrapers.services import ScraperIntegrationService
from apps.scrapers.source_offers import (
    SourceOfferSnapshot,
    build_source_offer_snapshots,
    record_scraped_product_offers,
)

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Histogram

    PRODUCT_CARD_REFRESHES = Counter(
        "product_card_source_refresh_total",
        "Demand-driven full product-card supplier refreshes",
        ("source", "outcome"),
    )
    PRODUCT_CARD_REFRESH_LATENCY = Histogram(
        "product_card_source_refresh_seconds",
        "Demand-driven full product-card supplier refresh latency",
        ("source",),
    )
    PRODUCT_CARD_REFRESH_CHANGES = Counter(
        "product_card_source_refresh_changes_total",
        "Inventory-only values changed by a product-card refresh",
        ("source", "field"),
    )
except (ImportError, ValueError):  # pragma: no cover - optional/dev autoreload
    PRODUCT_CARD_REFRESHES = None
    PRODUCT_CARD_REFRESH_LATENCY = None
    PRODUCT_CARD_REFRESH_CHANGES = None

CACHE_VERSION = "v1"
REFERENCE_ONLY_SOURCES = frozenset({"ilacfiyati"})
SINGLE_OFFER_REFRESH_SOURCES = frozenset({"akakce"})
FASHION_PRODUCT_TYPES = frozenset(
    {"clothing", "shoes", "headwear", "underwear", "islamic_clothing"}
)
MAX_DATABASE_PRICE = Decimal("99999999.99")


class ProductCardRefreshError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class RefreshTarget:
    product: Product
    offer: ProductSourceOffer
    parser_class: type

    @property
    def parser_key(self) -> str:
        return str(self.offer.parser_key or "").strip().casefold()


def _setting_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _setting_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _cache_get(key: str):
    try:
        return cache.get(key)
    except Exception:
        logger.exception("product_card_refresh_cache_get_failed", extra={"cache_key": key})
        return None


def _cache_set(key: str, value: Any, timeout: int) -> None:
    try:
        cache.set(key, value, timeout=max(timeout, 1))
    except Exception:
        logger.exception("product_card_refresh_cache_set_failed", extra={"cache_key": key})


def _cache_add(key: str, value: Any, timeout: int) -> bool:
    try:
        return bool(cache.add(key, value, timeout=max(timeout, 1)))
    except Exception:
        logger.exception("product_card_refresh_cache_add_failed", extra={"cache_key": key})
        # Cache degradation must not make parsed products permanently stale.
        return True


def _delete_lock_if_owned(key: str, token: str) -> None:
    try:
        if cache.get(key) == token:
            cache.delete(key)
    except Exception:
        logger.exception("product_card_refresh_cache_unlock_failed", extra={"cache_key": key})


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount <= 0 or amount > MAX_DATABASE_PRICE:
        return None
    return amount.quantize(Decimal("0.01"))


def _currency(value: Any) -> str:
    code = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3,5}", code):
        return ""
    return code


class ProductCardSourceRefreshService:
    """Eligibility, queue state and inventory-only reconciliation for one card."""

    SAFE_STATUS_MESSAGES = {
        "source_unavailable": "Источник временно недоступен. Показаны последние сохранённые данные.",
        "source_not_found": "Товар больше недоступен у поставщика. Показаны последние сохранённые данные.",
        "rate_limited": "Источник временно ограничил запросы. Показаны последние сохранённые данные.",
        "invalid_source": "Источник товара не прошёл проверку безопасности.",
        "identity_mismatch": "Ответ источника относится к другому товару.",
        "invalid_payload": "Источник вернул неполные данные. Карточка не изменена.",
        "unsupported": "Для этого источника обновление карточки пока не поддерживается.",
        "internal_error": "Не удалось обновить карточку. Показаны последние сохранённые данные.",
    }

    @staticmethod
    def _state_key(product_id: int) -> str:
        return f"product-card-refresh:state:{CACHE_VERSION}:{product_id}"

    @staticmethod
    def _lock_key(product_id: int) -> str:
        return f"product-card-refresh:lock:{CACHE_VERSION}:{product_id}"

    @staticmethod
    def _allowed_sources() -> set[str]:
        return {
            str(value or "").strip().casefold()
            for value in (
                getattr(settings, "PRODUCT_CARD_SOURCE_REFRESH_SOURCES", []) or []
            )
            if str(value or "").strip()
        }

    @staticmethod
    def enabled() -> bool:
        return bool(getattr(settings, "PRODUCT_CARD_SOURCE_REFRESH_ENABLED", False))

    @staticmethod
    def _request_timeout(parser_key: str) -> float:
        if (
            parser_key == "flo"
            and getattr(settings, "FLO_WEB_UNLOCKER_ENABLED", False)
        ):
            return _setting_float(
                "FLO_WEB_UNLOCKER_TIMEOUT_SECONDS",
                60.0,
                minimum=1.0,
                maximum=60.0,
            )
        return _setting_float(
            "PRODUCT_CARD_SOURCE_REFRESH_TIMEOUT_SECONDS",
            12.0,
            minimum=1.0,
            maximum=30.0,
        )

    def _target(self, product: Product) -> RefreshTarget | None:
        if not self.enabled() or not product.pk or not product.is_active:
            return None
        # Medicines keep their separate reference-price flow and are never sale stock.
        if str(product.product_type or "").strip().casefold() == "medicines":
            return None

        allowed = self._allowed_sources()
        if not allowed:
            return None

        verifier = SourceOfferVerificationService()
        offers = (
            product.source_offers.filter(
                is_active=True,
                parser_key__in=allowed,
            )
            .exclude(parser_key__in=REFERENCE_ONLY_SOURCES)
            .order_by("priority", "id")
        )
        for offer in offers:
            parser_class = verifier._trusted_parser_class(offer)
            if parser_class is not None and (
                offer.parser_key not in SINGLE_OFFER_REFRESH_SOURCES
                or verifier.supports_offer(offer)
            ):
                return RefreshTarget(product=product, offer=offer, parser_class=parser_class)
        return None

    def status(self, product: Product) -> dict[str, Any]:
        target = self._target(product)
        if target is None:
            return {
                "eligible": False,
                "status": "not_eligible",
                "retryable": False,
            }

        state = _cache_get(self._state_key(product.pk))
        if isinstance(state, dict):
            return {"eligible": True, **state}
        return {
            "eligible": True,
            "status": "idle",
            "source": target.parser_key,
            "retryable": False,
        }

    def _set_state(
        self,
        product_id: int,
        payload: dict[str, Any],
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        state = dict(payload)
        state["updated_at"] = timezone.now().isoformat()
        ttl = timeout or _setting_int(
            "PRODUCT_CARD_SOURCE_REFRESH_STATE_TTL_SECONDS", 300, minimum=30, maximum=3600
        )
        _cache_set(self._state_key(product_id), state, ttl)
        return state

    def request_refresh(self, product: Product) -> dict[str, Any]:
        target = self._target(product)
        if target is None:
            return self.status(product)

        existing = _cache_get(self._state_key(product.pk))
        if isinstance(existing, dict) and existing.get("status") in {
            "pending",
            "running",
        }:
            return {"eligible": True, **existing}

        lock_seconds = _setting_int(
            "PRODUCT_CARD_SOURCE_REFRESH_LOCK_SECONDS",
            150,
            minimum=30,
            maximum=600,
        )
        lock_key = self._lock_key(product.pk)
        token = uuid.uuid4().hex
        if not _cache_add(lock_key, token, lock_seconds):
            current = _cache_get(self._state_key(product.pk))
            if isinstance(current, dict):
                return {"eligible": True, **current}
            return {
                "eligible": True,
                "status": "pending",
                "source": target.parser_key,
                "retryable": False,
            }

        pending = self._set_state(
            product.pk,
            {
                "status": "pending",
                "source": target.parser_key,
                "retryable": False,
            },
        )
        try:
            from apps.catalog.tasks import refresh_product_card_source_task

            refresh_product_card_source_task.apply_async(args=[product.pk, token])
        except Exception:
            logger.exception(
                "product_card_refresh_enqueue_failed",
                extra={"product_id": product.pk, "source": target.parser_key},
            )
            _delete_lock_if_owned(lock_key, token)
            failed = self._set_state(
                product.pk,
                {
                    "status": "failed",
                    "source": target.parser_key,
                    "error_code": "internal_error",
                    "message": self.SAFE_STATUS_MESSAGES["internal_error"],
                    "retryable": True,
                },
                timeout=_setting_int(
                    "PRODUCT_CARD_SOURCE_REFRESH_ERROR_TTL_SECONDS",
                    30,
                    minimum=5,
                    maximum=300,
                ),
            )
            return {"eligible": True, **failed}

        # In eager Celery tests the task may already have replaced pending state.
        current = _cache_get(self._state_key(product.pk))
        return {"eligible": True, **(current if isinstance(current, dict) else pending)}

    def release_lock(self, product_id: int, token: str) -> None:
        _delete_lock_if_owned(self._lock_key(product_id), token)

    @staticmethod
    def _observe(source: str, outcome: str, started_at: float) -> None:
        if PRODUCT_CARD_REFRESHES is not None:
            PRODUCT_CARD_REFRESHES.labels(source=source or "unknown", outcome=outcome).inc()
        if PRODUCT_CARD_REFRESH_LATENCY is not None:
            PRODUCT_CARD_REFRESH_LATENCY.labels(source=source or "unknown").observe(
                max(time.monotonic() - started_at, 0.0)
            )

    @staticmethod
    def _scraper_config(offer: ProductSourceOffer) -> ScraperConfig | None:
        payload = offer.parser_config if isinstance(offer.parser_config, dict) else {}
        queryset = ScraperConfig.objects.filter(is_enabled=True, status="active")
        raw_id = payload.get("scraper_config_id")
        if raw_id not in (None, ""):
            try:
                config = queryset.filter(pk=int(raw_id)).first()
            except (TypeError, ValueError):
                config = None
            if config is not None and str(config.parser_class or "").casefold() == offer.parser_key:
                return config
            return None
        return (
            queryset.filter(parser_class__iexact=offer.parser_key)
            .order_by("priority", "pk")
            .first()
        )

    def _fetch_product(self, target: RefreshTarget) -> ScrapedProduct:
        config = self._scraper_config(target.offer)
        parsed_url = urlparse(target.offer.canonical_url)
        origin = f"https://{parsed_url.netloc}"
        timeout = self._request_timeout(target.parser_key)
        retries = _setting_int(
            "PRODUCT_CARD_SOURCE_REFRESH_MAX_RETRIES",
            1,
            minimum=0,
            maximum=2,
        )
        kwargs: dict[str, Any] = {
            "base_url": config.base_url if config else origin,
            "timeout": timeout,
            "max_retries": retries,
            "use_proxy": bool(config and config.use_proxy),
            "username": config.scraper_username if config else "",
            "password": config.scraper_password if config else "",
        }
        if target.parser_key == "flo" and bool(config and config.use_proxy):
            # Explicitly scopes the paid transport to this demand-driven card-open job.
            kwargs["use_web_unlocker"] = True
        with target.parser_class(**kwargs) as parser:
            if config is not None:
                parser.delay_range = (config.delay_min, config.delay_max)
                parser.configure_request_identity(
                    user_agent=config.user_agent,
                    headers=config.headers,
                    cookies=config.cookies,
                )
            if target.parser_key == "flo":
                # A FLO product group can link many sibling colours. Each sibling
                # would be another paid browser-rendering request, even though the
                # user opened only this saved colour. Refresh exactly that colour;
                # the cart follows the same one-offer rule.
                result = parser.parse_product_detail(
                    target.offer.canonical_url,
                    include_sibling_variants=False,
                )
            else:
                result = parser.parse_product_detail(target.offer.canonical_url)

        if isinstance(result, list):
            if len(result) != 1:
                raise ProductCardRefreshError(
                    "invalid_payload",
                    "Product detail response must contain exactly one product group",
                    retryable=False,
                )
            result = result[0]
        if not isinstance(result, ScrapedProduct):
            if target.parser_key == "flo":
                # Browser rendering already rejects FLO's CAPTCHA page. A clean
                # site response without productDetail is the category redirect
                # FLO uses for a removed product URL.
                raise ProductCardRefreshError(
                    "source_not_found",
                    "Supplier product was not found",
                    retryable=False,
                )
            raise ProductCardRefreshError(
                "source_unavailable",
                "Supplier returned no product detail",
                retryable=True,
            )
        return result

    @staticmethod
    def _single_offer_product(
        target: RefreshTarget,
        verifier: SourceOfferVerificationService,
    ) -> ScrapedProduct:
        result = verifier.verify(target.offer, force=True)
        if not result.is_success:
            error = result.error
            conclusive_absence = bool(
                error
                and error.code.value in {"not_found", "option_not_found", "gone"}
            )
            if not conclusive_absence:
                raise ProductCardRefreshError(
                    "source_unavailable" if not error or error.retryable else "unsupported",
                    error.message if error else "Single-offer verification failed",
                    retryable=bool(error and error.retryable),
                )
        price = result.source_price or target.product.price
        currency = result.source_currency or target.product.currency
        return ScrapedProduct(
            name=target.product.name,
            price=price,
            currency=currency,
            url=result.canonical_url or target.offer.canonical_url,
            external_id=target.offer.external_product_id,
            sku=target.offer.external_sku,
            is_available=result.availability_status.value in {"in_stock", "limited"},
            stock_quantity=result.stock_quantity,
            source=target.parser_key,
        )

    @staticmethod
    def _validate_identity(target: RefreshTarget, scraped: ScrapedProduct) -> None:
        parser_key = target.parser_key
        if str(scraped.source or "").strip().casefold() != parser_key:
            raise ProductCardRefreshError(
                "identity_mismatch", "Parser source changed", retryable=False
            )
        if get_parser(scraped.url) is not target.parser_class:
            raise ProductCardRefreshError(
                "invalid_source", "Supplier redirected to an untrusted domain", retryable=False
            )

        expected = str(target.offer.external_product_id or target.product.external_id or "").strip()
        observed = str(scraped.external_id or "").strip()
        if expected and observed and expected != observed:
            # LCW does not expose a durable parent/group id.  Its parser builds
            # one from the lowest currently linked colour id, so removing that
            # colour legitimately changes ``scraped.external_id``.  Accept the
            # drift only when the exact persisted supplier variant and its URL
            # are still present in the fresh matrix.  Parser/domain validation
            # above remains mandatory and other sources stay strict.
            attributes = scraped.attributes if isinstance(scraped.attributes, dict) else {}
            variants = attributes.get("fashion_variants")
            expected_variant = str(target.offer.variant_key or "").strip()
            expected_url = str(target.offer.canonical_url or "").strip().rstrip("/")
            lcw_variant_still_matches = (
                parser_key == "lcw"
                and expected_variant
                and expected_url
                and isinstance(variants, list)
                and any(
                    isinstance(row, dict)
                    and str(row.get("external_id") or "").strip() == expected_variant
                    and str(row.get("external_url") or "").strip().rstrip("/") == expected_url
                    for row in variants
                )
            )
            if lcw_variant_still_matches:
                return
            raise ProductCardRefreshError(
                "identity_mismatch", "Supplier product identity changed", retryable=False
            )

    def _validated_snapshots(
        self,
        target: RefreshTarget,
        scraped: ScrapedProduct,
    ) -> list[SourceOfferSnapshot]:
        self._validate_identity(target, scraped)
        snapshots = build_source_offer_snapshots(scraped, parser_key=target.parser_key)
        if not snapshots:
            raise ProductCardRefreshError(
                "invalid_payload", "Supplier response has no buyable options", retryable=False
            )
        for snapshot in snapshots:
            if snapshot.source_price is None or snapshot.source_price <= 0:
                raise ProductCardRefreshError(
                    "invalid_payload", "Supplier response has an invalid price", retryable=False
                )
            if not _currency(snapshot.source_currency):
                raise ProductCardRefreshError(
                    "invalid_payload", "Supplier response has an invalid currency", retryable=False
                )

        raw_price = _decimal(scraped.price)
        raw_currency = _currency(scraped.currency)
        if raw_price is None or not raw_currency:
            raise ProductCardRefreshError(
                "invalid_payload", "Supplier response has no valid base price", retryable=False
            )
        if any(snapshot.source_currency != raw_currency for snapshot in snapshots):
            raise ProductCardRefreshError(
                "invalid_payload", "Supplier returned mixed currencies", retryable=False
            )
        self._validate_price_anomaly(target, raw_price, raw_currency)

        attrs = scraped.attributes if isinstance(scraped.attributes, dict) else {}
        if target.product.product_type in FASHION_PRODUCT_TYPES:
            variants = attrs.get("fashion_variants")
            if not isinstance(variants, list) or not variants:
                raise ProductCardRefreshError(
                    "invalid_payload", "Fashion response has no variant matrix", retryable=False
                )
        if target.product.product_type == "furniture":
            variants = attrs.get("furniture_variants")
            has_saved_variant_matrix = target.product.source_offers.filter(
                is_active=True,
                parser_key=target.parser_key,
            ).exclude(variant_key="").exists()
            if has_saved_variant_matrix and (not isinstance(variants, list) or not variants):
                raise ProductCardRefreshError(
                    "invalid_payload", "Furniture response has no variant matrix", retryable=False
                )
        return snapshots

    @staticmethod
    def _validate_price_anomaly(
        target: RefreshTarget,
        price: Decimal,
        currency: str,
    ) -> None:
        reference = None
        if _currency(target.product.currency) == currency:
            reference = target.product.price
        if not reference:
            reference = (
                target.product.source_offers.filter(
                    is_active=True,
                    parser_key=target.parser_key,
                    source_currency=currency,
                    source_price__isnull=False,
                )
                .order_by("priority", "id")
                .values_list("source_price", flat=True)
                .first()
            )
        if not reference or reference <= 0:
            return
        ratio = price / Decimal(reference)
        minimum = Decimal(
            str(
                _setting_float(
                    "PRODUCT_CARD_SOURCE_REFRESH_MIN_PRICE_RATIO",
                    0.05,
                    minimum=0.001,
                    maximum=1.0,
                )
            )
        )
        maximum = Decimal(
            str(
                _setting_float(
                    "PRODUCT_CARD_SOURCE_REFRESH_MAX_PRICE_RATIO",
                    20.0,
                    minimum=1.0,
                    maximum=1000.0,
                )
            )
        )
        if ratio < minimum or ratio > maximum:
            raise ProductCardRefreshError(
                "invalid_payload", "Supplier price failed the anomaly guard", retryable=False
            )

    @staticmethod
    def _snapshot_map(
        snapshots: list[SourceOfferSnapshot],
    ) -> dict[tuple[str, str], SourceOfferSnapshot]:
        return {(row.variant_key, row.size_key): row for row in snapshots}

    @staticmethod
    def _existing_domain_item(product: Product):
        relation = {
            "clothing": "clothing_item",
            "shoes": "shoe_item",
            "headwear": "headwear_item",
            "underwear": "underwear_item",
            "islamic_clothing": "islamic_clothing_item",
            "furniture": "furniture_item",
        }.get(product.product_type)
        if not relation:
            return None
        try:
            return getattr(product, relation)
        except ObjectDoesNotExist as exc:
            raise ProductCardRefreshError(
                "invalid_payload",
                "Parsed product has no catalogue domain row",
                retryable=False,
            ) from exc

    @staticmethod
    def _availability(snapshot: SourceOfferSnapshot | None, fallback: Any) -> bool:
        if snapshot is None:
            return bool(fallback)
        return snapshot.availability_status in {
            ProductSourceOffer.AvailabilityStatus.IN_STOCK,
            ProductSourceOffer.AvailabilityStatus.LIMITED,
        }

    @staticmethod
    def _stock(snapshot: SourceOfferSnapshot | None, *, available: bool) -> int | None:
        if not available:
            return 0
        if snapshot and snapshot.stock_precision == ProductSourceOffer.StockPrecision.EXACT:
            return snapshot.stock_quantity
        return None

    def _sync_fashion_inventory(
        self,
        product: Product,
        variants: list[dict[str, Any]],
        snapshots: list[SourceOfferSnapshot],
    ) -> dict[str, int]:
        integration = ScraperIntegrationService()
        config = integration._fashion_model_config(product.product_type)
        if not config:
            raise ProductCardRefreshError(
                "unsupported", "No inventory model for this product type", retryable=False
            )
        domain_product = self._existing_domain_item(product)
        VariantModel = config["variant_model"]
        VariantSizeModel = config["variant_size_model"]
        ProductSizeModel = config["product_size_model"]
        by_option = self._snapshot_map(snapshots)
        counts = {"variants_created": 0, "variants_updated": 0, "sizes_created": 0, "sizes_updated": 0}

        for index, spec in enumerate(variants):
            if not isinstance(spec, dict):
                continue
            external_id = str(spec.get("external_id") or "").strip()
            if not external_id:
                raise ProductCardRefreshError(
                    "invalid_payload", "Variant has no stable source identity", retryable=False
                )
            price = _decimal(spec.get("price"))
            currency = _currency(spec.get("currency") or product.currency)
            if price is None or not currency:
                raise ProductCardRefreshError(
                    "invalid_payload", "Variant has invalid price data", retryable=False
                )

            raw_sizes = spec.get("sizes") if isinstance(spec.get("sizes"), list) else []
            normalized_sizes: list[dict[str, Any]] = []
            for size_index, raw_size in enumerate(raw_sizes):
                if not isinstance(raw_size, dict):
                    continue
                size_name = str(raw_size.get("size") or "").strip()[:50]
                if not size_name:
                    continue
                snapshot = by_option.get((external_id, size_name))
                available = self._availability(snapshot, raw_size.get("is_available"))
                normalized_sizes.append(
                    {
                        "size": size_name,
                        "is_available": available,
                        "stock_quantity": self._stock(snapshot, available=available),
                        "sort_order": int(raw_size.get("sort_order") or size_index),
                    }
                )

            variant_snapshot = by_option.get((external_id, ""))
            if normalized_sizes:
                available = any(row["is_available"] for row in normalized_sizes)
                exact_values = [
                    row["stock_quantity"]
                    for row in normalized_sizes
                    if row["is_available"] and row["stock_quantity"] is not None
                ]
                stock = sum(exact_values) if available and len(exact_values) == sum(
                    1 for row in normalized_sizes if row["is_available"]
                ) else (0 if not available else None)
            else:
                available = self._availability(variant_snapshot, spec.get("is_available"))
                stock = self._stock(variant_snapshot, available=available)

            color = str(spec.get("color") or "").strip()[:50]
            display_name = str(spec.get("display_name") or "").strip()[:500]
            name = display_name or " — ".join(value for value in (domain_product.name, color) if value)
            defaults = {
                "name": name[:500],
                "color": color,
                "sku": str(spec.get("sku") or external_id)[:100],
                "barcode": str(spec.get("barcode") or "")[:100],
                "gtin": str(spec.get("gtin") or "")[:100],
                "mpn": str(spec.get("mpn") or "")[:100],
                "price": price,
                "currency": currency,
                "external_url": str(spec.get("external_url") or "")[:2000],
                "sort_order": int(spec.get("sort_order") or index),
                "stock_quantity": stock,
                "is_available": available,
                "is_active": True,
                # Media is deliberately absent: card refresh must never invoke
                # download signals or overwrite an editor-curated gallery.
                "main_image": "",
                "external_data": {
                    "source": "scraper",
                    "source_parser": str((product.external_data or {}).get("source") or ""),
                    "source_offer_product_id": product.pk,
                    "source_offer_variant_key": external_id,
                },
            }
            variant, created = VariantModel.objects.get_or_create(
                product=domain_product,
                external_id=external_id,
                defaults=defaults,
            )
            if created:
                counts["variants_created"] += 1
            else:
                update_values: dict[str, Any] = {}
                for field, value in {
                    "price": price,
                    "currency": currency,
                    "is_available": available,
                    "stock_quantity": stock,
                    "is_active": True,
                }.items():
                    if getattr(variant, field) != value:
                        update_values[field] = value
                if update_values:
                    VariantModel.objects.filter(pk=variant.pk).update(**update_values)
                    counts["variants_updated"] += 1

            for size_row in normalized_sizes:
                size_obj = variant.sizes.filter(size=size_row["size"]).order_by("id").first()
                if size_obj is None:
                    VariantSizeModel.objects.create(variant=variant, **size_row)
                    counts["sizes_created"] += 1
                    continue
                size_updates = {
                    field: value
                    for field, value in size_row.items()
                    if field != "size" and getattr(size_obj, field) != value
                }
                if size_updates:
                    VariantSizeModel.objects.filter(pk=size_obj.pk).update(**size_updates)
                    counts["sizes_updated"] += 1

        active_variants = list(domain_product.variants.filter(is_active=True).order_by("sort_order", "id"))
        integration._sync_product_size_rows(
            domain_product,
            ProductSizeModel,
            variants=active_variants,
        )
        return counts

    def _sync_furniture_inventory(
        self,
        product: Product,
        variants: list[dict[str, Any]],
        snapshots: list[SourceOfferSnapshot],
    ) -> dict[str, int]:
        from apps.catalog.models import FurnitureVariant

        domain_product = self._existing_domain_item(product)
        by_option = self._snapshot_map(snapshots)
        counts = {"variants_created": 0, "variants_updated": 0, "sizes_created": 0, "sizes_updated": 0}
        for index, spec in enumerate(variants):
            if not isinstance(spec, dict):
                continue
            external_id = str(spec.get("external_id") or "").strip()
            if not external_id:
                raise ProductCardRefreshError(
                    "invalid_payload", "Furniture variant has no identity", retryable=False
                )
            price = _decimal(spec.get("price"))
            currency = _currency(spec.get("currency") or product.currency)
            if price is None or not currency:
                raise ProductCardRefreshError(
                    "invalid_payload", "Furniture variant has invalid price", retryable=False
                )
            snapshot = by_option.get((external_id, ""))
            available = self._availability(snapshot, spec.get("is_available"))
            stock = self._stock(snapshot, available=available)
            defaults = {
                "name": str(spec.get("display_name") or domain_product.name)[:500],
                "color": str(spec.get("color") or "")[:50],
                "sku": str(spec.get("sku") or external_id)[:100],
                "price": price,
                "currency": currency,
                "external_url": str(spec.get("external_url") or "")[:2000],
                "sort_order": int(spec.get("sort_order") or index),
                "stock_quantity": stock,
                "is_available": available,
                "is_active": True,
                "main_image": "",
                "external_data": {
                    "source": "scraper",
                    "source_parser": str((product.external_data or {}).get("source") or ""),
                    "source_offer_product_id": product.pk,
                    "source_offer_variant_key": external_id,
                },
            }
            variant, created = FurnitureVariant.objects.get_or_create(
                product=domain_product,
                external_id=external_id,
                defaults=defaults,
            )
            if created:
                counts["variants_created"] += 1
                continue
            updates: dict[str, Any] = {}
            for field, value in {
                "price": price,
                "currency": currency,
                "is_available": available,
                "stock_quantity": stock,
                "is_active": True,
            }.items():
                if getattr(variant, field) != value:
                    updates[field] = value
            if updates:
                FurnitureVariant.objects.filter(pk=variant.pk).update(**updates)
                counts["variants_updated"] += 1
        return counts

    @transaction.atomic
    def _mark_source_url_unavailable(self, target: RefreshTarget) -> dict[str, int]:
        """Persist conclusive removal for only the opened supplier URL.

        FLO groups sibling colours under one catalogue product.  A removed URL is
        conclusive for every saved size on that colour, but says nothing about a
        sibling colour with another URL.
        """

        product = Product.objects.select_for_update().get(pk=target.product.pk)
        now = timezone.now()
        affected_offers = product.source_offers.filter(
            is_active=True,
            parser_key=target.parser_key,
            canonical_url=target.offer.canonical_url,
        )
        variant_keys = list(
            affected_offers.exclude(variant_key="").values_list("variant_key", flat=True).distinct()
        )
        offers_updated = affected_offers.update(
            availability_status=ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK,
            stock_precision=ProductSourceOffer.StockPrecision.UNKNOWN,
            stock_quantity=None,
            last_checked_at=now,
            last_error_code="not_found",
            last_error_message="Supplier product URL was not found",
            consecutive_failures=0,
            updated_at=now,
        )

        variants_updated = 0
        sizes_updated = 0
        domain_product = None
        if product.product_type in FASHION_PRODUCT_TYPES and variant_keys:
            integration = ScraperIntegrationService()
            config = integration._fashion_model_config(product.product_type)
            if config:
                domain_product = self._existing_domain_item(product)
                VariantModel = config["variant_model"]
                VariantSizeModel = config["variant_size_model"]
                ProductSizeModel = config["product_size_model"]
                variants = VariantModel.objects.filter(
                    product=domain_product,
                    external_id__in=variant_keys,
                    is_active=True,
                )
                variant_ids = list(variants.values_list("pk", flat=True))
                variants_updated = variants.update(
                    is_available=False,
                    stock_quantity=0,
                )
                if variant_ids:
                    sizes_updated = VariantSizeModel.objects.filter(
                        variant_id__in=variant_ids
                    ).update(
                        is_available=False,
                        stock_quantity=0,
                    )
                active_variants = list(
                    domain_product.variants.filter(is_active=True).order_by("sort_order", "id")
                )
                integration._sync_product_size_rows(
                    domain_product,
                    ProductSizeModel,
                    variants=active_variants,
                )

        other_active_offer_exists = (
            product.source_offers.filter(is_active=True)
            .exclude(
                parser_key=target.parser_key,
                canonical_url=target.offer.canonical_url,
            )
            .exists()
        )
        product_updated = 0
        if offers_updated and not other_active_offer_exists:
            product_updated = Product.objects.filter(pk=product.pk).update(
                is_available=False,
                stock_quantity=0,
                availability_status="out_of_stock",
                last_synced_at=now,
                updated_at=now,
            )
            domain_product = domain_product or product.domain_item
            if domain_product is not product:
                fields = {field.name for field in domain_product._meta.concrete_fields}
                values: dict[str, Any] = {"is_available": False}
                if "stock_quantity" in fields:
                    values["stock_quantity"] = 0
                domain_product.__class__.objects.filter(pk=domain_product.pk).update(**values)

        return {
            "offers_updated": offers_updated,
            "variants_updated": variants_updated,
            "sizes_updated": sizes_updated,
            "product_updated": product_updated,
        }

    @staticmethod
    def _aggregate_stock(snapshots: list[SourceOfferSnapshot]) -> tuple[bool, int | None]:
        in_stock = [
            row
            for row in snapshots
            if row.availability_status
            in {
                ProductSourceOffer.AvailabilityStatus.IN_STOCK,
                ProductSourceOffer.AvailabilityStatus.LIMITED,
            }
        ]
        if not in_stock:
            return False, 0
        if all(row.stock_precision == ProductSourceOffer.StockPrecision.EXACT for row in in_stock):
            return True, sum(int(row.stock_quantity or 0) for row in in_stock)
        return True, None

    @staticmethod
    def _update_domain_price_stock(
        product: Product,
        *,
        price: Decimal,
        currency: str,
        available: bool,
        stock: int | None,
    ) -> None:
        domain = product.domain_item
        if domain is product:
            return
        fields = {field.name for field in domain._meta.concrete_fields}
        values: dict[str, Any] = {
            "price": price,
            "currency": currency,
            "is_available": available,
        }
        if "stock_quantity" in fields:
            values["stock_quantity"] = stock
        domain.__class__.objects.filter(pk=domain.pk).update(**values)

    @transaction.atomic
    def _reconcile(
        self,
        target: RefreshTarget,
        scraped: ScrapedProduct,
        snapshots: list[SourceOfferSnapshot],
        *,
        offers_already_persisted: bool = False,
    ) -> dict[str, Any]:
        product = Product.objects.select_for_update().get(pk=target.product.pk)
        price = _decimal(scraped.price)
        currency = _currency(scraped.currency)
        if price is None or not currency:  # guarded before transaction; defence in depth
            raise ProductCardRefreshError(
                "invalid_payload", "Invalid base price", retryable=False
            )
        available, stock = self._aggregate_stock(snapshots)
        attrs = scraped.attributes if isinstance(scraped.attributes, dict) else {}
        counts = {"variants_created": 0, "variants_updated": 0, "sizes_created": 0, "sizes_updated": 0}

        if product.product_type in FASHION_PRODUCT_TYPES:
            counts = self._sync_fashion_inventory(
                product,
                list(attrs.get("fashion_variants") or []),
                snapshots,
            )
        elif product.product_type == "furniture" and attrs.get("furniture_variants"):
            counts = self._sync_furniture_inventory(
                product,
                list(attrs.get("furniture_variants") or []),
                snapshots,
            )
        # Some legacy domains (for example accessories) intentionally have no
        # public variant table. Their complete option matrix is still refreshed
        # in ProductSourceOffer for cart/checkout, while the base card receives
        # only aggregate price/availability.

        if not offers_already_persisted:
            record_scraped_product_offers(
                product=product,
                scraped_product=scraped,
                scraper_config=self._scraper_config(target.offer),
                deactivate_missing=False,
                skip_variant_summaries_with_saved_sizes=True,
            )
        self._update_domain_price_stock(
            product,
            price=price,
            currency=currency,
            available=available,
            stock=stock,
        )

        price_changed = product.price != price or product.currency != currency
        synced_at = timezone.now()
        # Inventory refresh must not emit Product post_save signals.  Those
        # signals belong to the catalog/content pipeline and may rewrite shadow
        # metadata or media manifests even when save(update_fields=...) is used.
        Product.objects.filter(pk=product.pk).update(
            price=price,
            currency=currency,
            is_available=available,
            stock_quantity=stock,
            availability_status="in_stock" if available else "out_of_stock",
            last_synced_at=synced_at,
            updated_at=synced_at,
        )
        if price_changed:
            PriceHistory.objects.create(
                product=product,
                price=price,
                currency=currency,
                source=f"product_card_refresh:{target.parser_key}",
            )
        return {
            **counts,
            "offers_observed": len(snapshots),
            "price_changed": price_changed,
            "available": available,
        }

    def run(self, product_id: int) -> dict[str, Any]:
        started_at = time.monotonic()
        product = Product.objects.filter(pk=product_id, is_active=True).first()
        if product is None:
            failed = self._set_state(
                product_id,
                {
                    "status": "failed",
                    "error_code": "invalid_source",
                    "message": self.SAFE_STATUS_MESSAGES["invalid_source"],
                    "retryable": False,
                },
            )
            self._observe("unknown", "invalid_source", started_at)
            return failed
        target = self._target(product)
        if target is None:
            failed = self._set_state(
                product_id,
                {"status": "not_eligible", "retryable": False},
            )
            self._observe("unknown", "not_eligible", started_at)
            return failed

        self._set_state(
            product_id,
            {"status": "running", "source": target.parser_key, "retryable": False},
        )
        verifier = SourceOfferVerificationService()
        try:
            single_offer = target.parser_key in SINGLE_OFFER_REFRESH_SOURCES
            if single_offer:
                scraped = self._single_offer_product(target, verifier)
            else:
                if verifier.circuit_is_open(target.parser_key):
                    raise ProductCardRefreshError(
                        "source_unavailable", "Supplier circuit is open", retryable=True
                    )
                if not verifier._rate_allowed(target.parser_key):
                    raise ProductCardRefreshError(
                        "rate_limited", "Supplier rate limit reached", retryable=True
                    )

                timeout = self._request_timeout(target.parser_key)
                retries = _setting_int(
                    "PRODUCT_CARD_SOURCE_REFRESH_MAX_RETRIES",
                    1,
                    minimum=0,
                    maximum=2,
                )
                slot_ttl = max(10, math.ceil(timeout * (retries + 1) + 5))
                with verifier._source_slot(target.parser_key, slot_ttl) as acquired:
                    if not acquired:
                        raise ProductCardRefreshError(
                            "rate_limited", "Supplier concurrency limit reached", retryable=True
                        )
                    try:
                        scraped = self._fetch_product(target)
                    except ProductCardRefreshError:
                        raise
                    except Exception as exc:
                        raise ProductCardRefreshError(
                            "source_unavailable",
                            "Supplier request failed",
                            retryable=True,
                        ) from exc
            snapshots = self._validated_snapshots(target, scraped)
            result = self._reconcile(
                target,
                scraped,
                snapshots,
                offers_already_persisted=single_offer,
            )
            verifier._record_circuit_success(target.parser_key)
            if PRODUCT_CARD_REFRESH_CHANGES is not None:
                if result["price_changed"]:
                    PRODUCT_CARD_REFRESH_CHANGES.labels(
                        source=target.parser_key, field="price"
                    ).inc()
                for field in ("variants_created", "variants_updated", "sizes_created", "sizes_updated"):
                    if result[field]:
                        PRODUCT_CARD_REFRESH_CHANGES.labels(
                            source=target.parser_key, field=field
                        ).inc(result[field])
            succeeded = self._set_state(
                product_id,
                {
                    "status": "succeeded",
                    "source": target.parser_key,
                    "retryable": False,
                    "checked_at": timezone.now().isoformat(),
                    "changes": result,
                },
            )
            logger.info(
                "product_card_source_refresh",
                extra={
                    "product_id": product_id,
                    "source": target.parser_key,
                    "outcome": "succeeded",
                    "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
                    **result,
                },
            )
            self._observe(target.parser_key, "succeeded", started_at)
            return succeeded
        except ProductCardRefreshError as exc:
            unavailable_changes: dict[str, int] | None = None
            if exc.code == "source_not_found":
                try:
                    unavailable_changes = self._mark_source_url_unavailable(target)
                except Exception:
                    logger.exception(
                        "product_card_source_unavailable_persist_failed",
                        extra={
                            "product_id": product_id,
                            "source": target.parser_key,
                        },
                    )
            if exc.retryable and target.parser_key not in SINGLE_OFFER_REFRESH_SOURCES:
                verifier._record_circuit_failure(target.parser_key)
            failed = self._set_state(
                product_id,
                {
                    "status": "failed",
                    "source": target.parser_key,
                    "error_code": exc.code,
                    "message": self.SAFE_STATUS_MESSAGES.get(
                        exc.code, self.SAFE_STATUS_MESSAGES["internal_error"]
                    ),
                    "retryable": exc.retryable,
                    **({"changes": unavailable_changes} if unavailable_changes is not None else {}),
                },
                timeout=(
                    _setting_int(
                        "PRODUCT_CARD_SOURCE_REFRESH_ERROR_TTL_SECONDS",
                        30,
                        minimum=5,
                        maximum=300,
                    )
                    if exc.retryable
                    else None
                ),
            )
            logger.warning(
                "product_card_source_refresh_failed",
                extra={
                    "product_id": product_id,
                    "source": target.parser_key,
                    "error_code": exc.code,
                    "retryable": exc.retryable,
                    "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
                },
            )
            self._observe(target.parser_key, exc.code, started_at)
            return failed
        except Exception:
            logger.exception(
                "product_card_source_refresh_unexpected",
                extra={"product_id": product_id, "source": target.parser_key},
            )
            failed = self._set_state(
                product_id,
                {
                    "status": "failed",
                    "source": target.parser_key,
                    "error_code": "internal_error",
                    "message": self.SAFE_STATUS_MESSAGES["internal_error"],
                    "retryable": True,
                },
                timeout=_setting_int(
                    "PRODUCT_CARD_SOURCE_REFRESH_ERROR_TTL_SECONDS",
                    30,
                    minimum=5,
                    maximum=300,
                ),
            )
            self._observe(target.parser_key, "internal_error", started_at)
            return failed
