"""Audit and idempotently backfill ProductSourceOffer from stored scraper history."""

from __future__ import annotations

from collections import Counter
from typing import Iterator

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.catalog.models import Product
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.source_offers import (
    build_source_offer_snapshots,
    record_scraped_product_offers,
)


def _historical_scraped_products(product: Product) -> Iterator[ScrapedProduct]:
    external_data = product.external_data if isinstance(product.external_data, dict) else {}
    current_source = str(external_data.get("source") or "").strip().casefold()
    attributes = external_data.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}

    rows = external_data.get("scraped_sources")
    if not isinstance(rows, list):
        rows = []
    if not rows and current_source and product.external_url:
        rows = [
            {
                "source": current_source,
                "url": product.external_url,
                "price": product.price,
                "last_updated": product.last_synced_at,
            }
        ]

    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "").strip().casefold()
        url = str(row.get("url") or "").strip()
        identity = (source, url)
        if not source or not url or identity in seen:
            continue
        seen.add(identity)
        is_current_source = source == current_source
        yield ScrapedProduct(
            name=product.name,
            price=row.get("price") if row.get("price") is not None else product.price,
            currency=product.currency,
            url=url,
            external_id=product.external_id if is_current_source else "",
            sku=product.sku if is_current_source else "",
            is_available=product.is_available,
            stock_quantity=product.stock_quantity if is_current_source else None,
            attributes=attributes if is_current_source else {},
            source=source,
            scraped_at=str(row.get("last_updated") or ""),
        )


class Command(BaseCommand):
    help = (
        "Dry-run audit исторических scraper sources; с --apply идемпотентно создаёт "
        "ProductSourceOffer ограниченными batch."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Записать offers.")
        parser.add_argument("--source", default="", help="Ограничить parser key.")
        parser.add_argument("--start-id", type=int, default=0, help="Начать после Product.id.")
        parser.add_argument(
            "--limit",
            type=int,
            default=1000,
            help="Максимум Product за запуск (1..10000).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Размер iterator batch (1..1000).",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        source_filter = str(options["source"] or "").strip().casefold()
        start_id = max(int(options["start_id"] or 0), 0)
        limit = int(options["limit"])
        batch_size = int(options["batch_size"])
        if not 1 <= limit <= 10000:
            raise CommandError("--limit должен быть от 1 до 10000")
        if not 1 <= batch_size <= 1000:
            raise CommandError("--batch-size должен быть от 1 до 1000")

        queryset = (
            Product.objects.filter(
                Q(external_url__gt="") | Q(external_data__scraped_sources__isnull=False),
                pk__gt=start_id,
            )
            .order_by("pk")
            .only(
                "id",
                "name",
                "price",
                "currency",
                "external_url",
                "external_id",
                "sku",
                "is_available",
                "stock_quantity",
                "external_data",
                "last_synced_at",
            )
        )

        stats = Counter()
        last_product_id = start_id
        for product in queryset.iterator(chunk_size=batch_size):
            if stats["products"] >= limit:
                break
            stats["products"] += 1
            last_product_id = product.pk
            found_source = False
            for scraped_product in _historical_scraped_products(product):
                if source_filter and scraped_product.source != source_filter:
                    continue
                found_source = True
                snapshots = build_source_offer_snapshots(scraped_product)
                if not snapshots:
                    stats["invalid_sources"] += 1
                    continue
                stats["sources"] += 1
                stats["offers"] += len(snapshots)
                if apply_changes:
                    record_scraped_product_offers(
                        product=product,
                        scraped_product=scraped_product,
                    )
                    stats["written_sources"] += 1
            if not found_source:
                stats["without_source"] += 1

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(
            " ".join(
                (
                    f"mode={mode}",
                    f"products={stats['products']}",
                    f" sources={stats['sources']}",
                    f"offers={stats['offers']}",
                    f"written_sources={stats['written_sources']}",
                    f"invalid_sources={stats['invalid_sources']}",
                    f"without_source={stats['without_source']}",
                    f"last_product_id={last_product_id}",
                )
            )
        )
