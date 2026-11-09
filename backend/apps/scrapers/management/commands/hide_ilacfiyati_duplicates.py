"""Дубли лекарств и БАДов ilacfiyati по списку пар (показ по умолчанию).

Правило — apps.scrapers.ilacfiyati_duplicates, описание — docs/ILACFIYATI_DUPLICATES.md.
CSV пар: колонки keep_id и hide_id; необязательная same_source_page = 1, если старый адрес
источника скрываемой отдаёт 301 на адрес оставляемой (остальные колонки не читаются). Каждая пара
перепроверяется по базе: «скрыть» — полный дубль, «сомнительно» — любое расхождение,
такие пары не трогаются. Ничего не удаляется.

    manage.py hide_ilacfiyati_duplicates --pairs pairs.csv                         # показ
    manage.py hide_ilacfiyati_duplicates --pairs pairs.csv --csv decisions.csv     # показ + CSV
    manage.py hide_ilacfiyati_duplicates --pairs pairs.csv --apply --backup /backups/dups.json
    manage.py hide_ilacfiyati_duplicates --restore /backups/dups.json              # показ отката
    manage.py hide_ilacfiyati_duplicates --restore /backups/dups.json --apply      # откат
"""
import csv
import json
import os
from collections import Counter

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import Favorite, Product
from apps.orders.models import CartItem, OrderItem
from apps.scrapers import ilacfiyati_duplicates as dups
from apps.scrapers import ilacfiyati_twins

ACTION_TITLES = {dups.HIDE: "скрыть", dups.REVIEW: "сомнительно"}


def _read_pairs(path: str) -> list[tuple[int, int, bool]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not {"keep_id", "hide_id"} <= set(reader.fieldnames or ()):
            raise CommandError(f"В {path} нужны колонки keep_id и hide_id.")
        return [
            (int(row["keep_id"]), int(row["hide_id"]), str(row.get("same_source_page") or "").strip() == "1")
            for row in reader if row["keep_id"] and row["hide_id"]
        ]


def _favorites(products: list) -> Counter:
    """Сколько раз товар лежит в избранном (запись ссылается на Product или доменную карточку)."""
    counts = Counter()
    product_ct = ContentType.objects.get_for_model(Product)
    ids = [product.pk for product in products]
    for object_id in Favorite.objects.filter(content_type=product_ct, object_id__in=ids).values_list(
        "object_id", flat=True
    ):
        counts[object_id] += 1
    for product_type in dups.PRODUCT_TYPES:
        model = ilacfiyati_twins.domain_model(product_type)
        base_by_domain = dict(model.objects.filter(base_product_id__in=ids).values_list("pk", "base_product_id"))
        for object_id in Favorite.objects.filter(
            content_type=ContentType.objects.get_for_model(model), object_id__in=base_by_domain,
        ).values_list("object_id", flat=True):
            counts[base_by_domain[object_id]] += 1
    return counts


class Command(BaseCommand):
    help = "Дубли лекарств и БАДов ilacfiyati по списку пар: показ, --apply скрывает, --restore возвращает."

    def add_arguments(self, parser):
        parser.add_argument("--pairs", default="", help="CSV пар с колонками keep_id, hide_id.")
        parser.add_argument("--csv", default="", help="Записать решения в CSV.")
        parser.add_argument("--apply", action="store_true", help="Записать (иначе только показ).")
        parser.add_argument("--backup", default="", help="JSON-файл бэкапа «до» (обязателен с --apply).")
        parser.add_argument("--restore", default="", help="Вернуть товары из этого бэкапа.")

    def handle(self, *args, **options):
        if options["restore"]:
            return self._restore(options["restore"], apply=options["apply"])
        if not options["pairs"]:
            raise CommandError("Нужен --pairs <csv> или --restore <бэкап>.")
        if options["apply"] and not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл>.")
        if options["apply"] and os.path.exists(options["backup"]):
            raise CommandError(f"Файл {options['backup']} уже есть — бэкап его не перезаписывает, укажите новый.")

        decisions, missing = dups.decide_pairs(_read_pairs(options["pairs"]))
        hidden = [decision.hide for decision in decisions]
        hide_ids = [product.pk for product in hidden]
        in_carts = Counter(CartItem.objects.filter(product_id__in=hide_ids).values_list("product_id", flat=True))
        in_orders = Counter(OrderItem.objects.filter(product_id__in=hide_ids).values_list("product_id", flat=True))
        in_favorites = _favorites(hidden)

        header = [
            "решение", "причина", "тип", "оставить", "название в источнике", "цена", "в наличии", "штрихкод",
            "скрыть", "название в источнике", "цена", "в наличии", "штрихкод",
            "в Списках заявки", "в заявках", "в избранном", "источник оставляемой", "источник скрываемой",
        ]
        rows = []
        for decision in decisions:
            keep, hide = decision.keep, decision.hide
            rows.append([
                ACTION_TITLES[decision.action], decision.reason, hide.product_type,
                keep.pk, (keep.external_data or {}).get("source_name", ""), keep.price or "—",
                "да" if keep.is_available else "нет", dups.source_barcode(keep),
                hide.pk, (hide.external_data or {}).get("source_name", ""), hide.price or "—",
                "да" if hide.is_available else "нет", dups.source_barcode(hide),
                in_carts[hide.pk], in_orders[hide.pk], in_favorites[hide.pk], keep.external_url, hide.external_url,
            ])
        for keep_id, hide_id, reason in missing:
            rows.append(["сомнительно", reason, "", keep_id, "", "", "", "", hide_id] + [""] * 9)
        self.stdout.write(" | ".join(header))
        for row in rows:
            self.stdout.write(" | ".join(str(value) for value in row))
        stats = Counter(row[0] for row in rows)
        self.stdout.write(f"Пар: {len(rows)}, скрыть: {stats['скрыть']}, сомнительно: {stats['сомнительно']}")
        if options["csv"]:
            with open(options["csv"], "w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(header)
                writer.writerows(rows)

        if not options["apply"]:
            self.stdout.write("Показ: ничего не изменено. Для записи: --apply --backup <файл>.")
            return

        to_hide = [decision for decision in decisions if decision.action == dups.HIDE]
        backup = [dups.backup_row(decision.hide, decision.keep) for decision in to_hide]
        with open(options["backup"], "w", encoding="utf-8") as fh:
            json.dump(backup, fh, ensure_ascii=False, indent=1, default=str)
        for decision in to_hide:
            dups.hide_duplicate(decision.hide, decision.keep)
        self.stdout.write(self.style.SUCCESS(f"Скрыто: {len(to_hide)}. Бэкап: {options['backup']}"))

    def _restore(self, path: str, *, apply: bool):
        with open(path, encoding="utf-8") as fh:
            backup = json.load(fh)
        for row in backup:
            self.stdout.write(f"вернуть {row['product_id']} ({row['product_type']}), адреса: {', '.join(row['slugs'])}")
        if not apply:
            self.stdout.write(f"Показ отката: {len(backup)} товаров. Для записи: --restore {path} --apply.")
            return
        restored = sum(dups.restore_row(row) for row in backup)
        self.stdout.write(self.style.SUCCESS(f"Возвращено: {restored} из {len(backup)}."))
