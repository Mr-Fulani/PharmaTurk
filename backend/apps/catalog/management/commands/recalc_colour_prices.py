"""Разовый пересчёт цены, зачёркнутой и наличия товаров с цветами (показ по умолчанию).

До 04.11.2026 цену товара с цветами задавал первый цвет с ценой, даже
распроданный, а зачёркнутую — главный цвет парсера: витрина показывала одну
цену, сортировка и фильтр шли по другой. Теперь везде одно правило
``default_fashion_variant`` (первый по порядку цвет в наличии, зачёркнутая —
того же цвета). Команда сразу после релиза приводит к нему ``Product`` и
доменную карточку по сохранённым цветам — без запросов к источникам, не дожидаясь
следующего прохода парсера. Ручные источники (Instagram) не трогаются.

    manage.py recalc_colour_prices                                       # отчёт
    manage.py recalc_colour_prices --apply --backup /backups/colour_prices.json
"""
import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Prefetch
from django.db.models.fields.json import KT
from django.utils import timezone

from apps.catalog.models import (
    ClothingProduct,
    HeadwearProduct,
    IslamicClothingProduct,
    Product,
    ShoeProduct,
    UnderwearProduct,
)
from apps.catalog.utils.default_variant import default_fashion_variant
from apps.catalog.utils.old_price import source_old_price
from apps.scrapers.services import DEFAULT_ASSUMED_STOCK_QUANTITY

DOMAIN_MODELS = {
    "clothing": ClothingProduct,
    "shoes": ShoeProduct,
    "headwear": HeadwearProduct,
    "underwear": UnderwearProduct,
    "islamic_clothing": IslamicClothingProduct,
}
# Зачёркнутую по цветам передают все эти парсеры, кроме LCW.
COLOUR_OLD_PRICE_SOURCES = frozenset({"flo", "zara", "bershka", "pullandbear", "massimodutti", "superstep"})
SOURCES = COLOUR_OLD_PRICE_SOURCES | {"lcw"}
FIELDS = ("price", "old_price", "currency", "is_available", "stock_quantity")
EXAMPLES = 10


def target_values(source: str, current: dict, colours: list) -> dict:
    """Цена, зачёркнутая и наличие карточки по сохранённым цветам — как при импорте."""
    default = default_fashion_variant(colours)
    any_available = any(row.is_available for row in colours)
    total_stock = sum(row.stock_quantity or 0 for row in colours if row.stock_quantity)
    values = {
        "is_available": any_available,
        "stock_quantity": (
            DEFAULT_ASSUMED_STOCK_QUANTITY if any_available else (total_stock if total_stock > 0 else None)
        ),
    }
    if default.price is not None:
        old_price = default.old_price if source in COLOUR_OLD_PRICE_SOURCES else current["old_price"]
        values.update(
            price=default.price,
            currency=default.currency or current["currency"],
            old_price=source_old_price(old_price, default.price),
        )
    return values


class Command(BaseCommand):
    help = "Пересчитывает цену, зачёркнутую и наличие товаров с цветами по правилу default_fashion_variant."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Изменить данные (иначе только отчёт).")
        parser.add_argument("--backup", default="", help="JSON-файл со значениями «до» (обязателен с --apply).")
        parser.add_argument("--batch-size", type=int, default=500, help="Товаров за одну пачку (500).")

    def handle(self, *args, **options):
        if options["apply"] and not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл> со значениями «до».")
        batch_size = max(1, min(options["batch_size"], 5000))
        rows = list(
            Product.objects.annotate(source=KT("external_data__source"))
            .filter(source__in=SOURCES, product_type__in=list(DOMAIN_MODELS))
            .order_by("pk")
            .values_list("pk", "source", "product_type")
        )
        changes = []
        for start in range(0, len(rows), batch_size):
            changes.extend(self._batch_changes(rows[start:start + batch_size]))

        by_source = Counter(change["source"] for change in changes)
        price_changes = Counter(
            change["source"]
            for change in changes
            if "price" in change["after"] and change["after"]["price"] != change["before"]["price"]
        )
        for source in sorted(by_source):
            self.stdout.write(
                f"{source}: изменится {by_source[source]} товаров, из них цена — {price_changes[source]}"
            )
        self.stdout.write(f"Проверено товаров: {len(rows)}; изменится: {len(changes)}")
        for change in changes[:EXAMPLES]:
            before, after = change["before"], change["after"]
            diff = ", ".join(
                f"{field} {before[field]} → {after[field]}"
                for field in FIELDS
                if field in after and before[field] != after[field]
            )
            self.stdout.write(f"  #{change['product_id']} {change['source']}: {diff}")
        if not options["apply"]:
            self.stdout.write("Показ: ничего не изменено. Для записи: --apply --backup <файл>.")
            return

        with open(options["backup"], "w", encoding="utf-8") as fh:
            json.dump(
                [
                    {
                        "product_id": change["product_id"],
                        "domain": change["domain"],
                        "domain_id": change["domain_id"],
                        "before": {
                            key: value if value is None or isinstance(value, bool) else str(value)
                            for key, value in change["before"].items()
                        },
                    }
                    for change in changes
                ],
                fh,
                ensure_ascii=False,
            )
        for start in range(0, len(changes), batch_size):
            self._apply(changes[start:start + batch_size])
        self.stdout.write(self.style.SUCCESS(f"Пересчитано: {len(changes)}. Бэкап: {options['backup']}"))

    @staticmethod
    def _batch_changes(rows):
        sources = {pk: source for pk, source, _type in rows}
        current = {row["pk"]: row for row in Product.objects.filter(pk__in=list(sources)).values("pk", *FIELDS)}
        changes = []
        for product_type, model in DOMAIN_MODELS.items():
            ids = [pk for pk, _source, row_type in rows if row_type == product_type]
            if not ids:
                continue
            variant_model = model._meta.get_field("variants").related_model
            domains = model.objects.filter(base_product_id__in=ids).only(
                "pk", "base_product_id", *FIELDS
            ).prefetch_related(
                Prefetch(
                    "variants",
                    queryset=variant_model.objects.filter(is_active=True).order_by("sort_order", "id"),
                    to_attr="active_colours",
                )
            )
            for domain in domains:
                if not domain.active_colours:
                    continue
                before = current.get(domain.base_product_id)
                if before is None:
                    continue
                before = {field: before[field] for field in FIELDS}
                source = sources[domain.base_product_id]
                after = target_values(source, before, domain.active_colours)
                domain_before = {field: getattr(domain, field) for field in FIELDS}
                if all(before[f] == value and domain_before[f] == value for f, value in after.items()):
                    continue
                changes.append(
                    {
                        "product_id": domain.base_product_id,
                        "source": source,
                        "domain": model._meta.label,
                        "domain_id": domain.pk,
                        "before": before,
                        "after": after,
                    }
                )
        return changes

    @staticmethod
    def _apply(changes):
        now = timezone.now()
        models = {model._meta.label: model for model in DOMAIN_MODELS.values()}
        with transaction.atomic():
            for change in changes:
                # update(), а не save(): сигналы Product (контент, медиа, AI) здесь не нужны.
                Product.objects.filter(pk=change["product_id"]).update(**change["after"], updated_at=now)
                models[change["domain"]].objects.filter(pk=change["domain_id"]).update(**change["after"])
