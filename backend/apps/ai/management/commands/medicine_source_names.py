"""Турецкие названия лекарств, у которых name переведён или обрезан прежней обработкой.

Для каждого лекарства, чьё name не похоже на турецкий оригинал (кириллица или
число без единицы в конце: «MOUNJARO 7»), показывает, откуда AI-обработка
возьмёт турецкое название (medicine_title.medicine_source_name): из
external_data["source_name"] или из строки вкладки аналогов с тем же
штрихкодом, — и строится ли из него шаблон названия. Для остальных — URL для
перескрейпа: парсер ilacfiyati запишет source_name при следующем скрейпе.

Без --dry-run название из вкладки аналогов записывается в
external_data["source_name"]; name товара не меняется.

    manage.py medicine_source_names --dry-run
    manage.py medicine_source_names
"""

from collections import Counter

from django.core.management.base import BaseCommand

from apps.ai.services.medicine_title import build_medicine_title, looks_like_source_name, medicine_source_name
from apps.ai.services.ownership import remember_source_name
from apps.catalog.models import Product


class Command(BaseCommand):
    help = "Турецкие названия лекарств с переведённым или обрезанным name; URL для перескрейпа"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Только отчёт; БД не меняется")

    def handle(self, *args, **options):
        medicines = Product.objects.filter(product_type="medicines")
        total = 0
        broken_ids = []
        for pk, name in medicines.values_list("pk", "name").iterator(chunk_size=2000):
            total += 1
            if not looks_like_source_name(name):
                broken_ids.append(pk)

        found = Counter()
        templates = 0
        rescrape = []
        products = medicines.filter(pk__in=broken_ids).order_by("pk").only(
            "pk", "name", "external_url", "external_data"
        )
        self.stdout.write(f"Лекарств: {total}, name переведён или обрезан: {len(broken_ids)}\n")
        for product in products:
            source, origin = medicine_source_name(product.name, product.external_data)
            if origin == "name":
                rescrape.append(product)
                continue
            found[origin] += 1
            template = build_medicine_title(source)
            templates += bool(template)
            self.stdout.write(
                f"{product.pk}\t{origin}\t{product.name!r} → {source!r}"
                + ("" if template else "\tшаблон не строится")
            )
            if origin == "equivalents" and not options["dry_run"]:
                remember_source_name(product.external_data, source)
                product.save(update_fields=["external_data"])

        self.stdout.write(
            f"\nТурецкое название без перескрейпа: {sum(found.values())} "
            f"(source_name {found['source_name']}, вкладка аналогов {found['equivalents']}); "
            f"шаблон строится у {templates}"
        )
        if found["equivalents"] and not options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Записано в source_name: {found['equivalents']}"))
        self.stdout.write(f"\nНужен перескрейп по URL: {len(rescrape)}")
        for product in rescrape:
            self.stdout.write(f"{product.pk}\t{product.name!r}\t{product.external_url or '— нет URL'}")
