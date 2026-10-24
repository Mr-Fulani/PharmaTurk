"""Пересчитать отметку «ввоз ограничен» у всех лекарств по справочнику (TD-024).

    manage.py refresh_import_restrictions            # пересчитать и показать итог
    manage.py refresh_import_restrictions --dry-run  # только показать

Нужно после обновления apps/catalog/data/controlled_substances.json: при сохранении товара
отметка пересчитывается сама (сигнал), а справочник сам товары не трогает.
"""

from collections import Counter

from django.core.management.base import BaseCommand

from apps.catalog.controlled_substances import refresh_medicine
from apps.catalog.models import MedicineProduct


class Command(BaseCommand):
    help = "Отметка «ввоз ограничен» у лекарств — заново по справочнику контролируемых веществ."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Только показать, не записывать")

    def handle(self, *args, **options):
        stats, examples = Counter(), []
        for medicine in MedicineProduct.objects.only(
            "id", "name", "active_ingredient", "import_restricted_countries", "import_restriction_note"
        ).iterator(chunk_size=1000):
            if not refresh_medicine(medicine):
                continue
            stats["изменилось"] += 1
            for country in medicine.import_restricted_countries.split(",") if medicine.import_restricted_countries else ["снято"]:
                stats[country] += 1
            if len(examples) < 15:
                examples.append(f"  {medicine.id} {medicine.name[:60]} → {medicine.import_restricted_countries or 'снято'}")
            if not options["dry_run"]:
                MedicineProduct.objects.filter(pk=medicine.pk).update(
                    import_restricted_countries=medicine.import_restricted_countries,
                    import_restriction_note=medicine.import_restriction_note,
                )
        self.stdout.write("\n".join(examples))
        total = MedicineProduct.objects.exclude(import_restricted_countries="").count()
        self.stdout.write(f"{dict(stats)} | с отметкой всего: {total}{' (dry-run, не записано)' if options['dry_run'] else ''}")
