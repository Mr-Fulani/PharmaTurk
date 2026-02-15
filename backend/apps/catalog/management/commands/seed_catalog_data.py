"""
Создаёт категории, подкатегории и бренды с правильной иерархией и переводами ru/en.
Используется для восстановления каталога после потери БД.

Использование:
    python manage.py seed_catalog_data
    python manage.py seed_catalog_data --categories-only
    python manage.py seed_catalog_data --brands-only
    python manage.py seed_catalog_data --fix-hierarchy
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.db import transaction
from django.db.utils import IntegrityError

from apps.catalog.constants import ROOT_CATEGORIES, SUB_CATEGORIES, BRANDS_DATA
from apps.catalog.models import Category, CategoryType, CategoryTranslation, Brand, BrandTranslation


# Маппинг slug подкатегории из миграции 0024 -> slug корневой категории
SUBCAT_TO_ROOT = {
    "antibiotics": "medicines",
    "painkillers": "medicines",
    "cardio": "medicines",
    "dermatology": "medicines",
    "cold-flu": "medicines",
    "gastro": "medicines",
    "endocrinology-diabetes": "medicines",
    "ophthalmology": "medicines",
    "ent": "medicines",
    "orthopedics": "medicines",
    "vitamins": "supplements",
    "minerals": "supplements",
    "omega-fish-oil": "supplements",
    "protein-amino": "supplements",
    "collagen": "supplements",
    "probiotics": "supplements",
    "immunity": "supplements",
    "kids-supplements": "supplements",
    "measuring-devices": "medical-equipment",
    "care-devices": "medical-equipment",
    "rehab-orthoses": "medical-equipment",
    "consumables": "medical-equipment",
    "dentistry-tools": "medical-equipment",
    "dentistry-consumables": "medical-equipment",
    "kitchen-cookware": "tableware",
    "serving": "tableware",
    "storage": "tableware",
    "copper": "tableware",
    "porcelain": "tableware",
    "glass-ceramic": "tableware",
    "living-room": "furniture",
    "bedroom": "furniture",
    "office": "furniture",
    "kitchen-dining": "furniture",
    "rings": "jewelry",
    "chains": "jewelry",
    "bracelets": "jewelry",
    "earrings": "jewelry",
    "pendants": "jewelry",
    "wedding": "jewelry",
    "women": "jewelry",
    "men": "jewelry",
}


class Command(BaseCommand):
    help = "Создаёт категории, подкатегории и бренды с иерархией и переводами ru/en"

    def add_arguments(self, parser):
        parser.add_argument(
            "--categories-only",
            action="store_true",
            help="Создать только категории и подкатегории",
        )
        parser.add_argument(
            "--brands-only",
            action="store_true",
            help="Создать только бренды",
        )
        parser.add_argument(
            "--fix-hierarchy",
            action="store_true",
            help="Только исправить parent у существующих подкатегорий",
        )

    def handle(self, *args, **options):
        if options["fix_hierarchy"]:
            self._fix_hierarchy()
            return

        with transaction.atomic():
            if not options["brands_only"]:
                self._seed_category_types()
                self._seed_root_categories()
                self._seed_subcategories()
                self._fix_hierarchy()

            if not options["categories_only"]:
                self._seed_brands()

        self.stdout.write(self.style.SUCCESS("Готово."))

    def _seed_category_types(self):
        self.stdout.write("Создание типов категорий...")
        for i, (slug, name_ru, name_en, _, _, _) in enumerate(ROOT_CATEGORIES):
            ct = CategoryType.objects.filter(slug=slug).first()
            if ct:
                continue
            ct = CategoryType.objects.filter(name=name_ru).first()
            if ct:
                old_slug = ct.slug
                ct.slug = slug
                ct.sort_order = i
                ct.save()
                self.stdout.write(f"  ↻ CategoryType обновлён: {slug} (был slug={old_slug})")
                continue
            try:
                ct = CategoryType.objects.create(
                    slug=slug,
                    name=name_ru,
                    is_active=True,
                    sort_order=i,
                )
                self.stdout.write(f"  ✓ CategoryType: {slug}")
            except IntegrityError:
                ct = CategoryType.objects.filter(name=name_ru).first()
                if ct:
                    ct.slug = slug
                    ct.sort_order = i
                    ct.save(update_fields=["slug", "sort_order"])
                    self.stdout.write(f"  ↻ CategoryType исправлен: {slug}")

    def _seed_root_categories(self):
        self.stdout.write("Создание корневых категорий...")
        for i, (slug, name_ru, name_en, desc_ru, desc_en, type_slug) in enumerate(ROOT_CATEGORIES):
            cat_type = CategoryType.objects.filter(slug=type_slug).first()
            cat, created = Category.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name_ru,
                    "description": desc_ru or name_ru,
                    "category_type": cat_type,
                    "parent": None,
                    "is_active": True,
                    "sort_order": i,
                },
            )
            if created:
                self.stdout.write(f"  ✓ Корневая: {slug}")
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)

    def _seed_subcategories(self):
        self.stdout.write("Создание подкатегорий...")
        for parent_slug, items in SUB_CATEGORIES.items():
            parent = Category.objects.filter(slug=parent_slug, parent__isnull=True).first()
            if not parent:
                self.stdout.write(self.style.WARNING(f"  Родитель не найден: {parent_slug}, пропуск"))
                continue
            for sort, (name_ru, name_en, sub_slug, desc_ru, desc_en) in enumerate(items):
                cat, created = Category.objects.get_or_create(
                    slug=sub_slug,
                    defaults={
                        "name": name_ru,
                        "description": desc_ru or name_ru,
                        "category_type": parent.category_type,
                        "parent": parent,
                        "is_active": True,
                        "sort_order": sort,
                    },
                )
                if created:
                    self.stdout.write(f"  ✓ Подкатегория: {sub_slug} -> {parent_slug}")
                elif not cat.parent_id:
                    cat.parent = parent
                    cat.save()
                    self.stdout.write(f"  ↻ Исправлен parent: {sub_slug} -> {parent_slug}")
                _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)

    def _fix_hierarchy(self):
        self.stdout.write("Исправление иерархии подкатегорий...")
        updated = 0
        for sub_slug, root_slug in SUBCAT_TO_ROOT.items():
            root = Category.objects.filter(slug=root_slug, parent__isnull=True).first()
            if not root:
                continue
            cat = Category.objects.filter(slug=sub_slug).first()
            if cat and (not cat.parent_id or cat.parent_id != root.id):
                cat.parent = root
                cat.save()
                updated += 1
                self.stdout.write(f"  ↻ {sub_slug} -> {root_slug}")
        self.stdout.write(f"Исправлено: {updated}")

    def _seed_brands(self):
        self.stdout.write("Создание брендов...")
        seen_slugs = set()
        for primary_slug, items in BRANDS_DATA.items():
            for name, desc_ru, desc_en, website in items:
                slug = slugify(name)
                if not slug or slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                brand, created = Brand.objects.update_or_create(
                    slug=slug,
                    defaults={
                        "name": name,
                        "description": desc_ru,
                        "website": website or "",
                        "is_active": True,
                        "primary_category_slug": primary_slug,
                    },
                )
                if created:
                    self.stdout.write(f"  ✓ Бренд: {name} ({primary_slug})")
                _ensure_brand_translations(brand, name, desc_ru, desc_en)


def _ensure_category_translations(category, name_ru: str, name_en: str, desc_ru: str, desc_en: str):
    for locale, name, desc in [("ru", name_ru, desc_ru), ("en", name_en, desc_en)]:
        CategoryTranslation.objects.update_or_create(
            category=category,
            locale=locale,
            defaults={"name": name, "description": desc or ""},
        )


def _ensure_brand_translations(brand, name: str, desc_ru: str, desc_en: str):
    for locale, desc in [("ru", desc_ru), ("en", desc_en)]:
        BrandTranslation.objects.update_or_create(
            brand=brand,
            locale=locale,
            defaults={"name": name, "description": desc or ""},
        )
