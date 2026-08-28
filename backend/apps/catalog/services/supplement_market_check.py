"""On-demand reference-price checks for dietary supplements.

The source price observation and the sellable-stock contract are intentionally
separate. IlacFiyati is accepted only as a trusted reference-price catalogue. It
must never update availability, stock, or create a payable cart line.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator
from urllib.parse import urlparse

import httpx
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import (
    PriceHistory,
    ProductMarketCheck,
    SupplementProduct,
)
from apps.scrapers.base.scraper import ScraperAccessBlockedError
from apps.scrapers.models import ScraperConfig
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiSourceError
from apps.scrapers.parsers.registry import get_parser

logger = logging.getLogger(__name__)

CACHE_VERSION = "v1"
ACTIVE_STATUSES = {
    ProductMarketCheck.Status.PENDING,
    ProductMarketCheck.Status.RUNNING,
}

try:
    from prometheus_client import Counter, Histogram

    SUPPLEMENT_MARKET_CHECKS = Counter(
        "supplement_market_checks_total",
        "On-demand supplement reference-price checks",
        ("source", "outcome"),
    )
    SUPPLEMENT_MARKET_LATENCY = Histogram(
        "supplement_market_check_seconds",
        "On-demand supplement market-check latency",
        ("source",),
    )
except (ImportError, ValueError):  # pragma: no cover - optional during dev reloads
    SUPPLEMENT_MARKET_CHECKS = None
    SUPPLEMENT_MARKET_LATENCY = None


def _setting_int(name: str, default: int, *, minimum: int = 0, maximum: int = 86400) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _allowed_sources() -> set[str]:
    return {
        str(value or "").strip().casefold()
        for value in (getattr(settings, "SUPPLEMENT_MARKET_CHECK_SOURCES", ["ilacfiyati"]) or [])
        if str(value or "").strip()
    }


def _safe_cache_add(key: str, token: str, timeout: int) -> tuple[bool, bool]:
    try:
        return bool(cache.add(key, token, timeout=max(1, timeout))), True
    except Exception:
        logger.exception("supplement_market_cache_add_failed", extra={"cache_key": key})
        return False, False


def _cache_delete_if_owned(key: str, token: str) -> None:
    try:
        if cache.get(key) == token:
            cache.delete(key)
    except Exception:
        logger.exception("supplement_market_cache_unlock_failed", extra={"cache_key": key})


class SupplementMarketCheckError(RuntimeError):
    def __init__(self, code: str, message: str, *, http_status: int = 503):
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.http_status = http_status


@dataclass(frozen=True)
class TrustedSupplementSource:
    key: str
    url: str
    parser_class: type
    config: ScraperConfig


@dataclass(frozen=True)
class SupplementMarketRequestResult:
    check: ProductMarketCheck
    queued: bool
    cached: bool


class SupplementMarketCheckService:
    """Create, execute and serialize bounded supplement price observations."""

    def is_enabled(self) -> bool:
        return bool(getattr(settings, "SUPPLEMENT_MARKET_CHECK_ENABLED", False))

    @staticmethod
    def _source_candidates(supplement: SupplementProduct) -> list[str]:
        base = supplement.base_product
        candidates: list[str] = []
        for direct in (
            supplement.external_url,
            getattr(base, "external_url", "") if base else "",
        ):
            value = str(direct or "").strip()
            if value and value not in candidates:
                candidates.append(value)

        for payload in (
            supplement.external_data,
            getattr(base, "external_data", {}) if base else {},
        ):
            if not isinstance(payload, dict):
                continue
            rows = payload.get("scraped_sources") or []
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                value = str(row.get("url") or "").strip()
                if value and value not in candidates:
                    candidates.append(value)
        return candidates

    @staticmethod
    def _canonical_ilacfiyati_supplement_url(url: str) -> str | None:
        try:
            parsed = urlparse(str(url or "").strip())
            port = parsed.port
        except ValueError:
            return None
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if (
            parsed.scheme.casefold() != "https"
            or parsed.username
            or parsed.password
            or port not in {None, 443}
            or hostname not in {"ilacfiyati.com", "www.ilacfiyati.com"}
            or len(parts) < 2
            or parts[0] != "takviye-edici-gida"
            or not all(char.isalnum() or char in {"-", "_"} for char in parts[1])
        ):
            return None
        return f"https://ilacfiyati.com/takviye-edici-gida/{parts[1]}"

    def resolve_source(self, supplement: SupplementProduct) -> TrustedSupplementSource:
        if not self.is_enabled():
            raise SupplementMarketCheckError(
                "disabled",
                "Проверка актуальной цены временно отключена.",
            )
        if not supplement.base_product_id:
            raise SupplementMarketCheckError(
                "missing_product_identity",
                "Для БАДа не настроена проверка источника.",
                http_status=409,
            )
        if "ilacfiyati" not in _allowed_sources():
            raise SupplementMarketCheckError(
                "source_disabled",
                "Источник справочной цены временно отключён.",
            )

        parser_class = get_parser("ilacfiyati")
        if parser_class is None:
            raise SupplementMarketCheckError(
                "parser_unavailable",
                "Проверка этого источника сейчас недоступна.",
            )

        source_url = None
        for candidate in self._source_candidates(supplement):
            canonical = self._canonical_ilacfiyati_supplement_url(candidate)
            if canonical and get_parser(canonical) is parser_class:
                source_url = canonical
                break
        if not source_url:
            raise SupplementMarketCheckError(
                "invalid_source",
                "Для БАДа не найдена доверенная карточка первоисточника.",
                http_status=409,
            )

        config = (
            ScraperConfig.objects.filter(
                parser_class__iexact="ilacfiyati",
                is_enabled=True,
                status="active",
            )
            .order_by("priority", "pk")
            .first()
        )
        if config is None:
            raise SupplementMarketCheckError(
                "source_not_configured",
                "Источник актуальной цены ещё не настроен.",
            )
        return TrustedSupplementSource(
            key="ilacfiyati",
            url=source_url,
            parser_class=parser_class,
            config=config,
        )

    @staticmethod
    def _fresh(check: ProductMarketCheck, now) -> bool:
        success_ttl = _setting_int(
            "SUPPLEMENT_MARKET_CHECK_FRESH_SECONDS",
            43200,
            minimum=60,
            maximum=604800,
        )
        error_ttl = _setting_int(
            "SUPPLEMENT_MARKET_CHECK_ERROR_FRESH_SECONDS",
            300,
            minimum=0,
            maximum=3600,
        )
        if (
            check.status == ProductMarketCheck.Status.SUCCEEDED
            and check.last_success_at
            and check.last_success_at >= now - timedelta(seconds=success_ttl)
        ):
            return True
        return bool(
            check.status
            in {
                ProductMarketCheck.Status.SOURCE_UNAVAILABLE,
                ProductMarketCheck.Status.FAILED,
            }
            and check.finished_at
            and check.finished_at >= now - timedelta(seconds=error_ttl)
        )

    @staticmethod
    def _active(check: ProductMarketCheck, now) -> bool:
        stale_seconds = _setting_int(
            "SUPPLEMENT_MARKET_CHECK_STALE_RUNNING_SECONDS",
            180,
            minimum=30,
            maximum=1800,
        )
        marker = check.started_at or check.requested_at
        return bool(
            check.status in ACTIVE_STATUSES
            and marker
            and marker >= now - timedelta(seconds=stale_seconds)
        )

    @staticmethod
    def _global_rate_allowed(source: str) -> bool:
        limit = _setting_int(
            "SUPPLEMENT_MARKET_CHECK_GLOBAL_RATE_PER_MINUTE",
            10,
            minimum=1,
            maximum=300,
        )
        key = f"supplement-market:rate:{CACHE_VERSION}:{source}:{int(time.time() // 60)}"
        try:
            if cache.add(key, 1, timeout=70):
                count = 1
            else:
                count = int(cache.incr(key))
            return count <= limit
        except Exception:
            logger.exception("supplement_market_rate_limit_failed", extra={"source": source})
            return False

    def request_check(self, supplement: SupplementProduct) -> SupplementMarketRequestResult:
        source = self.resolve_source(supplement)
        now = timezone.now()
        lock_ttl = _setting_int(
            "SUPPLEMENT_MARKET_CHECK_ENQUEUE_LOCK_SECONDS",
            30,
            minimum=5,
            maximum=120,
        )
        lock_key = (
            f"supplement-market:enqueue:{CACHE_VERSION}:"
            f"{supplement.base_product_id}:{source.key}"
        )
        lock_token = uuid.uuid4().hex
        owns_lock = False

        try:
            with transaction.atomic():
                check, _ = ProductMarketCheck.objects.select_for_update().get_or_create(
                    product_id=supplement.base_product_id,
                    source=source.key,
                    defaults={"source_url": source.url},
                )

                is_fresh = self._fresh(check, now)
                is_active = self._active(check, now)
                check.request_count = int(check.request_count or 0) + 1
                check.requested_at = now
                check.source_url = source.url

                if is_fresh:
                    check.save(
                        update_fields=["request_count", "requested_at", "source_url", "updated_at"]
                    )
                    return SupplementMarketRequestResult(
                        check=check,
                        queued=False,
                        cached=True,
                    )

                if is_active:
                    check.save(
                        update_fields=["request_count", "requested_at", "source_url", "updated_at"]
                    )
                    return SupplementMarketRequestResult(
                        check=check,
                        queued=False,
                        cached=False,
                    )

                acquired, cache_healthy = _safe_cache_add(lock_key, lock_token, lock_ttl)
                if not cache_healthy:
                    raise SupplementMarketCheckError(
                        "guard_unavailable",
                        "Защита источника временно недоступна. Повторите позже.",
                    )
                if not acquired:
                    check.save(
                        update_fields=["request_count", "requested_at", "source_url", "updated_at"]
                    )
                    return SupplementMarketRequestResult(
                        check=check,
                        queued=False,
                        cached=False,
                    )
                owns_lock = True

                if not self._global_rate_allowed(source.key):
                    raise SupplementMarketCheckError(
                        "rate_limited",
                        "Слишком много проверок одновременно. Повторите немного позже.",
                        http_status=429,
                    )

                check.status = ProductMarketCheck.Status.PENDING
                check.started_at = None
                check.finished_at = None
                check.task_id = ""
                check.error_code = ""
                check.error_message = ""
                check.save(
                    update_fields=[
                        "source_url",
                        "status",
                        "request_count",
                        "requested_at",
                        "started_at",
                        "finished_at",
                        "task_id",
                        "error_code",
                        "error_message",
                        "updated_at",
                    ]
                )

            from apps.catalog.tasks import refresh_supplement_market_check_task

            try:
                async_result = refresh_supplement_market_check_task.apply_async(args=[check.pk])
            except Exception as exc:
                logger.exception(
                    "supplement_market_task_publish_failed",
                    extra={"check_id": check.pk, "source": source.key},
                )
                self._mark_failure(
                    check.pk,
                    status=ProductMarketCheck.Status.SOURCE_UNAVAILABLE,
                    code="queue_unavailable",
                    message="Проверку не удалось поставить в очередь. Повторите позже.",
                )
                raise SupplementMarketCheckError(
                    "queue_unavailable",
                    "Проверку не удалось запустить. Повторите позже.",
                ) from exc

            ProductMarketCheck.objects.filter(
                pk=check.pk,
                status=ProductMarketCheck.Status.PENDING,
                task_id="",
            ).update(task_id=str(async_result.id or "")[:100])
            check.refresh_from_db()
            return SupplementMarketRequestResult(check=check, queued=True, cached=False)
        finally:
            if owns_lock:
                _cache_delete_if_owned(lock_key, lock_token)

    @contextmanager
    def _source_slot(self, source: str) -> Iterator[bool]:
        limit = _setting_int(
            "SUPPLEMENT_MARKET_CHECK_SOURCE_CONCURRENCY",
            2,
            minimum=1,
            maximum=10,
        )
        ttl = _setting_int(
            "SUPPLEMENT_MARKET_CHECK_STALE_RUNNING_SECONDS",
            180,
            minimum=30,
            maximum=1800,
        )
        token = uuid.uuid4().hex
        acquired_key = ""
        cache_healthy = True
        for index in range(limit):
            key = f"supplement-market:slot:{CACHE_VERSION}:{source}:{index}"
            acquired, healthy = _safe_cache_add(key, token, ttl)
            cache_healthy = cache_healthy and healthy
            if acquired:
                acquired_key = key
                break
            if not healthy:
                break
        try:
            yield bool(acquired_key) and cache_healthy
        finally:
            if acquired_key:
                _cache_delete_if_owned(acquired_key, token)

    @staticmethod
    def _decimal_price(value: Any) -> Decimal:
        try:
            price = Decimal(str(value)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            raise SupplementMarketCheckError(
                "price_missing",
                "Источник не вернул корректную актуальную цену.",
                http_status=422,
            )
        if not price.is_finite() or price <= 0 or price > Decimal("999999999999.99"):
            raise SupplementMarketCheckError(
                "price_invalid",
                "Источник вернул некорректную актуальную цену.",
                http_status=422,
            )
        return price

    @staticmethod
    def _parser_for(source: TrustedSupplementSource):
        timeout = _setting_int(
            "SUPPLEMENT_MARKET_CHECK_REQUEST_TIMEOUT_SECONDS",
            15,
            minimum=3,
            maximum=30,
        )
        config = source.config
        parser = source.parser_class(
            config.base_url,
            delay_range=(config.delay_min, config.delay_max),
            timeout=timeout,
            max_retries=0,
            use_proxy=bool(config.use_proxy),
            username=config.scraper_username or None,
            password=config.scraper_password or None,
        )
        parser.configure_request_identity(
            user_agent=config.user_agent or None,
            headers=config.headers if isinstance(config.headers, dict) else None,
            cookies=config.cookies if isinstance(config.cookies, dict) else None,
        )
        return parser

    def _parse_snapshot(self, source: TrustedSupplementSource):
        with self._parser_for(source) as parser:
            parse_market_snapshot = getattr(parser, "parse_market_snapshot", None)
            if not callable(parse_market_snapshot):
                raise SupplementMarketCheckError(
                    "unsupported",
                    "Источник не поддерживает точечную проверку цены.",
                    http_status=409,
                )
            return parse_market_snapshot(source.url)

    def run(self, check_id: int) -> dict[str, Any]:
        started_monotonic = time.monotonic()
        with transaction.atomic():
            check = (
                ProductMarketCheck.objects.select_for_update()
                .select_related("product")
                .filter(pk=check_id)
                .first()
            )
            if check is None:
                return {"status": "missing", "check_id": check_id}
            if check.status != ProductMarketCheck.Status.PENDING:
                return {"status": check.status, "check_id": check.pk}
            check.status = ProductMarketCheck.Status.RUNNING
            check.started_at = timezone.now()
            check.finished_at = None
            check.save(update_fields=["status", "started_at", "finished_at", "updated_at"])
            supplement = SupplementProduct.objects.filter(base_product_id=check.product_id).first()

        if supplement is None or not supplement.is_active:
            self._mark_failure(
                check_id,
                status=ProductMarketCheck.Status.FAILED,
                code="supplement_unavailable",
                message="Карточка БАДа больше недоступна.",
            )
            return {"status": ProductMarketCheck.Status.FAILED, "check_id": check_id}

        source_key = check.source
        try:
            source = self.resolve_source(supplement)
            if source.key != check.source or source.url != check.source_url:
                raise SupplementMarketCheckError(
                    "source_changed",
                    "Источник БАДа изменился. Запустите новую проверку.",
                    http_status=409,
                )
            with self._source_slot(source.key) as slot_acquired:
                if not slot_acquired:
                    raise SupplementMarketCheckError(
                        "source_busy",
                        "Источник занят другими проверками. Повторите позже.",
                    )
                scraped = self._parse_snapshot(source)

            price = self._decimal_price(getattr(scraped, "price", None))
            currency = str(getattr(scraped, "currency", "") or "").strip().upper()
            if currency != "TRY":
                raise SupplementMarketCheckError(
                    "currency_invalid",
                    "Источник вернул цену в неожиданной валюте.",
                    http_status=422,
                )
            result = self._persist_success(
                check_id=check_id,
                price=price,
                currency=currency,
                source=source,
            )
            self._observe(source.key, "success", started_monotonic)
            return result
        except SoftTimeLimitExceeded:
            self._mark_failure(
                check_id,
                status=ProductMarketCheck.Status.SOURCE_UNAVAILABLE,
                code="timeout",
                message="Источник не успел ответить. Последняя подтверждённая цена сохранена.",
            )
            self._observe(source_key, "timeout", started_monotonic)
            return {"status": ProductMarketCheck.Status.SOURCE_UNAVAILABLE, "check_id": check_id}
        except SupplementMarketCheckError as exc:
            terminal_status = (
                ProductMarketCheck.Status.SOURCE_UNAVAILABLE
                if exc.code in {"source_busy", "guard_unavailable"}
                else ProductMarketCheck.Status.FAILED
            )
            self._mark_failure(
                check_id,
                status=terminal_status,
                code=exc.code,
                message=exc.public_message,
            )
            self._observe(source_key, exc.code, started_monotonic)
            return {"status": terminal_status, "check_id": check_id, "error_code": exc.code}
        except (ScraperAccessBlockedError, httpx.HTTPError) as exc:
            logger.warning(
                "supplement_market_source_unavailable",
                extra={
                    "check_id": check_id,
                    "source": source_key,
                    "error_type": type(exc).__name__,
                },
            )
            self._mark_failure(
                check_id,
                status=ProductMarketCheck.Status.SOURCE_UNAVAILABLE,
                code="source_unavailable",
                message="Источник временно недоступен. Последняя подтверждённая цена сохранена.",
            )
            self._observe(source_key, "source_unavailable", started_monotonic)
            return {"status": ProductMarketCheck.Status.SOURCE_UNAVAILABLE, "check_id": check_id}
        except IlacFiyatiSourceError:
            logger.warning(
                "supplement_market_malformed_source",
                extra={"check_id": check_id, "source": source_key},
            )
            self._mark_failure(
                check_id,
                status=ProductMarketCheck.Status.FAILED,
                code="malformed_response",
                message="Источник не вернул данные БАДа в ожидаемом формате.",
            )
            self._observe(source_key, "malformed_response", started_monotonic)
            return {"status": ProductMarketCheck.Status.FAILED, "check_id": check_id}
        except Exception:
            logger.exception(
                "supplement_market_unexpected_error",
                extra={"check_id": check_id, "source": source_key},
            )
            self._mark_failure(
                check_id,
                status=ProductMarketCheck.Status.FAILED,
                code="internal_error",
                message="Не удалось проверить цену. Повторите позже.",
            )
            self._observe(source_key, "internal_error", started_monotonic)
            return {"status": ProductMarketCheck.Status.FAILED, "check_id": check_id}

    def _persist_success(
        self,
        *,
        check_id: int,
        price: Decimal,
        currency: str,
        source: TrustedSupplementSource,
    ) -> dict[str, Any]:
        now = timezone.now()
        with transaction.atomic():
            check = (
                ProductMarketCheck.objects.select_for_update()
                .select_related("product")
                .get(pk=check_id)
            )
            supplement = SupplementProduct.objects.select_for_update().get(
                base_product_id=check.product_id
            )
            previous_price = supplement.price
            preserved_availability = supplement.is_available
            preserved_stock = supplement.stock_quantity
            price_changed = (
                previous_price != price or str(supplement.currency or "").upper() != currency
            )
            if price_changed:
                supplement.old_price = previous_price
                supplement.price = price
                supplement.currency = currency
                supplement.save()
                if (
                    supplement.is_available != preserved_availability
                    or supplement.stock_quantity != preserved_stock
                ):
                    raise SupplementMarketCheckError(
                        "stock_mutation_detected",
                        "Проверка цены не может изменять наличие БАДа.",
                    )
                PriceHistory.objects.create(
                    product_id=supplement.base_product_id,
                    price=price,
                    currency=currency,
                    source="ilacfiyati_supplement_on_demand",
                )

            check.status = ProductMarketCheck.Status.SUCCEEDED
            check.source_url = source.url
            check.previous_price = previous_price if price_changed else check.previous_price
            check.observed_price = price
            check.observed_currency = currency
            check.analog_count = 0
            check.error_code = ""
            check.error_message = ""
            check.finished_at = now
            check.last_success_at = now
            check.save(
                update_fields=[
                    "status",
                    "source_url",
                    "previous_price",
                    "observed_price",
                    "observed_currency",
                    "analog_count",
                    "error_code",
                    "error_message",
                    "finished_at",
                    "last_success_at",
                    "updated_at",
                ]
            )
        return {
            "status": ProductMarketCheck.Status.SUCCEEDED,
            "check_id": check_id,
            "price": str(price),
            "currency": currency,
            "price_changed": price_changed,
        }

    @staticmethod
    def _mark_failure(check_id: int, *, status: str, code: str, message: str) -> None:
        ProductMarketCheck.objects.filter(pk=check_id).update(
            status=status,
            error_code=str(code or "")[:64],
            error_message=str(message or "")[:500],
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )

    @staticmethod
    def _observe(source: str, outcome: str, started_at: float) -> None:
        if SUPPLEMENT_MARKET_CHECKS is not None:
            SUPPLEMENT_MARKET_CHECKS.labels(
                source=source or "unknown",
                outcome=outcome,
            ).inc()
        if SUPPLEMENT_MARKET_LATENCY is not None:
            SUPPLEMENT_MARKET_LATENCY.labels(source=source or "unknown").observe(
                max(0.0, time.monotonic() - started_at)
            )

    def serialize(
        self,
        supplement: SupplementProduct,
        check: ProductMarketCheck | None,
    ) -> dict[str, Any]:
        from apps.catalog.services.supplement_availability import (
            SupplementAvailabilityService,
        )

        now = timezone.now()
        status = check.status if check else "not_requested"
        last_success_at = check.last_success_at if check else None
        fresh_seconds = _setting_int(
            "SUPPLEMENT_MARKET_CHECK_FRESH_SECONDS",
            43200,
            minimum=60,
            maximum=604800,
        )
        is_stale = bool(
            check
            and check.observed_price is not None
            and (
                status != ProductMarketCheck.Status.SUCCEEDED
                or not last_success_at
                or last_success_at < now - timedelta(seconds=fresh_seconds)
            )
        )
        error = None
        if check and check.error_code:
            error = {"code": check.error_code, "message": check.error_message}
        capability = SupplementAvailabilityService().capability(supplement)
        return {
            "enabled": self.is_enabled(),
            "status": status,
            "product": {
                "id": supplement.pk,
                "slug": supplement.slug,
                "name": supplement.name,
                "dosage_form": supplement.dosage_form or None,
                "active_ingredient": supplement.active_ingredient or None,
                "serving_size": supplement.serving_size or None,
            },
            "price": (
                {
                    "amount": str(check.observed_price),
                    "currency": check.observed_currency or "TRY",
                }
                if check and check.observed_price is not None
                else None
            ),
            "previous_price": (
                str(check.previous_price) if check and check.previous_price is not None else None
            ),
            "source": check.source if check else None,
            "availability": {
                "status": capability.availability_verification,
                "can_add_to_cart": capability.can_add_to_cart,
                "purchase_mode": capability.purchase_mode,
                "message": (
                    "Наличие будет проверено у поставщика при добавлении в корзину."
                    if capability.can_add_to_cart
                    else "Источник сообщает только справочную цену; наличие подтверждает консультант."
                ),
            },
            "requested_at": (
                check.requested_at.isoformat() if check and check.requested_at else None
            ),
            "started_at": check.started_at.isoformat() if check and check.started_at else None,
            "finished_at": check.finished_at.isoformat() if check and check.finished_at else None,
            "last_success_at": last_success_at.isoformat() if last_success_at else None,
            "is_stale": is_stale,
            "error": error,
            "poll_after_seconds": 2 if status in ACTIVE_STATUSES else None,
        }

    @staticmethod
    def latest_for(supplement: SupplementProduct) -> ProductMarketCheck | None:
        if not supplement.base_product_id:
            return None
        return (
            ProductMarketCheck.objects.filter(
                product_id=supplement.base_product_id,
                source__in=_allowed_sources(),
            )
            .order_by("-requested_at", "-pk")
            .first()
        )
