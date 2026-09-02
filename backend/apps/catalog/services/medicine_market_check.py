"""On-demand informational medicine price checks.

This boundary intentionally does not reuse cart offer verification. Medicines are
not sold by the site, and legacy medical parsers expose synthetic stock defaults.
Only a validated reference price and medicine-equivalent observations are persisted.
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
    MedicineAnalog,
    MedicineProduct,
    PriceHistory,
    ProductMarketCheck,
)
from apps.scrapers.base.scraper import ScraperAccessBlockedError
from apps.scrapers.models import ScraperConfig
from apps.scrapers.parsers.ilacfiyati import (
    ILACFIYATI_PRICE_CURRENCIES,
    IlacFiyatiSourceError,
)
from apps.scrapers.parsers.registry import get_parser

logger = logging.getLogger(__name__)

CACHE_VERSION = "v1"
ACTIVE_STATUSES = {
    ProductMarketCheck.Status.PENDING,
    ProductMarketCheck.Status.RUNNING,
}

try:
    from prometheus_client import Counter, Histogram

    MEDICINE_MARKET_CHECKS = Counter(
        "medicine_market_checks_total",
        "On-demand medicine market price checks",
        ("source", "outcome"),
    )
    MEDICINE_MARKET_LATENCY = Histogram(
        "medicine_market_check_seconds",
        "On-demand medicine market check latency",
        ("source",),
    )
except (ImportError, ValueError):  # pragma: no cover - optional during dev reloads
    MEDICINE_MARKET_CHECKS = None
    MEDICINE_MARKET_LATENCY = None


def _setting_int(name: str, default: int, *, minimum: int = 0, maximum: int = 86400) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _allowed_sources() -> set[str]:
    return {
        str(value or "").strip().casefold()
        for value in (getattr(settings, "MEDICINE_MARKET_CHECK_SOURCES", ["ilacfiyati"]) or [])
        if str(value or "").strip()
    }


def _safe_cache_add(key: str, token: str, timeout: int) -> tuple[bool, bool]:
    """Return ``(acquired, cache_healthy)`` and fail closed on Redis errors."""

    try:
        return bool(cache.add(key, token, timeout=max(1, timeout))), True
    except Exception:
        logger.exception("medicine_market_cache_add_failed", extra={"cache_key": key})
        return False, False


def _cache_delete_if_owned(key: str, token: str) -> None:
    try:
        if cache.get(key) == token:
            cache.delete(key)
    except Exception:
        logger.exception("medicine_market_cache_unlock_failed", extra={"cache_key": key})


class MedicineMarketCheckError(RuntimeError):
    def __init__(self, code: str, message: str, *, http_status: int = 503):
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.http_status = http_status


@dataclass(frozen=True)
class TrustedMedicineSource:
    key: str
    url: str
    parser_class: type
    config: ScraperConfig


@dataclass(frozen=True)
class MedicineMarketRequestResult:
    check: ProductMarketCheck
    queued: bool
    cached: bool


class MedicineMarketCheckService:
    """Create, execute and serialize bounded medicine price observations."""

    def is_enabled(self) -> bool:
        return bool(getattr(settings, "MEDICINE_MARKET_CHECK_ENABLED", False))

    @staticmethod
    def _source_candidates(medicine: MedicineProduct) -> list[str]:
        base = medicine.base_product
        candidates: list[str] = []
        for direct in (
            medicine.external_url,
            getattr(base, "external_url", "") if base else "",
        ):
            value = str(direct or "").strip()
            if value and value not in candidates:
                candidates.append(value)

        for payload in (
            medicine.external_data,
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
    def _canonical_ilacfiyati_medicine_url(url: str) -> str | None:
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
            or parts[0] != "ilaclar"
            or not all(char.isalnum() or char in {"-", "_"} for char in parts[1])
        ):
            return None
        return f"https://ilacfiyati.com/ilaclar/{parts[1]}"

    def resolve_source(self, medicine: MedicineProduct) -> TrustedMedicineSource:
        if not self.is_enabled():
            raise MedicineMarketCheckError(
                "disabled",
                "Проверка актуальной цены временно отключена.",
            )
        if not medicine.base_product_id:
            raise MedicineMarketCheckError(
                "missing_product_identity",
                "Для препарата не настроена проверка источника.",
                http_status=409,
            )

        allowed = _allowed_sources()
        if "ilacfiyati" not in allowed:
            raise MedicineMarketCheckError(
                "source_disabled",
                "Источник актуальной цены временно отключён.",
            )

        parser_class = get_parser("ilacfiyati")
        if parser_class is None:
            raise MedicineMarketCheckError(
                "parser_unavailable",
                "Проверка этого источника сейчас недоступна.",
            )

        source_url = None
        for candidate in self._source_candidates(medicine):
            canonical = self._canonical_ilacfiyati_medicine_url(candidate)
            if canonical and get_parser(canonical) is parser_class:
                source_url = canonical
                break
        if not source_url:
            raise MedicineMarketCheckError(
                "invalid_source",
                "Для препарата не найдена доверенная карточка первоисточника.",
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
            raise MedicineMarketCheckError(
                "source_not_configured",
                "Источник актуальной цены ещё не настроен.",
            )
        return TrustedMedicineSource(
            key="ilacfiyati",
            url=source_url,
            parser_class=parser_class,
            config=config,
        )

    @staticmethod
    def _fresh(check: ProductMarketCheck, now) -> bool:
        success_ttl = _setting_int(
            "MEDICINE_MARKET_CHECK_FRESH_SECONDS",
            43200,
            minimum=60,
            maximum=604800,
        )
        error_ttl = _setting_int(
            "MEDICINE_MARKET_CHECK_ERROR_FRESH_SECONDS",
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
            "MEDICINE_MARKET_CHECK_STALE_RUNNING_SECONDS",
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
            "MEDICINE_MARKET_CHECK_GLOBAL_RATE_PER_MINUTE",
            10,
            minimum=1,
            maximum=300,
        )
        key = f"medicine-market:rate:{CACHE_VERSION}:{source}:{int(time.time() // 60)}"
        try:
            if cache.add(key, 1, timeout=70):
                count = 1
            else:
                count = int(cache.incr(key))
            return count <= limit
        except Exception:
            logger.exception("medicine_market_rate_limit_failed", extra={"source": source})
            return False

    def request_check(self, medicine: MedicineProduct) -> MedicineMarketRequestResult:
        source = self.resolve_source(medicine)
        now = timezone.now()
        lock_ttl = _setting_int(
            "MEDICINE_MARKET_CHECK_ENQUEUE_LOCK_SECONDS",
            30,
            minimum=5,
            maximum=120,
        )
        lock_key = (
            f"medicine-market:enqueue:{CACHE_VERSION}:{medicine.base_product_id}:{source.key}"
        )
        lock_token = uuid.uuid4().hex
        owns_lock = False

        try:
            with transaction.atomic():
                check, _ = ProductMarketCheck.objects.select_for_update().get_or_create(
                    product_id=medicine.base_product_id,
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
                    return MedicineMarketRequestResult(check=check, queued=False, cached=True)

                if is_active:
                    check.save(
                        update_fields=["request_count", "requested_at", "source_url", "updated_at"]
                    )
                    return MedicineMarketRequestResult(check=check, queued=False, cached=False)

                acquired, cache_healthy = _safe_cache_add(lock_key, lock_token, lock_ttl)
                if not cache_healthy:
                    raise MedicineMarketCheckError(
                        "guard_unavailable",
                        "Защита источника временно недоступна. Повторите позже.",
                    )
                if not acquired:
                    check.save(
                        update_fields=["request_count", "requested_at", "source_url", "updated_at"]
                    )
                    return MedicineMarketRequestResult(check=check, queued=False, cached=False)
                owns_lock = True

                if not self._global_rate_allowed(source.key):
                    raise MedicineMarketCheckError(
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

            from apps.catalog.tasks import refresh_medicine_market_check_task

            try:
                async_result = refresh_medicine_market_check_task.apply_async(args=[check.pk])
            except Exception as exc:
                logger.exception(
                    "medicine_market_task_publish_failed",
                    extra={"check_id": check.pk, "source": source.key},
                )
                self._mark_failure(
                    check.pk,
                    status=ProductMarketCheck.Status.SOURCE_UNAVAILABLE,
                    code="queue_unavailable",
                    message="Проверку не удалось поставить в очередь. Повторите позже.",
                )
                raise MedicineMarketCheckError(
                    "queue_unavailable",
                    "Проверку не удалось запустить. Повторите позже.",
                ) from exc

            ProductMarketCheck.objects.filter(
                pk=check.pk,
                status=ProductMarketCheck.Status.PENDING,
                task_id="",
            ).update(task_id=str(async_result.id or "")[:100])
            check.refresh_from_db()
            return MedicineMarketRequestResult(check=check, queued=True, cached=False)
        finally:
            if owns_lock:
                _cache_delete_if_owned(lock_key, lock_token)

    @contextmanager
    def _source_slot(self, source: str) -> Iterator[bool]:
        limit = _setting_int(
            "MEDICINE_MARKET_CHECK_SOURCE_CONCURRENCY",
            2,
            minimum=1,
            maximum=10,
        )
        ttl = _setting_int(
            "MEDICINE_MARKET_CHECK_STALE_RUNNING_SECONDS",
            180,
            minimum=30,
            maximum=1800,
        )
        token = uuid.uuid4().hex
        acquired_key = ""
        cache_healthy = True
        for index in range(limit):
            key = f"medicine-market:slot:{CACHE_VERSION}:{source}:{index}"
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
            raise MedicineMarketCheckError(
                "price_missing",
                "Источник не вернул корректную актуальную цену.",
                http_status=422,
            )
        if not price.is_finite() or price <= 0 or price > Decimal("999999999999.99"):
            raise MedicineMarketCheckError(
                "price_invalid",
                "Источник вернул некорректную актуальную цену.",
                http_status=422,
            )
        return price

    @staticmethod
    def _parser_for(source: TrustedMedicineSource):
        timeout = _setting_int(
            "MEDICINE_MARKET_CHECK_REQUEST_TIMEOUT_SECONDS",
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

    def _parse_snapshot(self, source: TrustedMedicineSource):
        with self._parser_for(source) as parser:
            parse_market_snapshot = getattr(parser, "parse_market_snapshot", None)
            if not callable(parse_market_snapshot):
                raise MedicineMarketCheckError(
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
            # Duplicate delivery must not execute the same source check twice. A
            # genuinely stale RUNNING row is reset to PENDING by request_check().
            if check.status != ProductMarketCheck.Status.PENDING:
                return {"status": check.status, "check_id": check.pk}
            check.status = ProductMarketCheck.Status.RUNNING
            check.started_at = timezone.now()
            check.finished_at = None
            check.save(update_fields=["status", "started_at", "finished_at", "updated_at"])
            medicine = MedicineProduct.objects.filter(base_product_id=check.product_id).first()

        if medicine is None or not medicine.is_active:
            self._mark_failure(
                check_id,
                status=ProductMarketCheck.Status.FAILED,
                code="medicine_unavailable",
                message="Карточка препарата больше недоступна.",
            )
            return {"status": ProductMarketCheck.Status.FAILED, "check_id": check_id}

        source_key = check.source
        try:
            source = self.resolve_source(medicine)
            if source.key != check.source or source.url != check.source_url:
                raise MedicineMarketCheckError(
                    "source_changed",
                    "Источник препарата изменился. Запустите новую проверку.",
                    http_status=409,
                )
            with self._source_slot(source.key) as slot_acquired:
                if not slot_acquired:
                    raise MedicineMarketCheckError(
                        "source_busy",
                        "Источник занят другими проверками. Повторите позже.",
                    )
                scraped = self._parse_snapshot(source)

            price = self._decimal_price(getattr(scraped, "price", None))
            currency = str(getattr(scraped, "currency", "") or "").strip().upper()
            if currency not in ILACFIYATI_PRICE_CURRENCIES:
                raise MedicineMarketCheckError(
                    "currency_invalid",
                    "Источник вернул цену в неожиданной валюте.",
                    http_status=422,
                )
            analogs = list(getattr(scraped, "analogs", None) or [])
            max_analogs = _setting_int(
                "MEDICINE_MARKET_CHECK_MAX_ANALOGS",
                50,
                minimum=0,
                maximum=200,
            )
            analogs = analogs[:max_analogs]
            result = self._persist_success(
                check_id=check_id,
                price=price,
                currency=currency,
                analogs=analogs,
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
        except MedicineMarketCheckError as exc:
            status = (
                ProductMarketCheck.Status.SOURCE_UNAVAILABLE
                if exc.code in {"source_busy", "guard_unavailable"}
                else ProductMarketCheck.Status.FAILED
            )
            self._mark_failure(
                check_id,
                status=status,
                code=exc.code,
                message=exc.public_message,
            )
            self._observe(source_key, exc.code, started_monotonic)
            return {"status": status, "check_id": check_id, "error_code": exc.code}
        except (ScraperAccessBlockedError, httpx.HTTPError) as exc:
            logger.warning(
                "medicine_market_source_unavailable",
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
                "medicine_market_malformed_source",
                extra={"check_id": check_id, "source": source_key},
            )
            self._mark_failure(
                check_id,
                status=ProductMarketCheck.Status.FAILED,
                code="malformed_response",
                message="Источник не вернул данные препарата в ожидаемом формате.",
            )
            self._observe(source_key, "malformed_response", started_monotonic)
            return {"status": ProductMarketCheck.Status.FAILED, "check_id": check_id}
        except Exception:
            logger.exception(
                "medicine_market_unexpected_error",
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

    @staticmethod
    def _find_existing_analog(analog: dict[str, Any]) -> MedicineProduct | None:
        barcode = str(analog.get("barcode") or "").strip()
        external_id = str(analog.get("external_id") or "").strip()
        source_url = str(analog.get("url") or "").strip()
        name = str(analog.get("name") or "").strip()
        qs = MedicineProduct.objects.filter(is_active=True)
        for field_name, value in (
            ("barcode", barcode),
            ("external_id", external_id),
            ("external_url", source_url),
            ("name__iexact", name),
        ):
            if value:
                found = qs.filter(**{field_name: value}).first()
                if found:
                    return found
        return None

    def _upsert_analogs(
        self,
        medicine: MedicineProduct,
        analogs: list[dict[str, Any]],
        *,
        source: str,
        observed_at,
    ) -> int:
        saved = 0
        for payload in analogs:
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("name") or "").strip()[:500]
            if not name:
                continue
            external_id = str(payload.get("external_id") or "").strip()[:200]
            barcode = str(payload.get("barcode") or "").strip()[:50]
            source_url = str(payload.get("url") or "").strip()[:2000]
            source_tab = str(payload.get("source_tab") or "").strip()[:100]
            qs = MedicineAnalog.objects.filter(product=medicine, source=source)
            analog_ref = None
            if external_id:
                analog_ref = qs.filter(external_id=external_id).first()
            if analog_ref is None and barcode:
                analog_ref = qs.filter(barcode=barcode).first()
            if analog_ref is None:
                analog_ref = qs.filter(name=name, source_tab=source_tab).first()
            if analog_ref is None:
                analog_ref = MedicineAnalog(product=medicine, source=source)

            reference_price = None
            if payload.get("price") is not None:
                try:
                    reference_price = self._decimal_price(payload.get("price"))
                except MedicineMarketCheckError:
                    reference_price = None
            analog_product = self._find_existing_analog(payload)
            analog_ref.name = name
            analog_ref.external_id = external_id
            analog_ref.barcode = barcode
            analog_ref.atc_code = str(payload.get("atc_code") or "").strip()[:20]
            analog_ref.sgk_equivalent_code = str(payload.get("sgk_equivalent_code") or "").strip()[
                :100
            ]
            analog_ref.source_tab = source_tab
            analog_ref.source_url = source_url
            analog_ref.reference_price = reference_price
            analog_ref.reference_currency = "TRY" if reference_price is not None else ""
            analog_ref.last_observed_at = observed_at
            if analog_product and analog_product.pk != medicine.pk:
                analog_ref.analog_product = analog_product
            analog_ref.save()
            saved += 1
        return saved

    def _persist_success(
        self,
        *,
        check_id: int,
        price: Decimal,
        currency: str,
        analogs: list[dict[str, Any]],
        source: TrustedMedicineSource,
    ) -> dict[str, Any]:
        now = timezone.now()
        with transaction.atomic():
            check = (
                ProductMarketCheck.objects.select_for_update()
                .select_related("product")
                .get(pk=check_id)
            )
            medicine = MedicineProduct.objects.select_for_update().get(
                base_product_id=check.product_id
            )
            previous_price = medicine.price
            price_changed = (
                previous_price != price or str(medicine.currency or "").upper() != currency
            )
            if price_changed:
                medicine.old_price = previous_price
                medicine.price = price
                medicine.currency = currency
                # MedicineProduct.save() synchronizes the shadow Product while preserving
                # the existing medicine availability/stock values unchanged.
                medicine.save()
                if medicine.base_product_id:
                    PriceHistory.objects.create(
                        product_id=medicine.base_product_id,
                        price=price,
                        currency=currency,
                        source="ilacfiyati_on_demand",
                    )

            analog_count = self._upsert_analogs(
                medicine,
                analogs,
                source=source.key,
                observed_at=now,
            )
            check.status = ProductMarketCheck.Status.SUCCEEDED
            check.source_url = source.url
            check.previous_price = previous_price if price_changed else check.previous_price
            check.observed_price = price
            check.observed_currency = currency
            check.analog_count = analog_count
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
            "analogs": analog_count,
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
        if MEDICINE_MARKET_CHECKS is not None:
            MEDICINE_MARKET_CHECKS.labels(source=source or "unknown", outcome=outcome).inc()
        if MEDICINE_MARKET_LATENCY is not None:
            MEDICINE_MARKET_LATENCY.labels(source=source or "unknown").observe(
                max(0.0, time.monotonic() - started_at)
            )

    def serialize(
        self, medicine: MedicineProduct, check: ProductMarketCheck | None
    ) -> dict[str, Any]:
        now = timezone.now()
        status = check.status if check else "not_requested"
        last_success_at = check.last_success_at if check else None
        fresh_seconds = _setting_int(
            "MEDICINE_MARKET_CHECK_FRESH_SECONDS",
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
            error = {
                "code": check.error_code,
                "message": check.error_message,
            }
        return {
            "enabled": self.is_enabled(),
            "status": status,
            "product": {
                "id": medicine.pk,
                "slug": medicine.slug,
                "name": medicine.name,
                "dosage_form": medicine.dosage_form or None,
                "volume": medicine.volume or None,
                "active_ingredient": medicine.active_ingredient or None,
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
            "analog_count": int(check.analog_count or 0) if check else 0,
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
    def latest_for(medicine: MedicineProduct) -> ProductMarketCheck | None:
        if not medicine.base_product_id:
            return None
        allowed = _allowed_sources()
        return (
            ProductMarketCheck.objects.filter(
                product_id=medicine.base_product_id,
                source__in=allowed,
            )
            .order_by("-requested_at", "-pk")
            .first()
        )
