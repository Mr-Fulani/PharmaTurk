"""Снять с выдачи доменные записи прежнего типа товара (dry-run по умолчанию).

У товара должна быть одна доменная запись — текущего product_type. До 2026-10-21
смена типа в админке создавала запись нового типа, а прежняя оставалась
активной: товар отдавался и в выдаче старого типа, а фото вариантов одежды в
новую запись не попадали (косметичка Massimo Dutti, Product 26178:
ClothingProduct 1027 с 5 фото в варианте, AccessoryProduct 450 без галереи).

Команда переносит картинки (и варианты, если новый тип их поддерживает) в
запись текущего типа и снимает прежнюю с публикации через update(): базовый
Product не меняется, файлы в хранилище не удаляются — ссылки на них остаются.

    manage.py retire_stale_domain_records                    # отчёт по всем товарам
    manage.py retire_stale_domain_records --product 26178    # отчёт по товару
    manage.py retire_stale_domain_records --product 26178 --apply --backup /backups/stale-26178.json

Откат по бэкапу: вернуть is_active прежних записей и удалить у записи текущего
типа строки галереи и варианты, которых нет в списках «до» (файлы при этом не
удалятся: на них ссылается прежняя запись).
"""
import json
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.domain_sync import (
    _GALLERY_RELATIONS,
    _VARIANT_RELATIONS,
    _child_relation,
    domain_models,
    retire_stale_domain_records,
)
from apps.catalog.models import Product


def _products_with_several_domain_records(product_ids):
    owners = defaultdict(list)
    for model in domain_models().values():
        rows = model.objects.filter(base_product__isnull=False)
        if product_ids:
            rows = rows.filter(base_product_id__in=product_ids)
        for pk, base_id, is_active in rows.values_list("pk", "base_product_id", "is_active"):
            owners[base_id].append((model, pk, is_active))
    return {base_id: rows for base_id, rows in owners.items() if len(rows) > 1}


def _child_pks(record, names):
    relation = _child_relation(type(record), names)
    return list(getattr(record, relation[0]).values_list("pk", flat=True)) if relation else []


class Command(BaseCommand):
    help = "Переносит медиа доменных записей прежнего типа в запись текущего и снимает их с выдачи."

    def add_arguments(self, parser):
        parser.add_argument("--product", type=int, action="append", default=[], help="pk Product (можно несколько раз).")
        parser.add_argument("--apply", action="store_true", help="Изменить данные (иначе только отчёт).")
        parser.add_argument("--backup", default="", help="JSON-файл бэкапа (обязателен с --apply).")
        parser.add_argument("--limit", type=int, default=50, help="Сколько товаров показать в отчёте.")

    def handle(self, *args, **options):
        owners = _products_with_several_domain_records(options["product"])
        products = Product.objects.in_bulk(list(owners))
        models = domain_models()
        pairs = Counter()
        visible_twice = 0
        for base_id, rows in owners.items():
            product = products[base_id]
            pairs[" + ".join(sorted(model.__name__ for model, _pk, _active in rows))] += 1
            if any(active and model._domain_product_type != product.product_type for model, _pk, active in rows):
                visible_twice += 1

        self.stdout.write(
            f"Товаров с несколькими доменными записями: {len(owners)}; "
            f"из них запись прежнего типа активна (товар виден в чужой выдаче): {visible_twice}"
        )
        for pair, count in pairs.most_common():
            self.stdout.write(f"  {pair}: {count}")

        plans = []
        for base_id in sorted(owners)[: max(options["limit"], 0) or None]:
            product = products[base_id]
            plan = retire_stale_domain_records(product, dry_run=True)
            plans.append((product, plan))
            current = models.get(product.product_type)
            self.stdout.write(
                f"Product {product.pk} «{product.name}» тип {product.product_type}: "
                + ("; ".join(
                    f"{row['model']} {row['pk']} (активна: {'да' if row['was_active'] else 'нет'}) → "
                    f"{row['target']}: фото {row['gallery']}, вариантов {row['variants']}"
                    for row in plan
                ) or f"нет записи текущего типа ({current.__name__ if current else '—'}), пропуск")
            )

        if not options["apply"]:
            self.stdout.write("Dry-run: ничего не изменено. Для записи: --apply --backup <файл>.")
            return
        if not options["backup"]:
            raise CommandError("С --apply нужен --backup <файл>.")
        if len(plans) < len(owners):
            raise CommandError("С --apply укажите товары через --product или поднимите --limit до всех товаров.")

        backup = []
        for product, plan in plans:
            if not plan:
                continue
            current = models[product.product_type].objects.get(base_product_id=product.pk)
            backup.append({
                "product": product.pk,
                "product_type": product.product_type,
                "current": {
                    "model": type(current).__name__,
                    "pk": current.pk,
                    "gallery_pks_before": _child_pks(current, _GALLERY_RELATIONS),
                    "variant_pks_before": _child_pks(current, _VARIANT_RELATIONS),
                },
                "stale": [{"model": row["model"], "pk": row["pk"], "is_active": row["was_active"]} for row in plan],
            })
        with open(options["backup"], "w", encoding="utf-8") as fh:
            json.dump(backup, fh, ensure_ascii=False, indent=1)

        done = Counter()
        for product, plan in plans:
            if not plan:
                continue
            for row in retire_stale_domain_records(product):
                done["records"] += 1
                done["gallery"] += row["gallery"]
                done["variants"] += row["variants"]
        self.stdout.write(self.style.SUCCESS(
            f"Снято с выдачи записей: {done['records']}; перенесено фото: {done['gallery']}, "
            f"вариантов: {done['variants']}. Бэкап: {options['backup']}"
        ))
