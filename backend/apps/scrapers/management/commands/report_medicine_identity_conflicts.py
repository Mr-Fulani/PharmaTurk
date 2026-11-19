"""Сколько карточек IlacFiyati расходится с источником и почему (TD-045). По умолчанию — только показ.

Парсер сверяет лекарство с источником перед записью (`medicine_categories`). Команда
считает по базе, без сети, какие карточки попадают под каждую причину расхождения:

- `barcode_conflict`, `atc_code_conflict`, `active_ingredient_conflict` — сохранённые
  значения карточки расходятся между собой: поле медикамента против ответа источника в
  `external_data.attributes` товара и медикамента. У вещества три подслучая: то же
  вещество в другом написании (после TD-045 не расхождение), поле записано по-русски
  (с источником не сравнить — сверка считает вещество неизвестным), вещества разные;
- `variant_or_product_type_conflict`, случай «а» — страница лекарства IlacFiyati
  (`/ilaclar/…`) ведёт на товар, который у нас не лекарство;
- `variant_or_product_type_conflict`, случай «б» — у лекарства `external_id` не тот, что
  в адресе его страницы, и страницу не ведёт другой товар. Это кандидаты: парсер
  считает такой ответ «вариантом», только если не нашёл карточку по точному адресу.

Для каждой строки указано, получит ли карточка цену и наличие при следующем проходе.

    manage.py report_medicine_identity_conflicts                          # показ: числа и примеры
    manage.py report_medicine_identity_conflicts --csv /backups/td045.csv # то же + выгрузка

Починка поля вещества (только подслучай «вещества разные», когда оба сохранённых ответа
источника называют одно вещество, а поле записано латиницей и не пустое): в поле
ставится запись источника. Пишется только `MedicineProduct.active_ingredient` через
`update()` (без сигналов). Заглушки аналогов и поле по-русски не трогает.

    manage.py report_medicine_identity_conflicts --apply --backup /backups/medicine-ingredient-YYYYMMDD.json
    manage.py report_medicine_identity_conflicts --restore /backups/medicine-ingredient-YYYYMMDD.json  # откат
"""
import csv
import json
import re
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import MedicineProduct, Product
from apps.scrapers.ilacfiyati_duplicates import is_real_barcode
from apps.scrapers.medicine_categories import _mapping, _normalized, _source_page
from apps.scrapers.services import ScraperIntegrationService

PRICE_YES = "цена и наличие обновятся"
PRICE_BARCODE = "цена и наличие обновятся, если штрихкод источника тот же"
PRICE_NO = "пропуск: у карточки нет одного настоящего штрихкода"
SAME_SUBSTANCE = "то же вещество, другое написание — после TD-045 не расхождение"
CYRILLIC_FIELD = "поле записано по-русски"
DIFFERENT_SUBSTANCE = "вещества разные"
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
CSV_COLUMNS = (
    "product_id", "medicine_id", "название", "причина", "подслучай", "что будет при проходе парсера",
    "поле", "у нас (поле)", "источник (external_data товара)", "источник (external_data медикамента)",
    "тип товара", "external_id", "external_url", "показан", "в наличии", "last_synced_at",
)


def _text(value):
    return str(value or "").strip()


def _old_ingredient(value):
    """Сравнение вещества до TD-045: регистр и пробелы."""
    return " ".join(_text(value).casefold().split())


