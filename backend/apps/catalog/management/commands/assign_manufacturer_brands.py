"""Бренды медикаментов и БАДов из производителя (dry-run по умолчанию).

Собирает производителей (MedicineProduct.manufacturer и
external_data.attributes.manufacturer у БАДов), склеивает варианты написания
одной фирмы, заводит недостающие бренды и проставляет их товарам, у которых
бренда нет или стоит заглушка «Другое». Фарм-бренды-дубли одной фирмы
(«Abbott» и «Abbott Laboratuarları») сливаются в один: товары переносятся,
пустой дубль без логотипа/описания удаляется. Прочие ручные бренды не трогаются.

    manage.py assign_manufacturer_brands                 # отчёт, без записи
    manage.py assign_manufacturer_brands --apply         # создать/слить бренды и проставить
"""
import csv
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import Brand, MedicineProduct, Product, SupplementProduct
from apps.catalog.utils.manufacturer_brands import (
    OTHER_BRAND_SLUG,
    BrandResolver,
    create_manufacturer_brand,
    ensure_brand_category,
    is_pharma_brand,
    manufacturer_display_name,
    manufacturer_key_tokens,
    root_tokens,
    supplement_manufacturer,
)

DOMAIN_MODELS = {"medicines": MedicineProduct, "supplements": SupplementProduct}


def _brand_is_curated(brand) -> bool:
    return bool(
        brand.logo or brand.card_media or brand.card_media_external_url
        or brand.description or brand.website or brand.show_on_homepage
    )


def _brand_in_use(brand) -> bool:
    for rel in brand._meta.related_objects:
        if not rel.one_to_many or rel.related_model.__name__.endswith("Translation"):
            continue
        if rel.related_model._base_manager.filter(**{rel.field.name: brand}).exists():
            return True
    return False


