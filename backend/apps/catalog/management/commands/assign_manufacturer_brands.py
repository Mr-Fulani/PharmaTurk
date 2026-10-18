"""Бренды медикаментов и БАДов из производителя (dry-run по умолчанию).

Собирает производителей (MedicineProduct.manufacturer и
external_data.attributes.manufacturer у БАДов), склеивает варианты написания
одной фирмы, заводит недостающие бренды и проставляет их товарам, у которых
бренда нет или стоит заглушка «Другое». Ручные бренды не трогаются.

    manage.py assign_manufacturer_brands                 # отчёт, без записи
    manage.py assign_manufacturer_brands --apply         # создать бренды и проставить
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
    build_brand_key_index,
    ensure_brand_category,
    manufacturer_brand_key,
    manufacturer_display_name,
    supplement_manufacturer,
    unique_brand_slug,
)


class Command(BaseCommand):
    help = "Бренды медикаментов и БАДов из производителя (по умолчанию dry-run с CSV-отчётом)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Создать бренды и проставить товарам.")
        parser.add_argument("--report", default="", help="Путь CSV-отчёта (по умолчанию /tmp/...).")

    def handle(self, *args, **options):
        apply = options["apply"]
        report_path = options["report"] or (
            f"/tmp/manufacturer_brands_{timezone.now():%Y%m%d_%H%M%S}.csv"
        )
        other_id = Brand.objects.filter(slug=OTHER_BRAND_SLUG).values_list("id", flat=True).first()

        rows = []  # (product_type, model, pk, base_product_id, brand_id, raw)
        for pk, base_id, brand_id, raw in MedicineProduct.objects.exclude(manufacturer="").values_list(
            "pk", "base_product_id", "brand_id", "manufacturer"
        ).iterator(chunk_size=2000):
            rows.append(("medicines", MedicineProduct, pk, base_id, brand_id, raw.strip()))
        for pk, base_id, brand_id, external_data in SupplementProduct.objects.values_list(
            "pk", "base_product_id", "brand_id", "external_data"
        ).iterator(chunk_size=2000):
            raw = supplement_manufacturer(external_data)
            if raw:
                rows.append(("supplements", SupplementProduct, pk, base_id, brand_id, raw))
        if not rows:
            raise CommandError("Производители не найдены — нечего сопоставлять (пустая БД?).")

        existing = build_brand_key_index(Brand.objects.all())
        clusters = defaultdict(lambda: {
            "variants": Counter(), "names": Counter(), "types": Counter(),
            "assign": defaultdict(list), "kept": 0,
        })
        for product_type, model, pk, base_id, brand_id, raw in rows:
            key = manufacturer_brand_key(raw)
            if not key:
                continue
            cluster = clusters[key]
            cluster["variants"][raw] += 1
            cluster["names"][manufacturer_display_name(raw)] += 1
            cluster["types"][product_type] += 1
            if brand_id is None or brand_id == other_id:
                cluster["assign"][model].append((pk, base_id))
            else:
                cluster["kept"] += 1

        plan = []
        for key, cluster in clusters.items():
            brand = existing.get(key)
            # Самое частое написание, при равенстве — короче
            name = brand.name if brand else min(
                cluster["names"].items(), key=lambda item: (-item[1], len(item[0]))
            )[0]
            plan.append((key, name, brand, cluster))
        plan.sort(key=lambda item: -sum(item[3]["types"].values()))

        with open(report_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "key", "brand_name", "existing_brand_id", "medicines", "supplements",
                "to_assign", "kept_other_brand", "variants",
            ])
            for key, name, brand, cluster in plan:
                writer.writerow([
                    key, name, brand.pk if brand else "",
                    cluster["types"]["medicines"], cluster["types"]["supplements"],
                    sum(len(v) for v in cluster["assign"].values()), cluster["kept"],
                    " | ".join(f"{raw} ({count})" for raw, count in cluster["variants"].most_common()),
                ])

        merged = sum(1 for *_, cluster in plan if len(cluster["variants"]) > 1)
        to_create = sum(1 for _, _, brand, _ in plan if brand is None)
        to_assign = sum(len(v) for *_, cluster in plan for v in cluster["assign"].values())
        kept = sum(cluster["kept"] for *_, cluster in plan)
        self.stdout.write(
            f"{'APPLY' if apply else 'DRY-RUN'}: производителей={len(rows)} "
            f"вариантов={len({r[5] for r in rows})} брендов={len(plan)} склеек={merged} "
            f"существующих={len(plan) - to_create} новых={to_create} "
            f"проставить={to_assign} оставлено_своих_брендов={kept}"
        )
        self.stdout.write(f"Отчёт: {report_path}")
        if not apply:
            return

        with transaction.atomic():
            for key, name, brand, cluster in plan:
                if brand is None:
                    brand = Brand.objects.create(name=name, slug=unique_brand_slug(name), is_active=True)
                changed = False
                for product_type in cluster["types"]:
                    changed = ensure_brand_category(brand, product_type) or changed
                if changed:
                    brand.save(update_fields=["category_slugs", "primary_category_slug", "updated_at"])
                for model, items in cluster["assign"].items():
                    # .update(): массовая запись без сигналов автоскачивания медиа и
                    # пересинхронизации; теневой Product получает тот же бренд.
                    model.objects.filter(pk__in=[pk for pk, _ in items]).update(brand=brand)
                    Product.objects.filter(
                        Q(brand__isnull=True) | Q(brand_id=other_id),
                        pk__in=[b for _, b in items if b],
                    ).update(brand=brand)

        try:
            from apps.catalog.brand_counts import refresh_brand_product_counts

            refresh_brand_product_counts()
        except Exception as exc:  # счётчики обновит Beat через минуту
            self.stderr.write(f"Счётчики брендов не обновлены: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Готово: проставлено {to_assign}, новых брендов {to_create}"))