class Command(BaseCommand):
    help = "Карточки IlacFiyati, расходящиеся с источником: числа по причинам, CSV, починка поля вещества."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default="", help="Куда выгрузить все строки (файл не должен существовать).")
        parser.add_argument("--sample", type=int, default=5, help="Сколько примеров на подслучай показать (5).")
        parser.add_argument("--apply", action="store_true", help="Починить поле вещества (иначе только показ).")
        parser.add_argument("--backup", default="", help="JSON-файл с прежними значениями (обязателен с --apply).")
        parser.add_argument("--restore", default="", help="Вернуть прежние значения поля из файла --backup.")

    def handle(self, *args, **options):
        if options["restore"]:
            return self._restore(options["restore"])
        rows, repairs = self._medicine_rows()
        rows += self._page_rows()

        totals = Counter((row["причина"], row["подслучай"], row["что будет при проходе парсера"]) for row in rows)
        self.stdout.write(f"Строк с расхождением: {len(rows)}")
        for (reason, case, outcome), count in sorted(totals.items()):
            self.stdout.write(f"\n{reason} — {case or 'без подслучая'}: {count} ({outcome})")
            shown = 0
            for row in rows:
                if shown >= options["sample"]:
                    break
                if (row["причина"], row["подслучай"], row["что будет при проходе парсера"]) != (reason, case, outcome):
                    continue
                shown += 1
                self.stdout.write(
                    f"  {row['product_id']}: {row['название']} — у нас «{row['у нас (поле)']}»,"
                    f" источник «{row['источник (external_data товара)'] or row['источник (external_data медикамента)']}»"
                )
        if options["csv"]:
            try:
                with open(options["csv"], "x", encoding="utf-8-sig", newline="") as output:
                    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
                    writer.writeheader()
                    writer.writerows(rows)
            except FileExistsError:
                raise CommandError(f"Файл {options['csv']} уже есть — не перезаписываем.")
            self.stdout.write(f"\nВыгружено строк: {len(rows)} → {options['csv']}")

        self.stdout.write(f"\nПоле вещества можно починить по источнику: {len(repairs)}")
        if not options["apply"]:
            self.stdout.write("Показ: ничего не изменено. Для починки поля вещества: --apply --backup <файл>.")
            return
        if not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл> с прежними значениями.")
        try:
            with open(options["backup"], "x", encoding="utf-8") as backup:
                json.dump(repairs, backup, ensure_ascii=False, indent=1)
        except FileExistsError:
            raise CommandError(f"Файл {options['backup']} уже есть — прежнюю копию не перезаписываем.")
        changed = 0
        with transaction.atomic():
            for row in repairs:
                # Условие по прежнему значению: правку, сделанную после чтения, не затираем.
                changed += MedicineProduct.objects.filter(
                    pk=row["medicine_id"], active_ingredient=row["before"],
                ).update(active_ingredient=row["after"])
        self.stdout.write(f"Исправлено: {changed}. Прежние значения: {options['backup']}")

    def _restore(self, path):
        with open(path, encoding="utf-8") as backup:
            rows = json.load(backup)
        restored = 0
        with transaction.atomic():
            for row in rows:
                # Поле, изменённое после починки, не трогаем.
                restored += MedicineProduct.objects.filter(
                    pk=row["medicine_id"], active_ingredient=row["after"],
                ).update(active_ingredient=row["before"])
        self.stdout.write(f"Возвращено: {restored} из {len(rows)}")

    @staticmethod
    def _row(product, medicine_id, reason, case, outcome, field="", ours="", base="", own=""):
        return {
            "product_id": product["pk"], "medicine_id": medicine_id or "", "название": product["name"],
            "причина": reason, "подслучай": case, "что будет при проходе парсера": outcome,
            "поле": field, "у нас (поле)": _text(ours), "источник (external_data товара)": _text(base),
            "источник (external_data медикамента)": _text(own),
            "тип товара": product["product_type"], "external_id": product["external_id"] or "",
            "external_url": product["external_url"] or "", "показан": product["is_active"],
            "в наличии": product["is_available"], "last_synced_at": product["last_synced_at"] or "",
        }

    def _medicine_rows(self):
        """Сохранённые значения карточки расходятся между собой — в порядке сверки парсера."""
        rows, repairs = [], []
        medicines = (
            MedicineProduct.objects
            .filter(base_product__product_type="medicines", base_product__external_data__source="ilacfiyati")
            .select_related("base_product").order_by("pk")
        )
        for medicine in medicines.iterator(chunk_size=1000):
            base = medicine.base_product
            product = {field: getattr(base, field) for field in (
                "pk", "name", "product_type", "external_id", "external_url", "is_active", "is_available",
                "last_synced_at",
            )}
            base_attrs = _mapping(_mapping(base.external_data).get("attributes"))
            own_attrs = _mapping(_mapping(medicine.external_data).get("attributes"))
            stub = any(_mapping(item.external_data).get("is_stub") is True for item in (base, medicine))
            barcodes = {_text(value) for value in (
                base_attrs.get("barcode"), own_attrs.get("barcode"), medicine.barcode,
            ) if _text(value)}
            same_package = len(barcodes) == 1 and is_real_barcode(next(iter(barcodes)))
            for field in ("barcode",) if stub else ("barcode", "atc_code", "active_ingredient"):
                values = (getattr(medicine, field), base_attrs.get(field), own_attrs.get(field))
                if len({
                    _old_ingredient(value) if field == "active_ingredient" else _normalized(value, field)
                    for value in values if _text(value)
                }) <= 1:
                    continue
                case, outcome = "", (PRICE_BARCODE if same_package else PRICE_NO)
                if field == "barcode":
                    outcome = "пропуск: штрихкоды карточки расходятся"
                elif field == "active_ingredient":
                    keys = [_normalized(value, field) for value in values if _text(value)]
                    source_keys = {_normalized(value, field) for value in values[1:] if _text(value)}
                    same = len(set(keys) - {frozenset()}) <= 1
                    if same:
                        case, outcome = SAME_SUBSTANCE, "обновится целиком"
                    if _CYRILLIC_RE.search(_text(values[0])):
                        # Русскую запись с источником не сравнить: для сверки вещество неизвестно.
                        case = CYRILLIC_FIELD
                    elif not same:
                        case = DIFFERENT_SUBSTANCE
                        if (_text(values[0]) and _text(values[1]) and _text(values[2])
                                and len(source_keys) == 1 and frozenset() not in source_keys):
                            repairs.append({
                                "medicine_id": medicine.pk, "product_id": base.pk, "name": medicine.name,
                                "before": medicine.active_ingredient, "after": _text(values[2])[:300],
                            })
                rows.append(self._row(product, medicine.pk, f"{field}_conflict", case, outcome, field, *values))
                break
        return rows, repairs

    def _page_rows(self):
        """Страница лекарства ведёт на товар другого типа («а») или с другим external_id («б»)."""
        rows = []
        products = list(
            Product.objects.filter(external_url__contains="ilacfiyati.com/ilaclar/").order_by("pk").values(
                "pk", "name", "product_type", "external_id", "external_url", "is_active", "is_available",
                "last_synced_at", "external_data__attributes__barcode", "medicine_item__barcode",
                "medicine_item__external_data__attributes__barcode",
            )
        )
        page_owners = {product["external_id"].casefold() for product in products if product["external_id"]}
        for product in products:
            page = _source_page(product["external_url"])
            slug = page[1] if len(page) == 2 else ""
            barcodes = {_text(product.pop(key)) for key in (
                "external_data__attributes__barcode", "medicine_item__barcode",
                "medicine_item__external_data__attributes__barcode",
            )} - {""}
            if product["product_type"] != "medicines":
                rows.append(self._row(
                    product, None, "variant_or_product_type_conflict",
                    f"а: у нас не лекарство ({product['product_type']})", PRICE_YES,
                    "product_type", product["product_type"], "medicines",
                ))
            elif (
                slug and product["external_id"] and product["external_id"].casefold() != slug
                and product["external_id"] not in ScraperIntegrationService.ILACFIYATI_DETAIL_TAB_EXTERNAL_IDS
                and slug not in page_owners
            ):
                rows.append(self._row(
                    product, None, "variant_or_product_type_conflict", "б: external_id не совпадает с адресом страницы",
                    PRICE_BARCODE if len(barcodes) == 1 and is_real_barcode(next(iter(barcodes))) else PRICE_NO,
                    "external_id", product["external_id"], slug,
                ))
        return rows
