"""Загрузка спроса из поисковиков в таблицу «Спрос из поиска» (docs/CATALOG_SEARCH_DEMAND.md).

Файл CSV со столбцами ``name,frequency`` и необязательным ``note``. Без ``--apply``
только показывает, что изменится. Строки, которых нет в файле, не трогает.
"""
import csv

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models_search import SearchDemand


class Command(BaseCommand):
    help = "Загружает спрос из поиска (название, запросов в месяц) из CSV. Без --apply — только показ."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--type", default="medicines", choices=[key for key, _ in SearchDemand.PRODUCT_TYPES])
        parser.add_argument("--apply", action="store_true", help="Записать в базу.")

    def handle(self, *args, csv_path, **options):
        product_type = options["type"]
        with open(csv_path, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if not rows or "name" not in rows[0] or "frequency" not in rows[0]:
            raise CommandError("В файле нужны столбцы name и frequency.")

        existing = {row.name_prefix: row for row in SearchDemand.objects.filter(product_type=product_type)}
        created = changed = same = 0
        for row in rows:
            name = row["name"].strip()
            frequency = int(row["frequency"])
            note = (row.get("note") or "").strip()
            current = existing.get(name)
            if current is None:
                created += 1
                self.stdout.write(f"новая: {name} — {frequency}")
                if options["apply"]:
                    SearchDemand.objects.create(
                        product_type=product_type, name_prefix=name, frequency=frequency, note=note
                    )
            elif current.frequency != frequency:
                changed += 1
                self.stdout.write(f"изменится: {name} — {current.frequency} → {frequency}")
                if options["apply"]:
                    current.frequency = frequency
                    current.save(update_fields=["frequency", "updated_at"])
            else:
                same += 1

        done = "Записано" if options["apply"] else "Показ без записи (для записи добавьте --apply)"
        self.stdout.write(f"{done}: новых {created}, изменённых {changed}, без изменений {same}.")
