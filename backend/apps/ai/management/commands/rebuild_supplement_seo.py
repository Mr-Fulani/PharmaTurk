"""Пересобрать SEO БАДов кодом из готовых AI-логов, без модели (SEO-ядро 07.11.2026).

    manage.py rebuild_supplement_seo --ids 3958,537            # показать было/стало
    manage.py rebuild_supplement_seo --all --show 20           # все БАДы, только показ
    manage.py rebuild_supplement_seo --all --apply --backup /tmp/supp-seo-before.json
    manage.py rebuild_supplement_seo --restore /tmp/supp-seo-before.json

Меняются только SEO title / description / keywords (RU и EN); название (H1) не меняется.
Поле, изменённое вручную после обработки, остаётся (apps/ai/services/supplement_seo_refresh.py).
"""

import json
from collections import Counter

from django.core import serializers
from django.core.management.base import BaseCommand, CommandError

from apps.ai.services.supplement_seo_refresh import SEO_FIELDS, apply_seo, plan_seo
from apps.catalog.models import Product


class Command(BaseCommand):
    help = "SEO БАДов — заново кодом из AI-логов (без модели), с бэкапом строк."

    def add_arguments(self, parser):
        parser.add_argument("--ids", help="id товаров через запятую")
        parser.add_argument("--all", action="store_true", help="Все БАДы")
        parser.add_argument("--apply", action="store_true", help="Записать (без него — только показать)")
        parser.add_argument("--backup", help="Файл бэкапа строк перед записью (обязателен с --apply)")
        parser.add_argument("--restore", help="Вернуть строки из файла бэкапа")
        parser.add_argument("--show", type=int, default=10, help="Сколько примеров показать")

    def handle(self, *args, **options):
        if options["restore"]:
            return self._restore(options["restore"])
        if options["apply"] and not options["backup"]:
            raise CommandError("--apply требует --backup <файл>")
        if bool(options["ids"]) == bool(options["all"]):
            raise CommandError("Нужно одно из: --ids 1,2,3 или --all")
        products = Product.objects.filter(product_type="supplements").order_by("id")
        if options["ids"]:
            products = products.filter(id__in=[int(x) for x in options["ids"].split(",") if x.strip()])
        stats, plans = Counter(), []
        for product in products.iterator(chunk_size=200):
            stats["товаров"] += 1
            changes, new, skipped = plan_seo(product)
            if skipped:
                stats[f"пропущено: {skipped}"] += 1
                continue
            if not changes:
                stats["уже как в коде или правлено вручную"] += 1
                continue
            stats["к изменению"] += 1
            stats["полей"] += len(changes)
            plans.append((product, changes, new))
        for product, changes, _new in plans[: options["show"]]:
            self.stdout.write(f"\n{product.id} {product.slug}")
            for change in changes:
                if change.field in ("meta_title", "meta_description") and change.locale == "ru":
                    self.stdout.write(f"  {change.label}: {change.old!r}\n    → {change.new!r}")
        self.stdout.write("\n" + json.dumps(dict(stats), ensure_ascii=False))
        if not options["apply"]:
            self.stdout.write("Только показ: для записи — --apply --backup <файл>.")
            return
        objects = {id(change.obj): change.obj for _p, changes, _n in plans for change in changes}
        with open(options["backup"], "w") as handle:
            handle.write(serializers.serialize("json", list(objects.values())))
        for _product, changes, new in plans:
            apply_seo(changes, new)
        self.stdout.write(f"Записано товаров: {len(plans)}, бэкап строк: {options['backup']} ({len(objects)} строк).")

    def _restore(self, path):
        with open(path) as handle:
            rows = list(serializers.deserialize("json", handle.read()))
        # Только SEO-поля: описание, записанное после бэкапа, остаётся. Обычный save(), а не
        # DeserializedObject.save(): у домена он синхронизирует Product.
        restored = 0
        for row in rows:
            current = type(row.object).objects.filter(pk=row.object.pk).first()
            if current is None:
                continue
            for field in SEO_FIELDS:
                setattr(current, field, getattr(row.object, field))
            current.save(update_fields=list(SEO_FIELDS))
            restored += 1
        self.stdout.write(f"Возвращено строк: {restored} из {len(rows)} ({path}).")
