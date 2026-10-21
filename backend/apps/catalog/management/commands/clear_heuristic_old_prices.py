"""Снять ложные «старые цены» у товаров из парсеров (dry-run по умолчанию).

До 2026-10-20 old_price заполнялся прежней ценой при любой смене цены или
валюты (парсеры, рыночные проверки, IKEA): снижение цены давало бессрочную
«скидку» на витрине. Теперь old_price — только зачёркнутая цена источника;
команда разово очищает накопленные значения у товаров из парсеров, их
доменных карточек и вариантов мебели. Настоящая зачёркнутая цена вернётся
со следующим парсингом. Instagram не трогается: цену там ведут вручную.

    manage.py clear_heuristic_old_prices                                  # отчёт
    manage.py clear_heuristic_old_prices --apply --backup /backups/old_price.json
"""
import json
from collections import Counter

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.fields.json import KT

from apps.catalog.models import FurnitureVariant, Product

PARSER_SOURCES = (
    "ilacfiyati", "lcw", "flo", "ikea", "zara", "ummaland",
    "bershka", "pullandbear", "massimodutti",
)


def _domain_models():
    return [
        model for model in apps.get_app_config("catalog").get_models()
        if model is not Product
        and any(f.name == "base_product" for f in model._meta.get_fields())
        and any(f.name == "old_price" for f in model._meta.get_fields())
    ]


class Command(BaseCommand):
    help = "Очищает old_price, заполненные прежней ценой (не ценой источника)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Изменить данные (иначе только отчёт).")
        parser.add_argument("--backup", default="", help="JSON-файл для бэкапа строк (обязателен с --apply).")

    def handle(self, *args, **options):
        products = (
            Product.objects.annotate(source=KT("external_data__source"))
            .filter(source__in=PARSER_SOURCES, old_price__isnull=False)
        )
        rows = list(products.values_list("id", "source", "price", "old_price"))
        ids = [row[0] for row in rows]
        by_source = Counter(row[1] for row in rows)
        discounts = Counter(row[1] for row in rows if row[2] is not None and row[3] > row[2])

        domain_rows = []
        for model in _domain_models():
            for pk, base_id, old_price in model.objects.filter(
                base_product_id__in=ids, old_price__isnull=False,
            ).values_list("pk", "base_product_id", "old_price"):
                domain_rows.append((model._meta.label, pk, base_id, old_price))
        variant_rows = list(
            FurnitureVariant.objects.filter(
                product__base_product_id__in=ids, old_price__isnull=False,
            ).values_list("pk", "old_price")
        )

        for source, count in sorted(by_source.items()):
            self.stdout.write(
                f"{source}: old_price у {count} товаров, из них «скидка» на витрине — {discounts[source]}"
            )
        self.stdout.write(
            f"Итого товаров: {len(ids)}; доменных карточек: {len(domain_rows)}; "
            f"вариантов мебели: {len(variant_rows)}"
        )
        if not options["apply"]:
            self.stdout.write("Dry-run: ничего не изменено. Для записи: --apply --backup <файл>.")
            return
        if not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл> со старыми значениями.")

        with open(options["backup"], "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "products": [[pk, str(old)] for pk, _source, _price, old in rows],
                    "domain": [[label, pk, base_id, str(old)] for label, pk, base_id, old in domain_rows],
                    "furniture_variants": [[pk, str(old)] for pk, old in variant_rows],
                },
                fh,
            )
        with transaction.atomic():
            Product.objects.filter(pk__in=ids).update(old_price=None)
            for model in _domain_models():
                model.objects.filter(base_product_id__in=ids).update(old_price=None)
            FurnitureVariant.objects.filter(product__base_product_id__in=ids).update(old_price=None)
        self.stdout.write(self.style.SUCCESS(f"Очищено. Бэкап: {options['backup']}"))
