"""БАДы из корня «БАДы» — по подкатегориям по турецкому названию (dry-run по умолчанию).

Правило — ``apps.catalog.supplement_taxonomy``; нераспознанные товары остаются в
корне. Цена не меняется: подкатегория без своей наценки наследует наценку корня,
команда это проверяет и без совпадения ничего не пишет. Пишутся доменная запись
и базовый ``Product`` (``QuerySet.update``: slug не меняется, сигналы не нужны).

    manage.py assign_supplement_subcategories            # отчёт + CSV, без записи
    manage.py assign_supplement_subcategories --apply    # CSV (старая категория) и запись
"""
import csv
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.ai.services.supplement_content import is_baby_food, supplement_source_name
from apps.catalog.models import Category, Product, SupplementProduct
from apps.catalog.supplement_taxonomy import ROOT_SLUG, SUBCATEGORY_SLUGS, supplement_category_slug
from apps.catalog.utils.product_markup import get_category_markup

EXAMPLES = 5


class Command(BaseCommand):
    help = "Распределяет БАДы из корня «БАДы» по подкатегориям по названию (по умолчанию dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Перенести товары в подкатегории.")
        parser.add_argument("--report", default="", help="Путь CSV-отчёта (по умолчанию /tmp/...).")

    def handle(self, *args, **options):
        apply = options["apply"]
        report_path = options["report"] or (
            f"/tmp/supplement_subcategories_{timezone.now():%Y%m%d_%H%M%S}.csv"
        )
        root = Category.objects.filter(slug=ROOT_SLUG, parent__isnull=True).first()
        if root is None:
            raise CommandError(f"Корневая категория «{ROOT_SLUG}» не найдена.")
        slugs = SUBCATEGORY_SLUGS
        targets = {
            category.slug: category
            for category in Category.objects.filter(slug__in=slugs, parent=root, is_active=True)
        }
        missing = sorted(set(slugs) - set(targets))
        if missing:
            raise CommandError(f"Нет активных подкатегорий «БАДов»: {', '.join(missing)}.")
        root_markup = get_category_markup(root)
        changed_markup = [
            slug for slug, category in targets.items() if get_category_markup(category) != root_markup
        ]
        if changed_markup:
            raise CommandError(
                f"Наценка подкатегорий отличается от корня ({root_markup}): {', '.join(changed_markup)} — "
                "перенос изменил бы цены."
            )

        domain_ids = dict(
            SupplementProduct.objects.filter(base_product__isnull=False).values_list("base_product_id", "pk")
        )
        rows = []  # (product_id, domain_id, slug | None, source_name)
        queryset = (
            Product.objects.filter(product_type="supplements", category=root)
            .select_related("brand")
            .order_by("pk")
        )
        for product in queryset.iterator(chunk_size=1000):
            source_name = supplement_source_name(product)
            brand = product.brand.name if product.brand_id else ""
            slug = supplement_category_slug(source_name, brand)
            rows.append((product.pk, domain_ids.get(product.pk), slug, source_name))

        with open(report_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["product_id", "domain_id", "old_category_id", "new_category_slug", "source_name"])
            for product_id, domain_id, slug, source_name in rows:
                writer.writerow([product_id, domain_id or "", root.pk, slug or "", source_name])

        by_slug = defaultdict(list)
        for row in rows:
            by_slug[row[2]].append(row[3])
        moved = len(rows) - len(by_slug.get(None, []))
        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(
            f"{mode}: в корне «{root.name}» {len(rows)}, в подкатегории {moved}, "
            f"остаются в корне {len(rows) - moved}; наценка корня {root_markup}% наследуется"
        )
        for slug, names in sorted(by_slug.items(), key=lambda item: (item[0] is None, -len(item[1]))):
            title = f"{slug} ({targets[slug].name})" if slug else "не распознано"
            self.stdout.write(f"  {title}: {len(names)}")
            for name in names[:EXAMPLES]:
                self.stdout.write(f"      {name}")
        unresolved = by_slug.get(None, [])
        baby = sum(1 for name in unresolved if is_baby_food(name))
        no_domain = sum(1 for row in rows if row[2] and row[1] is None)
        self.stdout.write(f"  из нераспознанных — детское питание (смеси, прикорм): {baby}")
        if no_domain:
            self.stdout.write(f"  без доменной записи (меняется только Product): {no_domain}")
        self.stdout.write(f"CSV: {report_path}")

        if not apply:
            self.stdout.write("Данные не изменены. Для применения добавьте --apply.")
            return

        grouped = defaultdict(lambda: ([], []))
        for product_id, domain_id, slug, _ in rows:
            if slug:
                grouped[slug][0].append(product_id)
                if domain_id:
                    grouped[slug][1].append(domain_id)
        updated = Counter()
        with transaction.atomic():
            for slug, (product_ids, domain_ids_) in grouped.items():
                category = targets[slug]
                updated["product"] += Product.objects.filter(pk__in=product_ids, category=root).update(
                    category=category
                )
                updated["domain"] += SupplementProduct.objects.filter(
                    pk__in=domain_ids_, category=root
                ).update(category=category)
        self.stdout.write(self.style.SUCCESS(
            f"Перенесено: Product {updated['product']}, SupplementProduct {updated['domain']}. "
            f"Откат — по CSV {report_path} (old_category_id)."
        ))
