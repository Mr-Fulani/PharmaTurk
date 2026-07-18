"""Аудит и backfill локализованных характеристик существующей мебели."""

from django.core.management.base import BaseCommand

from apps.catalog.models import FurnitureProduct
from apps.ai.services.semantic_validator import SemanticValidator
from apps.catalog.services.furniture_attributes import (
    build_furniture_dynamic_attributes,
    sync_furniture_dynamic_attributes,
)


class Command(BaseCommand):
    help = "Показывает план или создаёт локализованные dynamic attributes мебели"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Применить изменения; без флага только dry-run")
        parser.add_argument("--overwrite", action="store_true", help="Перезаписать существующие значения нормализованными")
        parser.add_argument("--limit", type=int, default=0, help="Ограничить число проверяемых товаров")

    def handle(self, *args, **options):
        queryset = FurnitureProduct.objects.select_related("category").order_by("pk")
        if options["limit"] > 0:
            queryset = queryset[: options["limit"]]
        scanned = candidates = changed = title_mismatches = 0
        for product in queryset:
            scanned += 1
            external_data = product.external_data if isinstance(product.external_data, dict) else {}
            source_attrs = external_data.get("attributes") if isinstance(external_data.get("attributes"), dict) else {}
            raw = {
                "furniture_type": source_attrs.get("furniture_type") or product.furniture_type,
                "material": source_attrs.get("material") or product.material,
                "dimensions": source_attrs.get("dimensions") or product.dimensions,
            }
            rows = build_furniture_dynamic_attributes(raw)
            candidates += len(rows)
            if options["apply"]:
                changed += sync_furniture_dynamic_attributes(
                    product,
                    raw,
                    overwrite=options["overwrite"],
                )
            semantic_report = SemanticValidator().validate(
                product.base_product,
                generated_titles={"ru": product.name},
                dynamic_attributes=[],
            )
            if "title" in semantic_report.rejected_fields:
                title_mismatches += 1
                self.stdout.write(
                    f"TITLE_MISMATCH product={product.pk} category={product.category.slug} name={product.name}"
                )

        mode = "APPLY" if options["apply"] else "DRY-RUN"
        self.stdout.write(
            f"{mode}: scanned={scanned} candidates={candidates} changed={changed} "
            f"title_mismatches={title_mismatches}"
        )
