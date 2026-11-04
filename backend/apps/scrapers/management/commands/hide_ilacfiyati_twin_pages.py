"""Лекарства-«близнецы» ilacfiyati: две страницы источника одного препарата (показ по умолчанию).

Правило — apps.scrapers.ilacfiyati_twins, описание — docs/ILACFIYATI_TWIN_PAGES.md. Для каждой
группы показанных лекарств с одним штрихкодом печатает решение: «скрыть» (полный дубль —
остаётся страница с ценой) или «на проверку» (разные числа или слова в названии, состав,
цены). Ничего не удаляется: --apply скрывает только строки «скрыть» (is_active=False у
Product и MedicineProduct) и ведёт их адрес 301 на оставленный товар.

    manage.py hide_ilacfiyati_twin_pages                                  # показ
    manage.py hide_ilacfiyati_twin_pages --barcode 1111111101867          # одна группа
    manage.py hide_ilacfiyati_twin_pages --csv twins.csv                  # показ + CSV
    manage.py hide_ilacfiyati_twin_pages --apply --backup /backups/twins.json

Откат по бэкапу: Product и MedicineProduct — is_active=True и прежний external_data
(QuerySet.update), строки ProductSlugHistory из бэкапа — удалить или вернуть прежнему товару.
"""
import csv
import json
import os
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import MedicineProduct, ProductSlugHistory
from apps.orders.models import CartItem, OrderItem
from apps.scrapers import ilacfiyati_twins

ACTION_TITLES = {ilacfiyati_twins.HIDE: "скрыть", ilacfiyati_twins.REVIEW: "на проверку"}


class Command(BaseCommand):
    help = "Две страницы ilacfiyati одного препарата: показ решений, --apply скрывает лишнюю."

    def add_arguments(self, parser):
        parser.add_argument("--barcode", action="append", default=[], help="Только этот штрихкод (можно несколько раз).")
        parser.add_argument("--csv", default="", help="Записать решения в CSV.")
        parser.add_argument("--apply", action="store_true", help="Скрыть строки «скрыть» (иначе только показ).")
        parser.add_argument("--backup", default="", help="JSON-файл бэкапа «до» (обязателен с --apply).")

    def handle(self, *args, **options):
        if options["apply"] and not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл>.")
        if options["apply"] and os.path.exists(options["backup"]):
            raise CommandError(f"Файл {options['backup']} уже есть — бэкап его не перезаписывает, укажите новый.")
        groups = ilacfiyati_twins.duplicate_barcode_groups()
        if options["barcode"]:
            groups = {barcode: rows for barcode, rows in groups.items() if barcode in options["barcode"]}
        decisions = [
            (barcode, decision)
            for barcode, products in groups.items()
            for decision in ilacfiyati_twins.decide_group(
                [ilacfiyati_twins.page_from_product(product) for product in products]
            )
        ]
        product_ids = [decision.page.pk for _barcode, decision in decisions]
        in_carts = Counter(CartItem.objects.filter(product_id__in=product_ids).values_list("product_id", flat=True))
        in_orders = Counter(OrderItem.objects.filter(product_id__in=product_ids).values_list("product_id", flat=True))

        header = [
            "штрихкод", "решение", "причина", "товар", "название в источнике", "цена", "в наличии", "источник",
            "оставить товар", "название в источнике", "цена", "в наличии", "источник", "в Списках заявки", "в заявках",
        ]
        rows = []
        for barcode, decision in decisions:
            page, keep = decision.page, decision.keep
            rows.append([
                barcode, ACTION_TITLES[decision.action], decision.reason,
                page.pk, page.source_name, page.price or "—", "да" if page.is_available else "нет", page.url,
                keep.pk, keep.source_name, keep.price or "—", "да" if keep.is_available else "нет", keep.url,
                in_carts[page.pk], in_orders[page.pk],
            ])
        self.stdout.write(" | ".join(header))
        for row in rows:
            self.stdout.write(" | ".join(str(value) for value in row))
        stats = Counter(ACTION_TITLES[decision.action] for _barcode, decision in decisions)
        self.stdout.write(
            f"Групп: {len(groups)}, скрыть: {stats['скрыть']}, на проверку: {stats['на проверку']}"
        )
        if options["csv"]:
            with open(options["csv"], "w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(header)
                writer.writerows(rows)

        if not options["apply"]:
            self.stdout.write("Показ: ничего не изменено. Для записи: --apply --backup <файл>.")
            return

        to_hide = [decision for _barcode, decision in decisions if decision.action == ilacfiyati_twins.HIDE]
        hidden_ids = [decision.page.pk for decision in to_hide]
        medicine_slugs = {}
        for base_id, slug in MedicineProduct.objects.filter(base_product_id__in=hidden_ids).values_list(
            "base_product_id", "slug"
        ):
            medicine_slugs.setdefault(base_id, []).append(slug)
        backup = []
        for decision in to_hide:
            product = decision.page.product
            slugs = sorted({product.slug, *medicine_slugs.get(product.pk, [])} - {"", None})
            backup.append({
                "product_id": product.pk,
                "keep_id": decision.keep.pk,
                "is_active": product.is_active,
                "external_data": product.external_data,
                "medicine_is_active": list(
                    MedicineProduct.objects.filter(base_product_id=product.pk).values("pk", "is_active")
                ),
                "slug_history_before": list(
                    ProductSlugHistory.objects.filter(old_slug__in=slugs).values("old_slug", "product_id", "product_type")
                ),
                "slugs": slugs,
            })
        with open(options["backup"], "w", encoding="utf-8") as fh:
            json.dump(backup, fh, ensure_ascii=False, indent=1, default=str)

        for decision in to_hide:
            ilacfiyati_twins.hide_twin(decision.page.product, decision.keep.product)
        self.stdout.write(self.style.SUCCESS(f"Скрыто: {len(to_hide)}. Бэкап: {options['backup']}"))
