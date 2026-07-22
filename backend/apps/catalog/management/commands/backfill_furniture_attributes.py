"""Аудит и backfill локализованных характеристик существующей мебели."""

from itertools import islice

from django.core.management.base import BaseCommand, CommandError

from apps.ai.services.semantic_validator import SemanticValidator
from apps.catalog.models import FurnitureProduct
from apps.catalog.services.furniture_attributes import (
    build_furniture_dynamic_attributes,
    sync_furniture_dynamic_attributes_batch,
)


class Command(BaseCommand):
    help = "Показывает план или создаёт локализованные dynamic attributes мебели"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="Применить изменения; без флага только dry-run"
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Перезаписать существующие значения нормализованными",
        )
        parser.add_argument(
            "--audit-titles",
            action="store_true",
            help="Дополнительно проверить соответствие заголовков категориям",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Число товаров в одной транзакции и строке прогресса (по умолчанию 200)",
        )
        parser.add_argument(
            "--start-pk",
            type=int,
            default=0,
            help="Начать с этого PK включительно; используется для продолжения прерванного запуска",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Ограничить общее число товаров; 0 означает без ограничения",
        )

    def handle(self, *args, **options):
        self._validate_options(options)
        batch_size = options["batch_size"]
        audit_titles = options["audit_titles"]
        validator = SemanticValidator.with_preloaded_categories() if audit_titles else None

        queryset = FurnitureProduct.objects.select_related(
            "category",
            "base_product",
            "base_product__category",
        ).order_by("pk")
        if options["start_pk"] > 0:
            queryset = queryset.filter(pk__gte=options["start_pk"])
        if options["limit"] > 0:
            queryset = queryset[: options["limit"]]

        scanned = candidates = changed = title_mismatches = 0
        last_pk = 0
        iterator = queryset.iterator(chunk_size=batch_size)
        for batch in self._batches(iterator, batch_size):
            sync_items = []
            for product in batch:
                scanned += 1
                last_pk = product.pk
                raw = self._raw_attributes(product)
                rows = build_furniture_dynamic_attributes(raw)
                candidates += len(rows)
                sync_items.append((product, raw))

                if validator is not None:
                    semantic_report = validator.validate(
                        product.base_product,
                        generated_titles={"ru": product.name},
                        dynamic_attributes=[],
                    )
                    if "title" in semantic_report.rejected_fields:
                        title_mismatches += 1
                        category_slug = getattr(product.category, "slug", "unknown")
                        self.stdout.write(
                            f"TITLE_MISMATCH product={product.pk} "
                            f"category={category_slug} name={product.name}"
                        )

            if options["apply"]:
                changed += sync_furniture_dynamic_attributes_batch(
                    sync_items,
                    overwrite=options["overwrite"],
                    write_batch_size=batch_size,
                )

            self.stdout.write(
                f"PROGRESS: last_pk={last_pk} scanned={scanned} "
                f"candidates={candidates} changed={changed} "
                f"title_mismatches={title_mismatches} "
                f"resume_start_pk={last_pk + 1}"
            )

        mode = "APPLY" if options["apply"] else "DRY-RUN"
        self.stdout.write(
            f"{mode}: scanned={scanned} candidates={candidates} changed={changed} "
            f"title_mismatches={title_mismatches} audit_titles={str(audit_titles).lower()} "
            f"last_pk={last_pk}"
        )

    @staticmethod
    def _validate_options(options):
        if options["batch_size"] <= 0:
            raise CommandError("--batch-size должен быть больше 0")
        if options["start_pk"] < 0:
            raise CommandError("--start-pk не может быть отрицательным")
        if options["limit"] < 0:
            raise CommandError("--limit не может быть отрицательным")
        if options["overwrite"] and not options["apply"]:
            raise CommandError("--overwrite разрешён только вместе с --apply")

    @staticmethod
    def _batches(iterator, batch_size):
        while batch := list(islice(iterator, batch_size)):
            yield batch

    @staticmethod
    def _raw_attributes(product):
        external_data = product.external_data if isinstance(product.external_data, dict) else {}
        source_attrs = (
            external_data.get("attributes")
            if isinstance(external_data.get("attributes"), dict)
            else {}
        )
        return {
            "furniture_type": source_attrs.get("furniture_type") or product.furniture_type,
            "material": source_attrs.get("material") or product.material,
            "dimensions": source_attrs.get("dimensions") or product.dimensions,
        }
