"""Вернуть лекарствам их собственный код АТХ (только показ по умолчанию).

Заглушка аналога получала ATC родительского препарата. Когда парсер IlacFiyati
позже читал её полную карточку, верный код источника попадал в
`external_data.attributes.atc_code` товара и медикамента, а поле
`MedicineProduct.atc_code` оставалось чужим (BRUFEN таблетки — M02AA13 вместо
M01AE01). Из-за расхождения парсер пропускал карточку целиком.

Команда правит только поле `atc_code` и только там, где коды из обоих
сохранённых ответов источника совпадают между собой и отличаются от поля.
Категорию, название, описание, SEO и цену не трогает; пишет `update()` без
сигналов; в сеть не ходит. Заглушки аналогов пропускает.

    manage.py repair_medicine_atc_codes                              # показ
    manage.py repair_medicine_atc_codes --apply --backup /backups/atc_codes.json
    manage.py repair_medicine_atc_codes --restore /backups/atc_codes.json   # откат
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import MedicineProduct
from apps.scrapers.medicine_categories import _normalized


def _code(value):
    return _normalized(value if isinstance(value, str) else "", "atc_code")


class Command(BaseCommand):
    help = "Ставит MedicineProduct.atc_code по коду источника из external_data обеих записей."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Изменить данные (иначе только показ).")
        parser.add_argument("--backup", default="", help="JSON-файл с прежними значениями (обязателен с --apply).")
        parser.add_argument("--sample", type=int, default=20, help="Сколько примеров показать (20).")
        parser.add_argument("--restore", default="", help="Вернуть прежние коды из файла --backup.")

    def handle(self, *args, **options):
        if options["restore"]:
            with open(options["restore"], encoding="utf-8") as backup:
                rows = json.load(backup)
            restored = 0
            with transaction.atomic():
                for row in rows:
                    # Код, изменённый после починки, не трогаем.
                    restored += MedicineProduct.objects.filter(
                        pk=row["medicine_id"], atc_code=row["atc_code_after"],
                    ).update(atc_code=row["atc_code_before"])
            self.stdout.write(f"Возвращено: {restored} из {len(rows)}")
            return
        rows = []
        medicines = (
            MedicineProduct.objects.filter(base_product__product_type="medicines")
            .exclude(atc_code="")
            .order_by("pk")
            .values_list(
                "pk", "base_product_id", "name", "atc_code",
                "external_data__attributes__atc_code",
                "base_product__external_data__attributes__atc_code",
                "external_data__is_stub", "base_product__external_data__is_stub",
            )
        )
        for pk, product_id, name, current, own, base, own_stub, base_stub in medicines.iterator(chunk_size=2000):
            if own_stub is True or base_stub is True:
                continue
            source = _code(own)
            if not source or source != _code(base) or source == _code(current):
                continue
            rows.append({
                "medicine_id": pk, "product_id": product_id, "name": name,
                "atc_code_before": current, "atc_code_after": own.strip()[:100],
            })

        self.stdout.write(f"Лекарств с чужим кодом АТХ в поле: {len(rows)}")
        for row in rows[: options["sample"]]:
            self.stdout.write(
                f"  {row['product_id']}: {row['name']} — {row['atc_code_before']} → {row['atc_code_after']}"
            )
        if not options["apply"]:
            self.stdout.write("Показ: ничего не изменено. Для записи: --apply --backup <файл>.")
            return
        if not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл> с прежними значениями.")

        try:
            with open(options["backup"], "x", encoding="utf-8") as backup:
                json.dump(rows, backup, ensure_ascii=False, indent=1)
        except FileExistsError:
            raise CommandError(f"Файл {options['backup']} уже есть — прежнюю копию не перезаписываем.")
        changed = 0
        with transaction.atomic():
            for row in rows:
                # Условие по прежнему значению: правку, сделанную после чтения, не затираем.
                changed += MedicineProduct.objects.filter(
                    pk=row["medicine_id"], atc_code=row["atc_code_before"],
                ).update(atc_code=row["atc_code_after"])
        self.stdout.write(f"Исправлено: {changed}. Прежние значения: {options['backup']}")
