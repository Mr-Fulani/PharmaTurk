"""Resilient service boundary for live verification of saved supplier offers."""

from __future__ import annotations

import logging
import math
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterator
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from django.utils import timezone

from apps.catalog.models import ProductSourceOffer
from apps.scrapers.base.offers import (
    MalformedOfferResponse,
    OfferAvailability,
    OfferCheckContext,
    OfferCheckError,
    OfferCheckErrorCode,
    OfferCheckResult,
    OfferStockPrecision,
    OfferVerificationError,
)
from apps.scrapers.base.scraper import BaseScraper
from apps.scrapers.parsers.registry import get_parser

try:
    from prometheus_client import Counter, Histogram

    SOURCE_OFFER_CHECKS = Counter(
        "source_offer_verification_total",
        "Live supplier offer checks",
        ("source", "outcome"),
    )
    SOURCE_OFFER_LATENCY = Histogram(
        "source_offer_verification_seconds",
        "Live supplier offer check latency",
        ("source",),
    )
    SOURCE_OFFER_CHANGES = Counter(
        "source_offer_verification_changes_total",
        "Supplier offer values changed during live verification",
        ("source", "field"),
    )
except (ImportError, ValueError):  # pragma: no cover - metrics are optional in dev reloads
    SOURCE_OFFER_CHECKS = None
    SOURCE_OFFER_LATENCY = None
    SOURCE_OFFER_CHANGES = None


logger = logging.getLogger(__name__)
CACHE_VERSION = "v1"


