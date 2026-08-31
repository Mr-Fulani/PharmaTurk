"""Bounded background refresh for persisted supplier offers.

The storefront must never trigger supplier requests as a side effect of reading
catalog data.  This module is the proactive counterpart to cart/checkout
verification: Celery calls it explicitly, with a hard batch boundary.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.utils import timezone
from billiard.exceptions import SoftTimeLimitExceeded

from apps.catalog.models import ProductSourceOffer
from apps.catalog.services.source_offer_verification import (
    SourceOfferVerificationService,
    manual_only_source_keys,
)

logger = logging.getLogger(__name__)

BACKGROUND_REFRESH_LOCK_KEY = "source-offer:background-refresh:v1"

try:
    from prometheus_client import Counter, Gauge

    SOURCE_OFFER_REFRESH_RUNS = Counter(
        "source_offer_background_refresh_total",
        "Bounded supplier offer refresh runs",
        ("outcome",),
    )
    SOURCE_OFFER_STALE_BACKLOG = Gauge(
        "source_offer_stale_backlog",
        "Active supplier offers older than the background refresh threshold",
    )
except (ImportError, ValueError):  # pragma: no cover - optional in dev reloads
    SOURCE_OFFER_REFRESH_RUNS = None
    SOURCE_OFFER_STALE_BACKLOG = None


def _bounded_setting(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _enabled_sources() -> list[str]:
    return sorted(
        {
            str(value or "").strip().casefold()
            for value in (getattr(settings, "SOURCE_OFFER_VERIFICATION_SOURCES", []) or [])
            if str(value or "").strip()
        }
    )


def _stale_offers(*, now, batch_size: int):
    stale_seconds = _bounded_setting(
        "SOURCE_OFFER_BACKGROUND_STALE_SECONDS",
        900,
        minimum=60,
        maximum=86400,
    )
    popular_cart_days = _bounded_setting(
        "SOURCE_OFFER_BACKGROUND_POPULAR_CART_DAYS",
        7,
        minimum=1,
        maximum=90,
    )
    stale_cutoff = now - timedelta(seconds=stale_seconds)
    popular_cutoff = now - timedelta(days=popular_cart_days)

    queryset = ProductSourceOffer.objects.filter(is_active=True).filter(
        Q(last_checked_at__isnull=True) | Q(last_checked_at__lte=stale_cutoff)
    ).exclude(parser_key__in=manual_only_source_keys())
    enabled_sources = _enabled_sources()
    if enabled_sources:
        queryset = queryset.filter(parser_key__in=enabled_sources)

    # Recently touched carts go first. The explicit NULL rank makes ordering
    # deterministic across PostgreSQL and SQLite for offers never checked yet.
    queryset = queryset.annotate(
        recent_cart_items=Count(
            "cart_items",
            filter=Q(cart_items__updated_at__gte=popular_cutoff),
            distinct=True,
        ),
        never_checked_rank=Case(
            When(last_checked_at__isnull=True, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ),
    ).order_by(
        "-recent_cart_items",
        "never_checked_rank",
        "last_checked_at",
        "priority",
        "id",
    )
    return queryset, queryset.count(), list(queryset[:batch_size])


def _acquire_lock(token: str, timeout: int) -> bool:
    try:
        return bool(cache.add(BACKGROUND_REFRESH_LOCK_KEY, token, timeout=timeout))
    except Exception:
        # Cache degradation should not stop maintenance entirely. Per-offer
        # single-flight still protects duplicate supplier calls where available.
        logger.exception("source_offer_background_lock_failed")
        return True


def _release_lock(token: str) -> None:
    try:
        if cache.get(BACKGROUND_REFRESH_LOCK_KEY) == token:
            cache.delete(BACKGROUND_REFRESH_LOCK_KEY)
    except Exception:
        logger.exception("source_offer_background_unlock_failed")


def _disabled(reason: str) -> dict[str, Any]:
    if SOURCE_OFFER_REFRESH_RUNS is not None:
        SOURCE_OFFER_REFRESH_RUNS.labels(outcome="disabled").inc()
    return {
        "status": "disabled",
        "reason": reason,
        "selected": 0,
        "checked": 0,
        "successful": 0,
        "retryable_errors": 0,
        "permanent_errors": 0,
    }


def refresh_stale_source_offers(*, now=None) -> dict[str, Any]:
    """Refresh one bounded stale batch, prioritising offers in active carts."""

    if not bool(getattr(settings, "SOURCE_OFFER_BACKGROUND_REFRESH_ENABLED", False)):
        return _disabled("background_refresh_disabled")
    if not bool(getattr(settings, "SOURCE_OFFER_VERIFICATION_ENABLED", False)):
        return _disabled("live_verification_disabled")

    batch_size = _bounded_setting(
        "SOURCE_OFFER_BACKGROUND_REFRESH_BATCH_SIZE",
        25,
        minimum=1,
        maximum=100,
    )
    lock_seconds = _bounded_setting(
        "SOURCE_OFFER_BACKGROUND_LOCK_SECONDS",
        330,
        minimum=30,
        maximum=3600,
    )
    token = uuid.uuid4().hex
    if not _acquire_lock(token, lock_seconds):
        if SOURCE_OFFER_REFRESH_RUNS is not None:
            SOURCE_OFFER_REFRESH_RUNS.labels(outcome="already_running").inc()
        return {
            "status": "already_running",
            "selected": 0,
            "checked": 0,
            "successful": 0,
            "retryable_errors": 0,
            "permanent_errors": 0,
        }

    try:
        current_time = now or timezone.now()
        _, stale_total, offers = _stale_offers(
            now=current_time,
            batch_size=batch_size,
        )
        if SOURCE_OFFER_STALE_BACKLOG is not None:
            SOURCE_OFFER_STALE_BACKLOG.set(stale_total)

        result: dict[str, Any] = {
            "status": "completed",
            "stale_total": stale_total,
            "selected": len(offers),
            "checked": 0,
            "successful": 0,
            "retryable_errors": 0,
            "permanent_errors": 0,
            "outcomes": {},
        }
        verifier = SourceOfferVerificationService()
        for offer in offers:
            try:
                check = verifier.verify(offer, force=True)
                result["checked"] += 1
                if check.is_success:
                    result["successful"] += 1
                    outcome = "success"
                else:
                    error = check.error
                    outcome = error.code.value if error is not None else "unknown_error"
                    if error is not None and error.retryable:
                        result["retryable_errors"] += 1
                    else:
                        result["permanent_errors"] += 1
                result["outcomes"][outcome] = result["outcomes"].get(outcome, 0) + 1
            except SoftTimeLimitExceeded:
                # Let Celery stop the batch cleanly; finally still releases the
                # distributed lock. Swallowing this would run until hard kill.
                raise
            except Exception:
                # A malformed offer or adapter must not abort the remaining batch.
                result["permanent_errors"] += 1
                result["outcomes"]["unexpected_error"] = (
                    result["outcomes"].get("unexpected_error", 0) + 1
                )
                logger.exception(
                    "source_offer_background_item_failed",
                    extra={"offer_id": offer.pk, "source": offer.parser_key},
                )

        metric_outcome = "completed_with_errors" if result["permanent_errors"] else "completed"
        if SOURCE_OFFER_REFRESH_RUNS is not None:
            SOURCE_OFFER_REFRESH_RUNS.labels(outcome=metric_outcome).inc()
        logger.info("source_offer_background_refresh", extra=result)
        return result
    finally:
        _release_lock(token)
