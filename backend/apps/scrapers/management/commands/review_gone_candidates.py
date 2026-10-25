"""Товары, которые режим «Только изменения» пометил к снятию с продажи (отчёт по умолчанию).

При ``SCRAPER_GONE_REQUIRES_REVIEW=true`` пропавшие у источника товары не снимаются
сами, а получают ``external_data["gone_candidate"]``. Команда показывает их, снимает
подтверждённые или убирает пометку.

    manage.py review_gone_candidates                         # отчёт
    manage.py review_gone_candidates --csv gone.csv          # отчёт в CSV
    manage.py review_gone_candidates --apply                 # снять с продажи всех кандидатов
    manage.py review_gone_candidates --apply --ids 12 15     # только эти товары
    manage.py review_gone_candidates --clear --ids 12        # оставить в продаже, убрать пометку
"""
import csv
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import Product
from apps.scrapers.listing_changes import GONE_CANDIDATE_KEY, mark_products_gone


class Command(BaseCommand):
    help = "Кандидаты на снятие с продажи из режима «Только изменения»: отчёт, --apply или --clear."

    def add_arguments(self, parser):
        parser.add_argument("--parser", default="", help="Только этот источник (например, ilacfiyati).")
        parser.add_argument("--ids", nargs="*", type=int, default=None, help="Только эти товары.")
        parser.add_argument("--apply", action="store_true", help="Снять кандидатов с продажи.")
        parser.add_argument("--clear", action="store_true", help="Убрать пометку, товар остаётся в продаже.")
        parser.add_argument("--csv", default="", help="Записать отчёт в CSV.")

    def handle(self, *args, **options):
        if options["apply"] and options["clear"]:
            raise CommandError("Либо --apply, либо --clear.")
        queryset = Product.objects.filter(**{f"external_data__{GONE_CANDIDATE_KEY}__isnull": False})
        if options["parser"]:
            queryset = queryset.filter(**{f"external_data__{GONE_CANDIDATE_KEY}__parser": options["parser"]})
        if options["ids"] is not None:
            queryset = queryset.filter(pk__in=options["ids"])
        rows = list(queryset.order_by("pk").values("pk", "name", "product_type", "is_available", "external_url", "external_data"))
        reasons = Counter((row["external_data"][GONE_CANDIDATE_KEY].get("reason") or "?") for row in rows)
        self.stdout.write(f"Кандидатов: {len(rows)} | причины: {dict(reasons)}")
        for row in rows[:50]:
            mark = row["external_data"][GONE_CANDIDATE_KEY]
            self.stdout.write(f"  {row['pk']} [{row['product_type']}] {mark.get('reason')} | {row['name'][:70]} | {row['external_url']}")
        if len(rows) > 50:
            self.stdout.write(f"  … ещё {len(rows) - 50}")
        if options["csv"]:
            with open(options["csv"], "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["id", "type", "reason", "at", "name", "url", "available"])
                for row in rows:
                    mark = row["external_data"][GONE_CANDIDATE_KEY]
                    writer.writerow([row["pk"], row["product_type"], mark.get("reason"), mark.get("at"),
                                     row["name"], row["external_url"], row["is_available"]])
            self.stdout.write(f"CSV: {options['csv']}")
        if not (options["apply"] or options["clear"]):
            return
        if options["apply"]:
            by_parser = {}
            for row in rows:
                mark = row["external_data"][GONE_CANDIDATE_KEY]
                by_parser.setdefault((mark.get("parser") or "", mark.get("reason") or "inactive"), []).append(row["pk"])
            removed = sum(
                mark_products_gone(ids, parser_key=parser_key, reason=reason, review=False)
                for (parser_key, reason), ids in by_parser.items()
            )
            self.stdout.write(f"Снято с продажи: {removed}")
        for row in rows:
            data = row["external_data"]
            data.pop(GONE_CANDIDATE_KEY, None)
            Product.objects.filter(pk=row["pk"]).update(external_data=data)
        self.stdout.write(f"Пометка снята: {len(rows)}")