def _setting_int(name: str, default: int, *, minimum: int = 0, maximum: int = 10000) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _setting_float(
    name: str,
    default: float,
    *,
    minimum: float = 0.0,
    maximum: float = 60.0,
) -> float:
    try:
        value = float(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _source_setting(mapping_name: str, default_name: str, parser_key: str, default: int) -> int:
    mapping = getattr(settings, mapping_name, {}) or {}
    raw = mapping.get(parser_key, getattr(settings, default_name, default))
    try:
        return max(0, min(int(raw), 10000))
    except (TypeError, ValueError):
        return default


def _cache_get(key: str):
    try:
        return cache.get(key)
    except Exception:
        logger.exception("source_offer_cache_get_failed", extra={"cache_key": key})
        return None


def _cache_set(key: str, value: Any, timeout: int) -> None:
    try:
        cache.set(key, value, timeout=max(timeout, 1))
    except Exception:
        logger.exception("source_offer_cache_set_failed", extra={"cache_key": key})


def _cache_add(key: str, value: Any, timeout: int) -> bool:
    try:
        return bool(cache.add(key, value, timeout=max(timeout, 1)))
    except Exception:
        logger.exception("source_offer_cache_add_failed", extra={"cache_key": key})
        # Cache degradation must not make every source unverifiable.
        return True


def _cache_delete_if_owned(key: str, token: str) -> None:
    try:
        if cache.get(key) == token:
            cache.delete(key)
    except Exception:
        logger.exception("source_offer_cache_unlock_failed", extra={"cache_key": key})


def _serialize_result(result: OfferCheckResult) -> dict[str, Any]:
    error = None
    if result.error is not None:
        error = {
            "code": result.error.code.value,
            "message": result.error.message,
            "retryable": result.error.retryable,
            "http_status": result.error.http_status,
        }
    return {
        "availability_status": result.availability_status.value,
        "stock_precision": result.stock_precision.value,
        "canonical_url": result.canonical_url,
        "source_price": str(result.source_price) if result.source_price is not None else None,
        "source_currency": result.source_currency,
        "stock_quantity": result.stock_quantity,
        "checked_at": result.checked_at.isoformat(),
        "error": error,
        "response_metadata": result.response_metadata,
    }


def _deserialize_result(payload: Any) -> OfferCheckResult | None:
    if not isinstance(payload, dict):
        return None
    try:
        error_payload = payload.get("error")
        error = None
        if isinstance(error_payload, dict):
            error = OfferCheckError(
                code=OfferCheckErrorCode(error_payload["code"]),
                message=str(error_payload.get("message") or ""),
                retryable=bool(error_payload.get("retryable")),
                http_status=error_payload.get("http_status"),
            )
        price = payload.get("source_price")
        return OfferCheckResult(
            availability_status=OfferAvailability(payload["availability_status"]),
            stock_precision=OfferStockPrecision(payload["stock_precision"]),
            canonical_url=str(payload.get("canonical_url") or ""),
            source_price=Decimal(str(price)) if price is not None else None,
            source_currency=str(payload.get("source_currency") or ""),
            stock_quantity=payload.get("stock_quantity"),
            checked_at=datetime.fromisoformat(payload["checked_at"]),
            error=error,
            response_metadata=(
                payload.get("response_metadata")
                if isinstance(payload.get("response_metadata"), dict)
                else {}
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None


class SourceOfferVerificationService:
    """Verify a persisted offer with cache, isolation and source-level guards."""

    def is_enabled_for(self, parser_key: str) -> bool:
        if not bool(getattr(settings, "SOURCE_OFFER_VERIFICATION_ENABLED", False)):
            return False
        allowed = {
            str(value or "").strip().casefold()
            for value in (getattr(settings, "SOURCE_OFFER_VERIFICATION_SOURCES", []) or [])
            if str(value or "").strip()
        }
        return not allowed or parser_key.casefold() in allowed

    @staticmethod
    def _context(offer: ProductSourceOffer) -> OfferCheckContext:
        return OfferCheckContext(
            canonical_url=offer.canonical_url,
            external_product_id=offer.external_product_id,
            external_sku=offer.external_sku,
            variant_key=offer.variant_key,
            size_key=offer.size_key,
            selected_options=(
                offer.selected_options if isinstance(offer.selected_options, dict) else {}
            ),
            parser_config=(offer.parser_config if isinstance(offer.parser_config, dict) else {}),
        )

    @staticmethod
    def _failure_result(
        context: OfferCheckContext,
        error: OfferCheckError,
    ) -> OfferCheckResult:
        if error.code == OfferCheckErrorCode.GONE:
            availability = OfferAvailability.DISCONTINUED
        elif error.code in {
            OfferCheckErrorCode.NOT_FOUND,
            OfferCheckErrorCode.OPTION_NOT_FOUND,
        }:
            availability = OfferAvailability.OUT_OF_STOCK
        elif error.code in {
            OfferCheckErrorCode.DISABLED,
            OfferCheckErrorCode.UNSUPPORTED,
        }:
            availability = OfferAvailability.UNSUPPORTED
        else:
            availability = OfferAvailability.SOURCE_UNREACHABLE
        return OfferCheckResult(
            availability_status=availability,
            stock_precision=OfferStockPrecision.UNKNOWN,
            canonical_url=context.canonical_url,
            error=error,
        )

    @staticmethod
    def _error(
        code: OfferCheckErrorCode,
        message: str,
        *,
        retryable: bool,
        http_status: int | None = None,
    ) -> OfferCheckError:
        return OfferCheckError(
            code=code,
            message=message,
            retryable=retryable,
            http_status=http_status,
        )

    def _trusted_parser_class(self, offer: ProductSourceOffer):
        parsed = urlparse(str(offer.canonical_url or ""))
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        source_domain = str(offer.source_domain or "").casefold().rstrip(".")
        if (
            parsed.scheme.casefold() != "https"
            or not hostname
            or parsed.username
            or parsed.password
            or hostname != source_domain
        ):
            return None
        parser_class = get_parser(str(offer.parser_key or "").casefold())
        url_parser_class = get_parser(offer.canonical_url)
        if parser_class is None or url_parser_class is not parser_class:
            return None
        return parser_class

    def supports_offer(self, offer: ProductSourceOffer) -> bool:
        """Return whether an offer has an enabled, explicit live-check adapter."""

        parser_key = str(getattr(offer, "parser_key", "") or "").strip().casefold()
        if not self.is_enabled_for(parser_key):
            return False
        parser_class = self._trusted_parser_class(offer)
        return bool(
            parser_class is not None
            and getattr(parser_class, "check_offer", None) is not BaseScraper.check_offer
        )

    @staticmethod
    def _redirect_is_trusted(parser_class, canonical_url: str) -> bool:
        parsed = urlparse(str(canonical_url or ""))
        if parsed.scheme.casefold() != "https" or not parsed.hostname:
            return False
        if parsed.username or parsed.password:
            return False
        return get_parser(canonical_url) is parser_class

    @staticmethod
    def _cache_key(offer: ProductSourceOffer) -> str:
        return f"source-offer:result:{CACHE_VERSION}:{offer.pk}:{offer.offer_key}"

    @staticmethod
    def _lock_key(offer: ProductSourceOffer) -> str:
        return f"source-offer:lock:{CACHE_VERSION}:{offer.pk}:{offer.offer_key}"

    @staticmethod
    def _circuit_key(parser_key: str) -> str:
        return f"source-offer:circuit:{CACHE_VERSION}:{parser_key}"

    @staticmethod
    def _failure_count_key(parser_key: str) -> str:
        return f"source-offer:failures:{CACHE_VERSION}:{parser_key}"

    def _circuit_is_open(self, parser_key: str) -> bool:
        return bool(_cache_get(self._circuit_key(parser_key)))

    def circuit_is_open(self, parser_key: str) -> bool:
        """Return read-only circuit state for operational diagnostics."""

        return self._circuit_is_open(str(parser_key or "").strip().casefold())

    def _record_circuit_success(self, parser_key: str) -> None:
        try:
            cache.delete(self._failure_count_key(parser_key))
            cache.delete(self._circuit_key(parser_key))
        except Exception:
            logger.exception("source_offer_circuit_reset_failed", extra={"source": parser_key})

    def _record_circuit_failure(self, parser_key: str) -> None:
        threshold = _setting_int(
            "SOURCE_OFFER_CIRCUIT_FAILURE_THRESHOLD",
            5,
            minimum=1,
            maximum=100,
        )
        failure_key = self._failure_count_key(parser_key)
        recovery = _setting_int(
            "SOURCE_OFFER_CIRCUIT_RECOVERY_SECONDS",
            60,
            minimum=1,
            maximum=3600,
        )
        try:
            if cache.add(failure_key, 1, timeout=recovery):
                failures = 1
            else:
                failures = int(cache.incr(failure_key))
            if failures >= threshold:
                cache.set(self._circuit_key(parser_key), True, timeout=recovery)
        except Exception:
            logger.exception("source_offer_circuit_record_failed", extra={"source": parser_key})

    def _rate_allowed(self, parser_key: str) -> bool:
        limit = _source_setting(
            "SOURCE_OFFER_SOURCE_RATE_PER_MINUTE",
            "SOURCE_OFFER_DEFAULT_RATE_PER_MINUTE",
            parser_key,
            60,
        )
        if limit <= 0:
            return True
        window = int(time.time() // 60)
        key = f"source-offer:rate:{CACHE_VERSION}:{parser_key}:{window}"
        try:
            if cache.add(key, 1, timeout=70):
                count = 1
            else:
                count = int(cache.incr(key))
            return count <= limit
        except Exception:
            logger.exception("source_offer_rate_limit_failed", extra={"source": parser_key})
            return True

    @contextmanager
    def _source_slot(self, parser_key: str, ttl: int) -> Iterator[bool]:
        limit = _source_setting(
            "SOURCE_OFFER_SOURCE_CONCURRENCY",
            "SOURCE_OFFER_DEFAULT_CONCURRENCY",
            parser_key,
            4,
        )
        if limit <= 0:
            yield True
            return
        token = uuid.uuid4().hex
        acquired_key = ""
        for index in range(limit):
            key = f"source-offer:slot:{CACHE_VERSION}:{parser_key}:{index}"
            if _cache_add(key, token, ttl):
                acquired_key = key
                break
        try:
            yield bool(acquired_key)
        finally:
            if acquired_key:
                _cache_delete_if_owned(acquired_key, token)

    def _wait_for_singleflight(self, cache_key: str) -> OfferCheckResult | None:
        wait_seconds = _setting_float(
            "SOURCE_OFFER_SINGLEFLIGHT_WAIT_SECONDS",
            0.5,
            maximum=3.0,
        )
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            cached = _deserialize_result(_cache_get(cache_key))
            if cached is not None:
                return cached
            time.sleep(min(0.05, max(deadline - time.monotonic(), 0)))
        return None

    def _run_parser_check(
        self,
        parser_class,
        parser_key: str,
        context: OfferCheckContext,
    ) -> OfferCheckResult:
        timeout = _setting_float(
            "SOURCE_OFFER_REQUEST_TIMEOUT_SECONDS",
            5.0,
            minimum=0.25,
            maximum=15.0,
        )
        retries = _setting_int("SOURCE_OFFER_MAX_RETRIES", 1, maximum=2)
        backoff = _setting_float(
            "SOURCE_OFFER_RETRY_BACKOFF_SECONDS",
            0.1,
            maximum=1.0,
        )
        origin = f"https://{urlparse(context.canonical_url).netloc}"
        parser_kwargs: dict[str, Any] = {
            "timeout": timeout,
            "max_retries": 0,
        }
        if self._proxy_enabled_for(parser_key, context):
            parser_kwargs["use_proxy"] = True
        last_error: OfferVerificationError | None = None
        for attempt in range(retries + 1):
            try:
                with parser_class(
                    origin,
                    **parser_kwargs,
                ) as parser:
                    result = parser.check_offer(context)
                if result.error is not None:
                    raise OfferVerificationError(
                        result.error.code,
                        result.error.message,
                        retryable=result.error.retryable,
                        http_status=result.error.http_status,
                    )
                if result.source_price is None:
                    raise MalformedOfferResponse("Source response does not contain current price")
                if not self._redirect_is_trusted(parser_class, result.canonical_url):
                    raise OfferVerificationError(
                        OfferCheckErrorCode.INVALID_SOURCE,
                        "Supplier redirected offer to an untrusted domain",
                        retryable=False,
                    )
                return result
            except OfferVerificationError as exc:
                last_error = exc
                if not exc.error.retryable or attempt >= retries:
                    raise
                if backoff > 0:
                    time.sleep(backoff * (attempt + 1))
        if last_error is not None:  # pragma: no cover - loop always raises/returns
            raise last_error
        raise MalformedOfferResponse()

    @staticmethod
    def _proxy_enabled_for(parser_key: str, context: OfferCheckContext) -> bool:
        """Use only the proxy policy of a matching, active server-side config.

        Historical backfill offers do not have ``scraper_config_id``. For those
        rows the exact parser key is a safe fallback: the config and proxy URL
        remain server-owned, while the client cannot submit either value.
        """

        if not str(getattr(settings, "SCRAPER_PROXY_URL", "") or "").strip():
            return False

        payload = context.parser_config if isinstance(context.parser_config, dict) else {}
        saved_parser_key = str(payload.get("parser_class") or "").strip().casefold()
        if saved_parser_key and saved_parser_key != parser_key:
            return False

        try:
            from apps.scrapers.models import ScraperConfig

            configs = ScraperConfig.objects.filter(
                is_enabled=True,
                status="active",
            )
            raw_config_id = payload.get("scraper_config_id")
            if raw_config_id not in (None, ""):
                try:
                    config_id = int(raw_config_id)
                except (TypeError, ValueError):
                    return False
                config = (
                    configs.filter(pk=config_id)
                    .only(
                        "parser_class",
                        "use_proxy",
                    )
                    .first()
                )
            else:
                config = (
                    configs.filter(parser_class__iexact=parser_key)
                    .order_by("priority", "pk")
                    .only("parser_class", "use_proxy")
                    .first()
                )
        except Exception:
            logger.exception(
                "source_offer_proxy_config_failed",
                extra={"source": parser_key},
            )
            return False

        if config is None:
            return False
        if str(config.parser_class or "").strip().casefold() != parser_key:
            return False
        return bool(config.use_proxy)

    @staticmethod
    def _persist_success(offer: ProductSourceOffer, result: OfferCheckResult) -> None:
        now = result.checked_at
        source_domain = (
            (urlparse(result.canonical_url).hostname or offer.source_domain).casefold().rstrip(".")
        )
        values = {
            "canonical_url": result.canonical_url,
            "source_domain": source_domain,
            "source_price": result.source_price,
            "source_currency": result.source_currency,
            "availability_status": result.availability_status.value,
            "stock_precision": result.stock_precision.value,
            "stock_quantity": result.stock_quantity,
            "last_checked_at": now,
            "last_successful_check_at": now,
            "last_error_code": "",
            "last_error_message": "",
            "consecutive_failures": 0,
            "response_metadata": result.response_metadata,
            "updated_at": timezone.now(),
        }
        ProductSourceOffer.objects.filter(pk=offer.pk).update(**values)
        for field_name, value in values.items():
            setattr(offer, field_name, value)

    @staticmethod
    def _observe_changes(offer: ProductSourceOffer, result: OfferCheckResult) -> None:
        changed_fields = []
        if offer.source_price != result.source_price:
            changed_fields.append("price")
        if offer.availability_status != result.availability_status.value:
            changed_fields.append("availability")
        if (
            offer.stock_precision != result.stock_precision.value
            or offer.stock_quantity != result.stock_quantity
        ):
            changed_fields.append("stock")
        for field_name in changed_fields:
            if SOURCE_OFFER_CHANGES is not None:
                SOURCE_OFFER_CHANGES.labels(
                    source=offer.parser_key,
                    field=field_name,
                ).inc()
        if changed_fields:
            logger.info(
                "source_offer_values_changed",
                extra={
                    "source": offer.parser_key,
                    "offer_id": offer.pk,
                    "changed_fields": changed_fields,
                },
            )

    @staticmethod
    def _persist_failure(offer: ProductSourceOffer, result: OfferCheckResult) -> None:
        if result.error is None:
            return
        values: dict[str, Any] = {
            "availability_status": result.availability_status.value,
            "stock_precision": OfferStockPrecision.UNKNOWN.value,
            "stock_quantity": None,
            "last_checked_at": result.checked_at,
            "last_error_code": result.error.code.value,
            "last_error_message": result.error.message[:2000],
            "updated_at": timezone.now(),
        }
        if result.error.retryable:
            values["consecutive_failures"] = F("consecutive_failures") + 1
        else:
            values["consecutive_failures"] = 0
        ProductSourceOffer.objects.filter(pk=offer.pk).update(**values)

    @staticmethod
    def _observe(parser_key: str, outcome: str, started_at: float) -> None:
        duration = max(time.monotonic() - started_at, 0.0)
        if SOURCE_OFFER_CHECKS is not None:
            SOURCE_OFFER_CHECKS.labels(source=parser_key, outcome=outcome).inc()
        if SOURCE_OFFER_LATENCY is not None:
            SOURCE_OFFER_LATENCY.labels(source=parser_key).observe(duration)
        logger.info(
            "source_offer_verification",
            extra={
                "source": parser_key,
                "outcome": outcome,
                "duration_ms": round(duration * 1000, 2),
            },
        )

    def verify(
        self,
        offer: ProductSourceOffer,
        *,
        force: bool = False,
    ) -> OfferCheckResult:
        """Verify one persisted offer. No URL or option comes from a client payload."""
        started_at = time.monotonic()
        parser_key = str(getattr(offer, "parser_key", "") or "").strip().casefold()
        context = self._context(offer)

        if not self.is_enabled_for(parser_key):
            result = self._failure_result(
                context,
                self._error(
                    OfferCheckErrorCode.DISABLED,
                    "Live source verification is disabled",
                    retryable=False,
                ),
            )
            self._observe(parser_key or "unknown", "disabled", started_at)
            return result
        if not offer.pk or not offer.is_active:
            result = self._failure_result(
                context,
                self._error(
                    OfferCheckErrorCode.INVALID_SOURCE,
                    "Source offer is not persisted and active",
                    retryable=False,
                ),
            )
            self._observe(parser_key or "unknown", "invalid_source", started_at)
            return result

        parser_class = self._trusted_parser_class(offer)
        if parser_class is None:
            result = self._failure_result(
                context,
                self._error(
                    OfferCheckErrorCode.INVALID_SOURCE,
                    "Saved source URL does not match parser registry/domain",
                    retryable=False,
                ),
            )
            self._persist_failure(offer, result)
            self._observe(parser_key, "invalid_source", started_at)
            return result

        cache_key = self._cache_key(offer)
        if not force:
            cached = _deserialize_result(_cache_get(cache_key))
            if cached is not None:
                self._observe(parser_key, "cache_hit", started_at)
                return cached

        if self._circuit_is_open(parser_key):
            result = self._failure_result(
                context,
                self._error(
                    OfferCheckErrorCode.CIRCUIT_OPEN,
                    "Supplier circuit breaker is open",
                    retryable=True,
                ),
            )
            self._observe(parser_key, "circuit_open", started_at)
            return result
        if not self._rate_allowed(parser_key):
            result = self._failure_result(
                context,
                self._error(
                    OfferCheckErrorCode.RATE_LIMITED,
                    "Supplier verification rate limit reached",
                    retryable=True,
                ),
            )
            self._observe(parser_key, "rate_limited", started_at)
            return result

        timeout = _setting_float("SOURCE_OFFER_REQUEST_TIMEOUT_SECONDS", 5.0, maximum=15.0)
        retries = _setting_int("SOURCE_OFFER_MAX_RETRIES", 1, maximum=2)
        lock_ttl = max(5, math.ceil(timeout * (retries + 1) + 3))
        lock_key = self._lock_key(offer)
        lock_token = uuid.uuid4().hex
        if not _cache_add(lock_key, lock_token, lock_ttl):
            cached = self._wait_for_singleflight(cache_key)
            if cached is not None:
                self._observe(parser_key, "singleflight_hit", started_at)
                return cached
            result = self._failure_result(
                context,
                self._error(
                    OfferCheckErrorCode.IN_PROGRESS,
                    "The same source offer is already being verified",
                    retryable=True,
                ),
            )
            self._observe(parser_key, "in_progress", started_at)
            return result

        try:
            with self._source_slot(parser_key, lock_ttl) as slot_acquired:
                if not slot_acquired:
                    result = self._failure_result(
                        context,
                        self._error(
                            OfferCheckErrorCode.RATE_LIMITED,
                            "Supplier verification concurrency limit reached",
                            retryable=True,
                        ),
                    )
                    self._observe(parser_key, "concurrency_limited", started_at)
                    return result
                try:
                    result = self._run_parser_check(parser_class, parser_key, context)
                except OfferVerificationError as exc:
                    result = self._failure_result(context, exc.error)
                except Exception as exc:
                    logger.exception(
                        "source_offer_unexpected_parser_error",
                        extra={"source": parser_key, "offer_id": offer.pk},
                    )
                    result = self._failure_result(
                        context,
                        self._error(
                            OfferCheckErrorCode.MALFORMED_RESPONSE,
                            str(exc) or "Unexpected parser error",
                            retryable=False,
                        ),
                    )

            if result.is_success:
                self._record_circuit_success(parser_key)
                self._observe_changes(offer, result)
                self._persist_success(offer, result)
                ttl = _setting_int(
                    "SOURCE_OFFER_SUCCESS_CACHE_TTL",
                    120,
                    minimum=1,
                    maximum=3600,
                )
                outcome = "success"
            else:
                if result.error and result.error.retryable:
                    self._record_circuit_failure(parser_key)
                self._persist_failure(offer, result)
                ttl = _setting_int(
                    "SOURCE_OFFER_ERROR_CACHE_TTL",
                    15,
                    minimum=1,
                    maximum=300,
                )
                outcome = result.error.code.value if result.error else "error"
            _cache_set(cache_key, _serialize_result(result), ttl)
            self._observe(parser_key, outcome, started_at)
            return result
        finally:
            _cache_delete_if_owned(lock_key, lock_token)
