from django.core.management.base import BaseCommand

from apps.catalog.constants import ECOMMERCE_ATTRIBUTES
from apps.catalog.models import Category, GlobalAttributeKey


class Command(BaseCommand):
    help = "Аудит и синхронизация category-привязок для GlobalAttributeKey."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Синхронизировать category-привязки по ECOMMERCE_ATTRIBUTES.",
        )
        parser.add_argument(
            "--only-unbound",
            action="store_true",
            help="Показывать только ключи без category-привязок.",
        )

    def handle(self, *args, **options):
        attribute_map = {
            self._canonical_slug(slug): {
                "source_slug": slug,
                "name_ru": name_ru,
                "name_en": name_en,
                "sort_order": sort_order,
                "category_slugs": category_slugs,
            }
            for slug, name_ru, name_en, sort_order, category_slugs in ECOMMERCE_ATTRIBUTES
        }

        if options["sync"]:
            self._sync_attribute_categories(attribute_map)

        self._report(attribute_map, only_unbound=options["only_unbound"])

    def _canonical_slug(self, slug: str) -> str:
        return str(slug or "").strip().lower().replace("_", "-")

    def _sync_attribute_categories(self, attribute_map):
        self.stdout.write(self.style.NOTICE("Синхронизация category-привязок для GlobalAttributeKey..."))
        updated = 0
        for key in GlobalAttributeKey.objects.prefetch_related("categories").all():
            canonical = self._canonical_slug(key.slug)
            payload = attribute_map.get(canonical)
            if not payload:
                continue
            categories = list(
                Category.objects.filter(slug__in=payload["category_slugs"]).values_list("id", flat=True)
            )
            existing = set(key.categories.values_list("id", flat=True))
            missing = [cid for cid in categories if cid not in existing]
            if missing:
                key.categories.add(*missing)
                updated += 1
                self.stdout.write(
                    f"  + {key.slug}: добавлено категорий {len(missing)}"
                    + (f" (alias of {payload['source_slug']})" if key.slug != payload["source_slug"] else "")
                )
        self.stdout.write(self.style.SUCCESS(f"Синхронизация завершена. Обновлено ключей: {updated}"))

    def _report(self, attribute_map, *, only_unbound: bool):
        total = GlobalAttributeKey.objects.count()
        unbound = []
        mismatched = []

        for key in GlobalAttributeKey.objects.prefetch_related("categories").order_by("slug"):
            category_slugs = sorted(key.categories.values_list("slug", flat=True))
            if not category_slugs:
                unbound.append(key.slug)
                continue

            expected = sorted(attribute_map.get(self._canonical_slug(key.slug), {}).get("category_slugs", []))
            if expected and sorted(set(category_slugs)) != sorted(set(expected)):
                mismatched.append((key.slug, category_slugs, expected))

        self.stdout.write(self.style.NOTICE(f"Всего dynamic attribute keys: {total}"))
        self.stdout.write(self.style.NOTICE(f"Без category-привязок: {len(unbound)}"))

        if unbound:
            self.stdout.write(self.style.WARNING("Ключи без привязок:"))
            for slug in unbound:
                self.stdout.write(f"  - {slug}")

        if not only_unbound and mismatched:
            self.stdout.write(self.style.WARNING("Ключи с расхождением между БД и ECOMMERCE_ATTRIBUTES:"))
            for slug, actual, expected in mismatched[:50]:
                self.stdout.write(f"  - {slug}: actual={actual} expected={expected}")

        if not unbound and (only_unbound or not mismatched):
            self.stdout.write(self.style.SUCCESS("Проблемных category-привязок не найдено."))