class Command(BaseCommand):
    help = "Бренды медикаментов и БАДов из производителя (по умолчанию dry-run с CSV-отчётом)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Создать/слить бренды и проставить товарам.")
        parser.add_argument("--report", default="", help="Путь CSV-отчёта (по умолчанию /tmp/...).")

    def handle(self, *args, **options):
        apply = options["apply"]
        report_path = options["report"] or (
            f"/tmp/manufacturer_brands_{timezone.now():%Y%m%d_%H%M%S}.csv"
        )
        other_id = Brand.objects.filter(slug=OTHER_BRAND_SLUG).values_list("id", flat=True).first()

        rows = []  # (product_type, pk, base_product_id, brand_id, raw)
        for pk, base_id, brand_id, raw in MedicineProduct.objects.exclude(manufacturer="").values_list(
            "pk", "base_product_id", "brand_id", "manufacturer"
        ).iterator(chunk_size=2000):
            rows.append(("medicines", pk, base_id, brand_id, raw.strip()))
        for pk, base_id, brand_id, external_data in SupplementProduct.objects.values_list(
            "pk", "base_product_id", "brand_id", "external_data"
        ).iterator(chunk_size=2000):
            raw = supplement_manufacturer(external_data)
            if raw:
                rows.append(("supplements", pk, base_id, brand_id, raw))
        if not rows:
            raise CommandError("Производители не найдены — нечего сопоставлять (пустая БД?).")

        brands = list(Brand.objects.all())
        resolver = BrandResolver(brands)
        pharma_brands = [b for b in brands if is_pharma_brand(b)]
        tokens_of = {raw: manufacturer_key_tokens(raw) for *_, raw in rows}
        known = {t for t in tokens_of.values() if t} | {manufacturer_key_tokens(b.name) for b in pharma_brands}

        groups = defaultdict(lambda: {
            "variants": Counter(), "root_names": Counter(), "names": Counter(), "types": Counter(),
            "rows": [],
        })
        for row in rows:
            tokens = tokens_of[row[4]]
            if not tokens:
                continue
            root = root_tokens(tokens, known)
            group = groups[root]
            group["variants"][row[4]] += 1
            group["names"][manufacturer_display_name(row[4])] += 1
            if tokens == root:
                group["root_names"][manufacturer_display_name(row[4])] += 1
            group["types"][row[0]] += 1
            group["rows"].append(row)

        brands_by_root = defaultdict(list)
        for brand in pharma_brands:
            brands_by_root[root_tokens(manufacturer_key_tokens(brand.name), known)].append(brand)

        plan = []
        for root, group in groups.items():
            candidates = sorted(brands_by_root.get(root, []), key=lambda b: b.pk)
            brand = (
                next((b for b in candidates if manufacturer_key_tokens(b.name) == root), None)
                or (candidates[0] if candidates else resolver.exact.get("".join(root)))
            )
            duplicates = [b for b in candidates if brand is not None and b.pk != brand.pk]
            names = group["root_names"] or group["names"]
            # Самое частое написание, при равенстве — короче
            name = brand.name if brand else min(names.items(), key=lambda item: (-item[1], len(item[0])))[0]
            duplicate_ids = {b.pk for b in duplicates}
            assign = defaultdict(list)
            kept = 0
            for product_type, pk, base_id, brand_id, _ in group["rows"]:
                if brand_id is None or brand_id == other_id or brand_id in duplicate_ids:
                    assign[product_type].append((pk, base_id))
                elif brand is None or brand_id != brand.pk:
                    kept += 1
            plan.append((root, name, brand, duplicates, group, assign, kept))
        plan.sort(key=lambda item: -sum(item[4]["types"].values()))

        with open(report_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "key", "brand_name", "existing_brand_id", "medicines", "supplements",
                "to_assign", "kept_other_brand", "merged_brands", "variants",
            ])
            for root, name, brand, duplicates, group, assign, kept in plan:
                writer.writerow([
                    " ".join(root), name, brand.pk if brand else "",
                    group["types"]["medicines"], group["types"]["supplements"],
                    sum(len(v) for v in assign.values()), kept,
                    " | ".join(f"{d.name} (#{d.pk})" for d in duplicates),
                    " | ".join(f"{raw} ({count})" for raw, count in group["variants"].most_common()),
                ])

        merged = sum(1 for p in plan if len(p[4]["variants"]) > 1)
        to_create = sum(1 for p in plan if p[2] is None)
        to_assign = sum(len(v) for p in plan for v in p[5].values())
        to_merge = sum(len(p[3]) for p in plan)
        kept = sum(p[6] for p in plan)
        self.stdout.write(
            f"{'APPLY' if apply else 'DRY-RUN'}: производителей={len(rows)} "
            f"вариантов={len(tokens_of)} брендов={len(plan)} склеек={merged} "
            f"существующих={len(plan) - to_create} новых={to_create} дублей_слить={to_merge} "
            f"проставить={to_assign} оставлено_своих_брендов={kept}"
        )
        self.stdout.write(f"Отчёт: {report_path}")
        if not apply:
            return

        deleted = 0
        with transaction.atomic():
            for root, name, brand, duplicates, group, assign, _ in plan:
                if brand is None:
                    brand = create_manufacturer_brand(name)
                changed = False
                for product_type in group["types"]:
                    changed = ensure_brand_category(brand, product_type) or changed
                if changed:
                    brand.save(update_fields=["category_slugs", "primary_category_slug", "updated_at"])
                placeholder = Q(brand__isnull=True) | Q(brand_id=other_id) | Q(brand_id__in=[d.pk for d in duplicates])
                for product_type, items in assign.items():
                    # .update(): массовая запись без сигналов автоскачивания медиа и
                    # пересинхронизации; теневой Product получает тот же бренд.
                    DOMAIN_MODELS[product_type].objects.filter(pk__in=[pk for pk, _ in items]).update(brand=brand)
                    Product.objects.filter(placeholder, pk__in=[b for _, b in items if b]).update(brand=brand)
                for duplicate in duplicates:
                    for model in DOMAIN_MODELS.values():
                        model.objects.filter(brand=duplicate).update(brand=brand)
                    Product.objects.filter(brand=duplicate, product_type__in=list(DOMAIN_MODELS)).update(brand=brand)
                    if not _brand_is_curated(duplicate) and not _brand_in_use(duplicate):
                        duplicate.delete()
                        deleted += 1

        try:
            from apps.catalog.brand_counts import refresh_brand_product_counts

            refresh_brand_product_counts()
        except Exception as exc:  # счётчики обновит Beat через минуту
            self.stderr.write(f"Счётчики брендов не обновлены: {exc}")
        self.stdout.write(self.style.SUCCESS(
            f"Готово: проставлено {to_assign}, новых брендов {to_create}, удалено дублей {deleted}"
        ))
