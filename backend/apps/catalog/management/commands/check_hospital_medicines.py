"""Сверка признака «Больничный препарат» с правилом (TD-047, docs/HOSPITAL_MEDICINES.md).

Показывает показанные на сайте лекарства, которые по правилу apps.catalog.hospital_rule похожи на
больничные, но не отмечены, и наоборот — отмечены, но под правило не подходят. По умолчанию
ничего не меняет. --apply отмечает только неотмеченные; флажок ни у кого не снимается, цены и
наличие не меняются, ничего не скрывается.

    manage.py check_hospital_medicines                              # показ
    manage.py check_hospital_medicines --csv hospital.csv           # показ + CSV
    manage.py check_hospital_medicines --group Диализ               # только одна группа
    manage.py check_hospital_medicines --apply --backup /backups/hospital.json

Откат по бэкапу: MedicineProduct с id из файла — is_hospital=False (QuerySet.update).
"""
import csv
import json
import os
from collections import Counter
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django.db.models.fields.json import KeyTextTransform

from apps.catalog.hospital_rule import hospital_medicine_group
from apps.catalog.models import MedicineProduct
from apps.catalog.services.catalog_sort_rank import recompute_sort_ranks

UNMARKED = "подходит под правило, не отмечен"
MARKED_NO_RULE = "отмечен, под правило не подходит"
# Служебные карточки: заглушки аналогов и скрываемые вторые страницы источника.
SERVICE_KEYS = ("is_stub", "ilacfiyati_duplicate_of", "ilacfiyati_twin_of")
EXAMPLES = 20


class Command(BaseCommand):
    help = "Сверка «Больничный препарат» с правилом: показ, --apply отмечает неотмеченные."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default="", help="Записать расхождения в CSV.")
        parser.add_argument("--group", action="append", default=[],
                            help="Только группы, в названии которых есть этот текст (можно несколько раз).")
        parser.add_argument("--apply", action="store_true", help="Отметить неотмеченные (иначе только показ).")
        parser.add_argument("--backup", default="", help="JSON-файл бэкапа «до» (обязателен с --apply).")

    def handle(self, *args, **options):
        if options["apply"] and not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл>.")
        if options["apply"] and os.path.exists(options["backup"]):
            raise CommandError(f"Файл {options['backup']} уже есть — бэкап его не перезаписывает, укажите новый.")
        groups = [text.lower() for text in options["group"]]

        medicines = (
            MedicineProduct.objects
            .filter(is_active=True, base_product__isnull=False, base_product__product_type="medicines")
            .annotate(
                source_name=KeyTextTransform("source_name", "base_product__external_data"),
                **{key: KeyTextTransform(key, "base_product__external_data") for key in SERVICE_KEYS},
            )
            .values(
                "id", "base_product_id", "name", "atc_code", "is_hospital", "is_available", "price",
                "external_url", "base_product__slug", "source_name", *SERVICE_KEYS,
            )
            .order_by("id")
        )
        header = [
            "расхождение", "группа", "product_id", "medicine_id", "в наличии", "есть цена", "ATC",
            "название в источнике", "название на сайте", "ссылка",
        ]
        rows, to_mark, total = [], [], 0
        for medicine in medicines.iterator(chunk_size=2000):
            if any(medicine[key] not in (None, "", "false") for key in SERVICE_KEYS):
                continue
            total += 1
            # Название источника хранится не у всех старых карточек; адрес страницы
            # IlacFiyati — то же турецкое название через дефисы.
            source_text = medicine["source_name"] or " ".join(
                [medicine["name"], urlparse(medicine["external_url"] or "").path.rsplit("/", 1)[-1].replace("-", " ")]
            )
            group = hospital_medicine_group(source_text, medicine["atc_code"])
            if bool(group) == medicine["is_hospital"]:
                continue
            if group and groups and not any(text in group.lower() for text in groups):
                continue
            if group:
                to_mark.append(medicine["id"])
            rows.append([
                UNMARKED if group else MARKED_NO_RULE, group, medicine["base_product_id"], medicine["id"],
                "да" if medicine["is_available"] else "нет", "да" if medicine["price"] else "нет",
                medicine["atc_code"], medicine["source_name"] or "", medicine["name"],
                f"https://mudaroba.com/product/{medicine['base_product__slug']}",
            ])

        for kind in (UNMARKED, MARKED_NO_RULE):
            kind_rows = [row for row in rows if row[0] == kind]
            self.stdout.write(f"\n{kind}: {len(kind_rows)}")
            for group, count in Counter(row[1] for row in kind_rows if row[1]).most_common():
                self.stdout.write(f"  {group}: {count}")
            for row in kind_rows[:EXAMPLES]:
                self.stdout.write("  " + " | ".join(str(value) for value in row[1:8]))
            if len(kind_rows) > EXAMPLES:
                self.stdout.write(f"  … ещё {len(kind_rows) - EXAMPLES} (весь список — в --csv)")
        self.stdout.write(f"\nПроверено показанных лекарств: {total}")
        if options["csv"]:
            with open(options["csv"], "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(header)
                writer.writerows(rows)
            self.stdout.write(f"CSV: {options['csv']}")

        if not options["apply"]:
            self.stdout.write("Показ: ничего не изменено. Для записи: --apply --backup <файл>.")
            return

        backup = list(
            MedicineProduct.objects.filter(id__in=to_mark, is_hospital=False)
            .values("id", "base_product_id", "is_hospital")
        )
        with open(options["backup"], "w", encoding="utf-8") as fh:
            json.dump(backup, fh, ensure_ascii=False, indent=1)
        marked = MedicineProduct.objects.filter(id__in=to_mark, is_hospital=False).update(is_hospital=True)
        # Больничный стоит в разделе после товаров с ценой — порядок пересчитываем сразу.
        recompute_sort_ranks(MedicineProduct)
        self.stdout.write(self.style.SUCCESS(f"Отмечено: {marked}. Бэкап: {options['backup']}"))
