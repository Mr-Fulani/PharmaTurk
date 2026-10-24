"""Пересчитать название и SEO опубликованных лекарств кодом, без модели (TD-028).

    manage.py medicine_refresh_code_fields                    # только показать
    manage.py medicine_refresh_code_fields --ids 746,2305     # выбранные товары
    manage.py medicine_refresh_code_fields --apply --backup /tmp/refresh-before.json

Меняется только то, что не правили руками после обработки (apps/ai/services/medicine_refresh.py).
"""

import json
from collections import Counter

from django.core import serializers
from django.core.management.base import BaseCommand, CommandError

from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.medicine_refresh import apply_refresh, latest_applied_log, plan_refresh
from apps.catalog.models import Product


class Command(BaseCommand):
    help = "Название и SEO опубликованных лекарств — заново кодом (без модели), с бэкапом строк."

    def add_arguments(self, parser):
        parser.add_argument("--ids", help="id товаров через запятую (по умолчанию — все обработанные лекарства)")
        parser.add_argument("--apply", action="store_true", help="Записать (без него — только показать)")
        parser.add_argument("--backup", help="Файл бэкапа строк перед записью (обязателен с --apply)")
        parser.add_argument("--show", type=int, default=10, help="Сколько примеров показать")

    def handle(self, *args, **options):
        if options["apply"] and not options["backup"]:
            raise CommandError("--apply требует --backup <файл>")
        products = Product.objects.filter(product_type="medicines").select_related("medicine_item")
        if options["ids"]:
            products = products.filter(id__in=[int(x) for x in options["ids"].split(",") if x.strip()])
        generator = ContentGenerator.__new__(ContentGenerator)
        generator.llm = None
        stats, plans = Counter(), []
        for product in products.iterator(chunk_size=200):
            log = latest_applied_log(product.id)
            if not log:
                continue
            stats["обработанных"] += 1
            changes, new = plan_refresh(product, log, generator)
            if new is None:
                stats["название кодом не собирается"] += 1
                continue
            if not changes:
                stats["уже как в коде или правлено вручную"] += 1
                continue
            stats["к изменению"] += 1
            stats["полей"] += len(changes)
            plans.append((product, log, changes, new))
        for product, _log, changes, _new in plans[: options["show"]]:
            self.stdout.write(f"\n{product.id} {product.slug}")
            for change in changes:
                if change.field in ("name", "meta_title", "meta_description"):
                    self.stdout.write(f"  {change.label}: {change.old[:90]!r} → {change.new[:90]!r}")
        self.stdout.write("\n" + json.dumps(dict(stats), ensure_ascii=False))
        if not options["apply"]:
            self.stdout.write("Только показ: для записи — --apply --backup <файл>.")
            return
        objects = {id(change.obj): change.obj for _p, _l, changes, _n in plans for change in changes}
        with open(options["backup"], "w") as handle:
            handle.write(serializers.serialize("json", list(objects.values())))
        for _product, log, changes, new in plans:
            apply_refresh(log, changes, new)
        self.stdout.write(f"Записано товаров: {len(plans)}, бэкап строк: {options['backup']} ({len(objects)} строк).")
