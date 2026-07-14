"""Аудит и безопасный перенос существующих товаров IKEA по подкатегориям."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.catalog.ikea_category_mapping import (
    LEGACY_FURNITURE_CATEGORY_ALIASES,
    resolve_ikea_product_category,
)
from apps.catalog.models import Category, FurnitureProduct


class Command(BaseCommand):
    help = (
        "Показывает предлагаемые категории IKEA; меняет данные только с явным --apply. "
        "Категории не удаляет и не деактивирует."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Применить только уверенно определённые изменения категорий.",
        )
        parser.add_argument("--limit", type=int, default=0, help="Ограничить число товаров.")
        parser.add_argument(
            "--show-all",
            action="store_true",
            help="Показывать также товары, уже находящиеся в правильной категории.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        limit = max(0, int(options["limit"] or 0))
        show_all = bool(options["show_all"])

        categories = {
            category.slug: category
            for category in Category.objects.filter(category_type__slug="furniture")
        }
        # На старых базах category_type мог быть не заполнен, поэтому добираем
        # все целевые категории по slug из маппинга фактически найденных товаров.
        queryset = (
            FurnitureProduct.objects.filter(
                Q(brand__name__iexact="IKEA")
                | Q(external_data__source__iexact="ikea")
                | Q(external_data__source__iexact="ikea_tr_direct")
            )
            .select_related("category", "brand", "base_product")
            .order_by("id")
        )
        if limit:
            queryset = queryset[:limit]

        products = list(queryset)
        matches = []
        unknown = []
        missing_categories = set()
        unchanged = 0

        for product in products:
            match = resolve_ikea_product_category(product)
            if not match:
                unknown.append(product)
                continue
            target = categories.get(match.category_slug)
            if target is None:
                target = Category.objects.filter(slug=match.category_slug).first()
                if target:
                    categories[target.slug] = target
            if target is None:
                missing_categories.add(match.category_slug)
                continue
            if product.category_id == target.id:
                unchanged += 1
                if show_all:
                    self.stdout.write(
                        f"= #{product.id} {product.name}: {target.name} [{match.reason}]"
                    )
                continue
            matches.append((product, target, match))
            current = product.category.name if product.category_id else "без категории"
            self.stdout.write(
                f"{'APPLY' if apply_changes else 'DRY'} #{product.id} {product.name}: "
                f"{current} -> {target.name} [{match.reason}]"
            )

        if apply_changes and missing_categories:
            raise CommandError(
                "Seed категорий нужно выполнить до переноса. Отсутствуют: "
                + ", ".join(sorted(missing_categories))
            )

        changed = 0
        if apply_changes:
            with transaction.atomic():
                for product, target, _match in matches:
                    product.category = target
                    product.save(update_fields=["category"])
                    changed += 1

        if unknown:
            self.stdout.write(self.style.WARNING("\nНе удалось определить категорию:"))
            for product in unknown[:100]:
                current = product.category.name if product.category_id else "без категории"
                self.stdout.write(f"? #{product.id} {product.name} (сейчас: {current})")
            if len(unknown) > 100:
                self.stdout.write(f"... и ещё {len(unknown) - 100}")

        legacy_rows = []
        for old_slug, new_slug in LEGACY_FURNITURE_CATEGORY_ALIASES.items():
            old_category = Category.objects.filter(slug=old_slug).first()
            if old_category:
                count = FurnitureProduct.objects.filter(category=old_category).count()
                legacy_rows.append((old_slug, new_slug, count))
        if legacy_rows:
            self.stdout.write(self.style.WARNING("\nСтарые/похожие категории для проверки:"))
            for old_slug, new_slug, count in legacy_rows:
                self.stdout.write(f"! {old_slug} -> {new_slug}; товаров: {count}")

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{mode}: IKEA товаров={len(products)}, предложено={len(matches)}, "
                f"изменено={changed}, уже верно={unchanged}, не определено={len(unknown)}, "
                f"нет целевых категорий={len(missing_categories)}"
            )
        )
        if not apply_changes:
            self.stdout.write("Данные не изменены. Для применения после проверки добавьте --apply.")
