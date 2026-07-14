from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Category, ShoeProduct
from apps.scrapers.parsers.flo import resolve_flo_shoe_category_slug


class Command(BaseCommand):
    help = "Распределяет импортированную из FLO обувь из корня shoes по подкатегориям."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Применить изменения")

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        targets = {
            category.slug: category
            for category in Category.objects.filter(
                slug__in=("sandals", "sneakers", "home-shoes", "boots", "dress-shoes"),
                is_active=True,
            )
        }
        queryset = (
            ShoeProduct.objects.filter(
                category__slug="shoes",
                external_url__icontains="flo.com.tr",
            )
            .select_related("base_product")
            .order_by("pk")
        )

        proposed = []
        unresolved = 0
        for product in queryset.iterator(chunk_size=500):
            slug = resolve_flo_shoe_category_slug(product.name, product.external_url)
            category = targets.get(slug)
            if category is None:
                unresolved += 1
                continue
            proposed.append((product, category))

        counts = {}
        for _, category in proposed:
            counts[category.slug] = counts.get(category.slug, 0) + 1

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(
            f"{mode}: в корне FLO={queryset.count()}, предложено={len(proposed)}, "
            f"не определено={unresolved}"
        )
        for slug, count in sorted(counts.items()):
            self.stdout.write(f"  {slug}: {count}")

        if not apply_changes:
            self.stdout.write("Данные не изменены. Для применения добавьте --apply.")
            return

        with transaction.atomic():
            for product, category in proposed:
                ShoeProduct.objects.filter(pk=product.pk).update(category=category)
                if product.base_product_id:
                    product.base_product.__class__.objects.filter(
                        pk=product.base_product_id
                    ).update(category=category)
        self.stdout.write(self.style.SUCCESS(f"Изменено товаров: {len(proposed)}"))
