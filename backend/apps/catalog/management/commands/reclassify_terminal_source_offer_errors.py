"""Reclassify narrowly proven terminal source-option outcomes without source traffic."""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.catalog.models import ProductSourceOffer


SUPPORTED_SOURCES = frozenset({"lcw", "zara"})
ERROR_PREFIX = "Source option was not found: "


def terminal_status(offer: ProductSourceOffer) -> str:
    """Return a terminal status only for the exact historical adapter outcome."""
    message = str(offer.last_error_message or "")
    if offer.parser_key == "lcw" and offer.variant_key and offer.size_key:
        if message == f"{ERROR_PREFIX}{offer.size_key}":
            return ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK
    if offer.parser_key == "zara" and offer.variant_key:
        if message == f"{ERROR_PREFIX}{offer.variant_key}":
            return ProductSourceOffer.AvailabilityStatus.DISCONTINUED
    return ""


class Command(BaseCommand):
    help = (
        "Dry-run audit terminal LCW/Zara option_not_found rows; --apply only clears "
        "the exact source-specific outcomes already observed as non-buyable."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply the reclassification.")
        parser.add_argument(
            "--source",
            choices=("all", *sorted(SUPPORTED_SOURCES)),
            default="all",
            help="Restrict the source mapping.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=5000,
            help="Maximum eligible rows to reclassify (1..10000).",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        source = str(options["source"] or "all")
        limit = int(options["limit"])
        if not 1 <= limit <= 10000:
            raise CommandError("--limit должен быть от 1 до 10000")

        sources = SUPPORTED_SOURCES if source == "all" else {source}
        queryset = (
            ProductSourceOffer.objects.filter(
                is_active=True,
                parser_key__in=sources,
                last_error_code="option_not_found",
            )
            .order_by("id")
            .only(
                "id",
                "parser_key",
                "variant_key",
                "size_key",
                "last_checked_at",
                "last_error_message",
            )
        )

        if apply_changes:
            with transaction.atomic():
                offers = list(queryset.select_for_update())
                stats = self._apply(offers, limit=limit)
        else:
            stats, _ = self._plan(list(queryset), limit=limit)

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(
            " ".join(
                (
                    f"mode={mode}",
                    f"eligible={stats['eligible']}",
                    f"skipped={stats['skipped']}",
                    f"lcw_out_of_stock={stats['lcw:out_of_stock']}",
                    f"zara_discontinued={stats['zara:discontinued']}",
                )
            )
        )

    @staticmethod
    def _plan(offers, *, limit: int):
        stats = Counter()
        selected = []
        for offer in offers:
            status = terminal_status(offer)
            if not status:
                stats["skipped"] += 1
                continue
            if stats["eligible"] >= limit:
                stats["skipped"] += 1
                continue
            selected.append((offer.pk, offer.parser_key, status))
            stats["eligible"] += 1
            stats[f"{offer.parser_key}:{status}"] += 1
        return stats, selected

    @classmethod
    def _apply(cls, offers, *, limit: int):
        stats, selected = cls._plan(offers, limit=limit)
        now = timezone.now()
        for parser_key, status in (
            ("lcw", ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK),
            ("zara", ProductSourceOffer.AvailabilityStatus.DISCONTINUED),
        ):
            ids = [
                pk
                for pk, selected_parser, selected_status in selected
                if selected_parser == parser_key and selected_status == status
            ]
            if not ids:
                continue
            ProductSourceOffer.objects.filter(
                pk__in=ids,
                last_error_code="option_not_found",
            ).update(
                availability_status=status,
                stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
                stock_quantity=None,
                last_successful_check_at=F("last_checked_at"),
                last_error_code="",
                last_error_message="",
                consecutive_failures=0,
                updated_at=now,
            )
        return stats
