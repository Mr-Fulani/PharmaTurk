"""Read-only rollout diagnostics for supplier source offers.

The report intentionally uses aggregate queries only. It never calls a parser,
refreshes an offer, or mutates catalog/cart/order state, so operators can run it
before enabling any source-offer feature flag.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Count, Q
from django.utils import timezone

from apps.catalog.models import Product, ProductSourceOffer

REQUIRED_MIGRATIONS = (
    ("catalog", "0202_productsourceoffer"),
    ("orders", "0010_cartitem_source_verification"),
    ("orders", "0011_orderitem_source_snapshot"),
)


def _applied_migrations(*, using: str) -> set[tuple[str, str]]:
    connection = connections[using]
    return set(MigrationRecorder(connection).migration_qs.values_list("app", "name").iterator())


def _count_by(queryset, field: str) -> dict[str, int]:
    return {
        str(row[field]): int(row["count"])
        for row in queryset.values(field).annotate(count=Count("id")).order_by(field)
    }


def _feature_flags() -> dict[str, Any]:
    return {
        "recording_enabled": bool(getattr(settings, "SOURCE_OFFER_RECORDING_ENABLED", False)),
        "verification_enabled": bool(getattr(settings, "SOURCE_OFFER_VERIFICATION_ENABLED", False)),
        "verification_sources": sorted(
            {
                str(source).strip().casefold()
                for source in getattr(settings, "SOURCE_OFFER_VERIFICATION_SOURCES", [])
                if str(source).strip()
            }
        ),
        "background_refresh_enabled": bool(
            getattr(settings, "SOURCE_OFFER_BACKGROUND_REFRESH_ENABLED", False)
        ),
        "cart_enforcement_enabled": bool(
            getattr(settings, "SOURCE_OFFER_CART_ENFORCEMENT_ENABLED", False)
        ),
        "catalog_projection_enabled": bool(
            getattr(settings, "SOURCE_OFFER_CATALOG_PROJECTION_ENABLED", False)
        ),
    }


def _flag_blockers(flags: dict[str, Any]) -> list[str]:
    blockers = []
    if flags["verification_enabled"] and not flags["verification_sources"]:
        blockers.append("verification_enabled_with_empty_allowlist")
    if flags["cart_enforcement_enabled"] and not flags["verification_enabled"]:
        blockers.append("cart_enforcement_without_verification")
    if flags["background_refresh_enabled"] and not flags["verification_enabled"]:
        blockers.append("background_refresh_without_verification")
    return blockers


def _cart_report(*, using: str, migration_ready: bool) -> dict[str, Any]:
    if not migration_ready:
        return {"available": False, "reason": "migration_0010_not_applied"}

    from apps.orders.models import CartItem

    items = CartItem.objects.using(using).all()
    return {
        "available": True,
        "items_total": items.count(),
        "items_with_source_offer": items.filter(source_offer_id__isnull=False).count(),
        "verification_statuses": _count_by(items, "verification_status"),
        "items_with_issues": items.exclude(verification_issues=[]).count(),
    }


def _order_report(*, using: str, migration_ready: bool) -> dict[str, Any]:
    if not migration_ready:
        return {"available": False, "reason": "migration_0011_not_applied"}

    from apps.orders.models import OrderItem

    items = OrderItem.objects.using(using).all()
    return {
        "available": True,
        "items_total": items.count(),
        "items_with_source_snapshot": items.exclude(source_parser="").count(),
        "supplier_confirmation_required": items.filter(supplier_confirmation_required=True).count(),
    }


def build_source_offer_rollout_report(
    *,
    using: str = DEFAULT_DB_ALIAS,
    stale_seconds: int | None = None,
    now=None,
) -> dict[str, Any]:
    """Build a serializable, aggregate-only rollout report."""
    now = now or timezone.now()
    stale_seconds = int(
        stale_seconds
        if stale_seconds is not None
        else getattr(settings, "SOURCE_OFFER_BACKGROUND_STALE_SECONDS", 900)
    )
    stale_seconds = max(stale_seconds, 1)
    stale_before = now - timedelta(seconds=stale_seconds)

    applied = _applied_migrations(using=using)
    migration_status = {
        f"{app}.{name}": (app, name) in applied for app, name in REQUIRED_MIGRATIONS
    }
    missing_migrations = [
        migration for migration, is_applied in migration_status.items() if not is_applied
    ]

    products = Product.objects.using(using).all()
    source_candidates = products.filter(
        Q(external_url__gt="") | Q(external_data__scraped_sources__isnull=False)
    )
    candidate_count = source_candidates.count()

    offers = ProductSourceOffer.objects.using(using).all()
    active_offers = offers.filter(is_active=True)
    covered_products = source_candidates.filter(source_offers__is_active=True).distinct()
    covered_count = covered_products.count()

    never_checked = active_offers.filter(last_checked_at__isnull=True).count()
    stale = active_offers.filter(
        Q(last_checked_at__isnull=True) | Q(last_checked_at__lt=stale_before)
    ).count()
    fake_stock = {
        str(row["stock_quantity"]): int(row["count"])
        for row in source_candidates.filter(stock_quantity__in=(3, 1000))
        .values("stock_quantity")
        .annotate(count=Count("id"))
        .order_by("stock_quantity")
    }

    per_source = []
    for row in (
        active_offers.values("parser_key")
        .annotate(
            offers=Count("id"),
            products=Count("product_id", distinct=True),
            never_checked=Count("id", filter=Q(last_checked_at__isnull=True)),
            stale=Count(
                "id",
                filter=(Q(last_checked_at__isnull=True) | Q(last_checked_at__lt=stale_before)),
            ),
            with_errors=Count("id", filter=~Q(last_error_code="")),
        )
        .order_by("parser_key")
    ):
        per_source.append(
            {
                "parser_key": row["parser_key"],
                "offers": int(row["offers"]),
                "products": int(row["products"]),
                "never_checked": int(row["never_checked"]),
                "stale": int(row["stale"]),
                "with_errors": int(row["with_errors"]),
            }
        )

    flags = _feature_flags()
    blockers = [f"missing_migration:{migration}" for migration in missing_migrations]
    blockers.extend(_flag_blockers(flags))
    if candidate_count and not active_offers.exists():
        blockers.append("source_candidates_without_active_offers")

    warnings = []
    if fake_stock:
        warnings.append("legacy_fake_stock_present")
    if never_checked:
        warnings.append("active_offers_never_checked")
    if stale:
        warnings.append("active_offers_stale")

    cart_migration_ready = migration_status["orders.0010_cartitem_source_verification"]
    order_migration_ready = migration_status["orders.0011_orderitem_source_snapshot"]
    coverage_percent = (
        round((covered_count * 100) / candidate_count, 2) if candidate_count else 100.0
    )

    return {
        "mode": "READ_ONLY",
        "generated_at": now.isoformat(),
        "database_alias": using,
        "stale_seconds": stale_seconds,
        "schema": {
            "all_required_migrations_applied": not missing_migrations,
            "migrations": migration_status,
        },
        "feature_flags": flags,
        "catalog": {
            "products_total": products.count(),
            "source_candidate_products": candidate_count,
            "candidate_products_with_active_offers": covered_count,
            "coverage_percent": coverage_percent,
            "legacy_fake_stock_candidates": fake_stock,
        },
        "offers": {
            "total": offers.count(),
            "active": active_offers.count(),
            "inactive": offers.filter(is_active=False).count(),
            "never_checked": never_checked,
            "stale": stale,
            "availability_statuses": _count_by(active_offers, "availability_status"),
            "stock_precisions": _count_by(active_offers, "stock_precision"),
            "per_source": per_source,
        },
        "cart": _cart_report(using=using, migration_ready=cart_migration_ready),
        "orders": _order_report(using=using, migration_ready=order_migration_ready),
        "blockers": blockers,
        "warnings": warnings,
        "ready_for_source_rollout": not blockers,
    }
