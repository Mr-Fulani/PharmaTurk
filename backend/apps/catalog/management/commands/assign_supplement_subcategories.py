"""БАДы из корня «БАДы» — по разделам, из разделов — по подкатегориям-веществам
(dry-run по умолчанию).

Правило — ``apps.catalog.supplement_taxonomy``: раздел по турецкому названию, иначе по
RU-названию карточки; внутри раздела подкатегория 3-го уровня («Магний», «Витамин D»),
если в названии ровно одно вещество раздела. Нераспознанные товары остаются, где были.
Подкатегории из ``RETIRED_SUBCATEGORY_SLUGS`` без товаров выключаются (решение владельца
27.10.2026). Цена не меняется: подкатегория без своей наценки наследует наценку корня,
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
from apps.catalog.supplement_taxonomy import (
    RETIRED_SUBCATEGORY_SLUGS,
    ROOT_SLUG,
    SUBCATEGORY_SLUGS,
    SUBSTANCE_RULES,
    supplement_category_slug,
    supplement_category_slug_ru,
    supplement_substance_slug,
)
from apps.catalog.utils.product_markup import get_category_markup

EXAMPLES = 5


class Command(BaseCommand):
    help = "Распределяет БАДы по разделам и подкатегориям по названию (по умолчанию dry-run)."

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
        targets = {
            category.slug: category
            for category in Category.objects.filter(slug__in=SUBCATEGORY_SLUGS, parent=root, is_active=True)
        }
        missing = sorted(set(SUBCATEGORY_SLUGS) - set(targets))
        if missing:
            raise CommandError(f"Нет активных подкатегорий «БАДов»: {', '.join(missing)}.")
        substances = {
            slug: parent for parent, rules in SUBSTANCE_RULES.items() for slug, _ in rules if slug
        }
        for category in Category.objects.filter(
            slug__in=substances, parent__in=targets.values(), is_active=True,
        ).select_related("parent"):
            if category.parent.slug == substances[category.slug]:
                targets[category.slug] = category
        missing = sorted(set(substances) - set(targets))
        if missing:
            raise CommandError(f"Нет активных подкатегорий 3-го уровня: {', '.join(missing)}.")
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
        sections = {category.pk: slug for slug, category in targets.items() if slug in SUBCATEGORY_SLUGS}
        rows = []  # (product_id, domain_id, old_category_id, slug | None, source_name)
        in_root = in_sections = 0
        queryset = (
            Product.objects.filter(product_type="supplements", category_id__in=[root.pk, *sections])
            .select_related("brand")
            .order_by("pk")
        )
        for product in queryset.iterator(chunk_size=1000):
            source_name = supplement_source_name(product)
            brand = product.brand.name if product.brand_id else ""
            if product.category_id == root.pk:
                in_root += 1
                # Турецкое название ничего не говорит — по RU-названию карточки (supplement_category_slug_ru).
                section = supplement_category_slug(source_name, brand) or supplement_category_slug_ru(
                    product.name, brand
                )
            else:
                in_sections += 1
                section = sections[product.category_id]
            slug = section and (supplement_substance_slug(section, source_name, product.name, brand) or section)
            if slug and targets[slug].pk == product.category_id:
                continue
            rows.append((product.pk, domain_ids.get(product.pk), product.category_id, slug, source_name))

        with open(report_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["product_id", "domain_id", "old_category_id", "new_category_slug", "source_name"])
            for product_id, domain_id, old_category_id, slug, source_name in rows:
                writer.writerow([product_id, domain_id or "", old_category_id, slug or "", source_name])

        by_slug = defaultdict(list)
        for row in rows:
            by_slug[row[3]].append(row[4])
        unresolved = by_slug.get(None, [])
        moved = len(rows) - len(unresolved)
        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(
            f"{mode}: в корне «{root.name}» {in_root}, в разделах {in_sections}; переносится {moved}, "
            f"остаются в корне {len(unresolved)}; наценка корня {root_markup}% наследуется"
        )
        for slug, names in sorted(by_slug.items(), key=lambda item: (item[0] is None, -len(item[1]))):
            title = f"{slug} ({targets[slug].name})" if slug else "не распознано"
            self.stdout.write(f"  {title}: {len(names)}")
            for name in names[:EXAMPLES]:
                self.stdout.write(f"      {name}")
        baby = sum(1 for name in unresolved if is_baby_food(name))
        no_domain = sum(1 for row in rows if row[3] and row[1] is None)
        self.stdout.write(f"  из нераспознанных — детское питание (смеси, прикорм): {baby}")
        if no_domain:
            self.stdout.write(f"  без доменной записи (меняется только Product): {no_domain}")

        retired = list(Category.objects.filter(
            slug__in=RETIRED_SUBCATEGORY_SLUGS, parent__parent=root, is_active=True,
        ).order_by("slug"))
        busy = {
            category.slug for category in retired
            if Product.objects.filter(category=category).exists()
            or SupplementProduct.objects.filter(category=category).exists()
            or Category.objects.filter(parent=category).exists()
        }
        idle = [category for category in retired if category.slug not in busy]
        if idle:
            self.stdout.write(f"  выключаются пустые подкатегории: {', '.join(c.slug for c in idle)}")
        if busy:
            self.stdout.write(self.style.WARNING(
                f"  не выключены — в них есть товары или дочерние категории: {', '.join(sorted(busy))}"
            ))
        self.stdout.write(f"CSV: {report_path}")

        if not apply:
            self.stdout.write("Данные не изменены. Для применения добавьте --apply.")
            return

        grouped = defaultdict(lambda: ([], []))
        for product_id, domain_id, old_category_id, slug, _ in rows:
            if slug:
                grouped[(old_category_id, slug)][0].append(product_id)
                if domain_id:
                    grouped[(old_category_id, slug)][1].append(domain_id)
        updated = Counter()
        with transaction.atomic():
            for (old_category_id, slug), (product_ids, domain_ids_) in grouped.items():
                category = targets[slug]
                updated["product"] += Product.objects.filter(
                    pk__in=product_ids, category_id=old_category_id,
                ).update(category=category)
                updated["domain"] += SupplementProduct.objects.filter(
                    pk__in=domain_ids_, category_id=old_category_id,
                ).update(category=category)
            updated["retired"] = Category.objects.filter(pk__in=[c.pk for c in idle]).update(is_active=False)
        self.stdout.write(self.style.SUCCESS(
            f"Перенесено: Product {updated['product']}, SupplementProduct {updated['domain']}; "
            f"выключено подкатегорий {updated['retired']}. "
            f"Откат — по CSV {report_path} (old_category_id)."
        ))
