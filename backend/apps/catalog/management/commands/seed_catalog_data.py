"""
Создаёт категории, подкатегории, атрибуты и бренды с правильной иерархией и переводами ru/en.
Используется для восстановления каталога после потери БД.

Использование:
    python manage.py seed_catalog_data
    python manage.py seed_catalog_data --categories-only
    python manage.py seed_catalog_data --attributes-only
    python manage.py seed_catalog_data --brands-only
    python manage.py seed_catalog_data --fix-hierarchy
    python manage.py seed_catalog_data --category-seo-only
"""

import re

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.db import transaction
from django.db.utils import IntegrityError

from apps.catalog.constants import (
    ROOT_CATEGORIES,
    SUB_CATEGORIES,
    MEDICAL_EQUIPMENT_SUBCATEGORIES,
    ACCESSORIES_SUBCATEGORIES,
    PERFUMERY_SUBCATEGORIES,
    INCENSE_SUBCATEGORIES,
    HEADWEAR_SUBCATEGORIES,
    UNDERWEAR_SUBCATEGORIES,
    SHOE_SUBCATEGORIES,
    CLOTHING_SUBCATEGORIES,
    JEWELRY_SUBCATEGORIES,
    SUPPLEMENTS_SUBCATEGORIES,
    MEDICINES_SUBCATEGORIES,
    FURNITURE_SUBCATEGORIES,
    AUTO_PARTS_SUBCATEGORIES,
    TABLEWARE_SUBCATEGORIES,
    ELECTRONICS_SUBCATEGORIES,
    SPORTS_SUBCATEGORIES,
    ISLAMIC_CLOTHING_SUBCATEGORIES,
    SERVICES_SUBCATEGORIES,
    ECOMMERCE_ATTRIBUTES,
    BRANDS_DATA,
)
from apps.catalog.models import (
    Category,
    CategoryType,
    CategoryTranslation,
    Brand,
    BrandTranslation,
    GlobalAttributeKey,
    GlobalAttributeKeyTranslation,
)


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
    # Медтехника L2 (под medical-equipment)
    "diagnostic-equipment": "medical-equipment",
    "rehabilitation-equipment": "medical-equipment",
    "orthopedic-products": "medical-equipment",
    "respiratory-equipment": "medical-equipment",
    "physiotherapy-equipment": "medical-equipment",
    "wound-care-consumables": "medical-equipment",
    "ophthalmology-equipment": "medical-equipment",
    "hearing-aids": "medical-equipment",
    "disinfection-hygiene": "medical-equipment",
    # Аксессуары L2 (под accessories)
    "bags-wallets": "accessories",
    "acc-jewelry": "accessories",
    "fashion-jewelry": "accessories",
    "watches": "accessories",
    "belts": "accessories",
    "acc-headwear": "accessories",
    "scarves-shawls": "accessories",
    "acc-gloves": "accessories",
    "eyewear": "accessories",
    "hair-accessories": "accessories",
    "umbrellas": "accessories",
    "ties-pocket-squares": "accessories",
    "acc-phone-accessories": "accessories",
    # Парфюмерия L2 (под perfumery)
    "fragrances": "perfumery",
    "oil-perfumes": "perfumery",
    "scented-products": "perfumery",
    "miniatures-samples": "perfumery",
    "perfumery-gift-sets": "perfumery",
    # Благовония L2 (под incense)
    "scented-candles": "incense",
    "incense-sticks": "incense",
    "incense-cones": "incense",
    "resins-loose-incense": "incense",
    "essential-oils": "incense",
    "aroma-diffusers": "incense",
    "sachets-sprays": "incense",
    "incense-accessories": "incense",
    "cookware": "tableware",
    "kitchen-cookware": "tableware",
    "tableware-serving": "tableware",
    "serving": "tableware",
    "drinkware": "tableware",
    "tea-coffee-ware": "tableware",
    "bakeware": "tableware",
    "food-storage": "tableware",
    "storage": "tableware",
    "kitchen-accessories": "tableware",
    "tableware-sets": "tableware",
    "copper": "tableware",
    "porcelain": "tableware",
    "glass-ceramic": "tableware",
    "living-room": "furniture",
    "bedroom": "furniture",
    "kitchen-dining": "furniture",
    "office": "furniture",
    "kids-furniture": "furniture",
    "storage-furniture": "furniture",
    "outdoor-furniture": "furniture",
    # Автозапчасти L2 (под auto-parts)
    "engine-parts": "auto-parts",
    "brake-system": "auto-parts",
    "suspension": "auto-parts",
    "steering-system": "auto-parts",
    "transmission": "auto-parts",
    "electrical-system": "auto-parts",
    "cooling-system": "auto-parts",
    "body-parts": "auto-parts",
    "lighting": "auto-parts",
    "filters": "auto-parts",
    # Обувь L2 (под shoes)
    "boots": "shoes",
    "dress-shoes": "shoes",
    "casual-shoes": "shoes",
    "sneakers": "shoes",
    "sandals": "shoes",
    "home-shoes": "shoes",
    "women-shoes": "shoes",
    "men-shoes": "shoes",
    "unisex-shoes": "shoes",
    "kids-shoes": "shoes",
    # Одежда L2 (под clothing; sportswear и underwear — отдельные корни)
    "outerwear": "clothing",
    "tops": "clothing",
    "knitwear": "clothing",
    "bottoms": "clothing",
    "dresses": "clothing",
    "suits": "clothing",
    "loungewear": "clothing",
    "sleepwear": "clothing",
    "workwear": "clothing",
    # Украшения L2 (под jewelry)
    "rings": "jewelry",
    "earrings": "jewelry",
    "necklaces": "jewelry",
    "bracelets": "jewelry",
    "brooches": "jewelry",
    "pendants-charms": "jewelry",
    "body-jewelry": "jewelry",
    "hair-jewelry": "jewelry",
    "mens-jewelry": "jewelry",
    "jewelry-sets": "jewelry",
    "wedding": "jewelry",
    "women": "jewelry",
    "men": "jewelry",
    # БАДы L2 (под supplements)
    "vitamins": "supplements",
    "minerals": "supplements",
    "immunity": "supplements",
    "digestive-health": "supplements",
    "energy-vitality": "supplements",
    "sports-nutrition": "supplements",
    "omega-fatty-acids": "supplements",
    "herbal-supplements": "supplements",
    "kids-supplements": "supplements",
    # Медикаменты L2 (под medicines)
    "antibiotics": "medicines",
    "painkillers": "medicines",
    "cold-flu": "medicines",
    "allergy": "medicines",
    "heart-cardiovascular": "medicines",
    "sleep-stress": "medicines",
    "cardio": "medicines",
    "dermatology": "medicines",
    "gastro": "medicines",
    "endocrinology-diabetes": "medicines",
    "ophthalmology": "medicines",
    "ent": "medicines",
    "orthopedics": "medicines",
    # Исламская одежда L2 (под islamic-clothing)
    "hijabs": "islamic-clothing",
    "abayas": "islamic-clothing",
    "jilbabs": "islamic-clothing",
    "niqabs": "islamic-clothing",
    "islamic-dresses": "islamic-clothing",
    "islamic-outerwear-women": "islamic-clothing",
    "islamic-sets": "islamic-clothing",
    "thobes": "islamic-clothing",
    "kurthas": "islamic-clothing",
    "shalwar": "islamic-clothing",
    "islamic-headwear": "islamic-clothing",
    "islamic-outerwear-men": "islamic-clothing",
    "prayer-clothing": "islamic-clothing",
    "festive-occasion-wear": "islamic-clothing",
    # Электроника L2 (под electronics)
    "smartphones-phones": "electronics",
    "laptops-computers": "electronics",
    "tablets": "electronics",
    "tvs-displays": "electronics",
    "audio": "electronics",
    "photo-video": "electronics",
    "gaming": "electronics",
    "smart-home": "electronics",
    "wearables": "electronics",
    "pc-components": "electronics",
    "networking": "electronics",
    "office-equipment": "electronics",
    "accessories-peripherals": "electronics",
    # Спорттовары L2 (под sports)
    "fitness-gym": "sports",
    "team-sports": "sports",
    "racket-sports": "sports",
    "martial-arts": "sports",
    "water-sports": "sports",
    "winter-sports": "sports",
    "cycling": "sports",
    "running-walking": "sports",
    "outdoor-hiking": "sports",
    "sportswear-footwear": "sports",
    "sports-sports-nutrition": "sports",
    # Головные уборы L2 (под headwear)
    "hw-winter-headwear": "headwear",
    "hw-summer-headwear": "headwear",
    "hw-caps": "headwear",
    "hw-hats": "headwear",
    "hw-berets": "headwear",
    "hw-turbans": "headwear",
    "hw-sport-headwear": "headwear",
    "hw-children-headwear": "headwear",
    # Нижнее бельё L2 (под underwear)
    "uw-womens-underwear": "underwear",
    "uw-mens-underwear": "underwear",
    "uw-children-underwear": "underwear",
    "uw-thermal-underwear": "underwear",
    "uw-sleepwear": "underwear",
    "uw-socks-hosiery": "underwear",
}


# Услуги: svc-* создаются с правильным parent в _seed_services_subcategories.
# НЕ добавляем их в SUBCAT_TO_ROOT — _fix_hierarchy перезаписал бы parent на uslugi
# и сломал бы иерархию (L2 под uslugi, L3 под L2 и т.д.).


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
        parser.add_argument(
            "--attributes-only",
            action="store_true",
            help="Создать только типы динамических атрибутов (GlobalAttributeKey)",
        )
        parser.add_argument(
            "--category-seo-only",
            action="store_true",
            help="Заполнить пустые SEO-поля категорий и обновить category metadata",
        )

    def handle(self, *args, **options):
        if options["fix_hierarchy"]:
            self._fix_hierarchy()
            return

        if options["category_seo_only"]:
            self._backfill_category_metadata()
            self.stdout.write(self.style.SUCCESS("Готово."))
            return

        if options["attributes_only"]:
            self._seed_attribute_keys()
            self.stdout.write(self.style.SUCCESS("Готово."))
            return

        with transaction.atomic():
            if not options["brands_only"]:
                self._seed_category_types()
                self._seed_root_categories()
                self._seed_subcategories()
                self._seed_medical_equipment_subcategories()
                self._seed_accessories_subcategories()
                self._seed_perfumery_subcategories()
                self._seed_incense_subcategories()
                self._seed_headwear_subcategories()
                self._seed_underwear_subcategories()
                self._seed_shoes_subcategories()
                self._seed_clothing_subcategories()
                self._seed_jewelry_subcategories()
                self._seed_supplements_subcategories()
                self._seed_medicines_subcategories()
                self._seed_furniture_subcategories()
                self._seed_auto_parts_subcategories()
                self._seed_tableware_subcategories()
                self._seed_electronics_subcategories()
                self._seed_sports_subcategories()
                self._seed_islamic_clothing_subcategories()
                self._seed_services_subcategories()
                self._seed_attribute_keys()
                self._fix_hierarchy()

            if not options["categories_only"]:
                self._seed_brands()

        self.stdout.write(self.style.SUCCESS("Готово."))

    def _ensure_category(
        self,
        *,
        slug,
        name,
        description,
        category_type,
        parent,
        sort_order,
        is_active=True,
    ):
        """Создать категорию или привести существующую к ожидаемой иерархии."""
        category, created = Category.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": description,
                "category_type": category_type,
                "parent": parent,
                "is_active": is_active,
                "sort_order": sort_order,
            },
        )

        update_fields = []
        if category.name != name:
            category.name = name
            update_fields.append("name")
        if (category.description or "") != (description or ""):
            category.description = description or ""
            update_fields.append("description")
        expected_type_id = category_type.id if category_type else None
        if category.category_type_id != expected_type_id:
            category.category_type = category_type
            update_fields.append("category_type")
        expected_parent_id = parent.id if parent else None
        if category.parent_id != expected_parent_id:
            category.parent = parent
            update_fields.append("parent")
        if category.is_active != is_active:
            category.is_active = is_active
            update_fields.append("is_active")
        if category.sort_order != sort_order:
            category.sort_order = sort_order
            update_fields.append("sort_order")

        metadata_updates = self._collect_category_metadata_updates(
            category=category,
            name=name,
            description=description or "",
            parent=parent,
        )
        for field_name, field_value in metadata_updates.items():
            if getattr(category, field_name) != field_value:
                setattr(category, field_name, field_value)
                update_fields.append(field_name)

        if update_fields:
            category.save(update_fields=update_fields)

        return category, created, bool(update_fields)

    def _collect_category_metadata_updates(self, *, category, name: str, description: str, parent):
        updates = {}
        inferred_gender = _infer_category_gender(name, category.slug)
        if inferred_gender:
            updates["gender"] = inferred_gender

        seo_defaults = _build_category_seo_defaults(
            name=name,
            slug=category.slug,
            description=description,
            parent=parent,
        )
        for field_name, field_value in seo_defaults.items():
            current_value = str(getattr(category, field_name, "") or "").strip()
            if not current_value:
                updates[field_name] = field_value
        return updates

    def _backfill_category_metadata(self):
        self.stdout.write("Заполнение SEO и metadata для категорий...")
        updated = 0
        for category in Category.objects.select_related("parent").order_by("id"):
            updates = self._collect_category_metadata_updates(
                category=category,
                name=category.name,
                description=category.description or "",
                parent=category.parent,
            )
            if not updates:
                continue
            for field_name, field_value in updates.items():
                setattr(category, field_name, field_value)
            category.save(update_fields=list(updates.keys()))
            updated += 1
        self.stdout.write(f"Обновлено категорий: {updated}")

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
            cat, created, updated = self._ensure_category(
                slug=slug,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=None,
                is_active=True,
                sort_order=i,
            )
            if created:
                self.stdout.write(f"  ✓ Корневая: {slug}")
            elif updated:
                self.stdout.write(f"  ↻ Корневая исправлена: {slug}")
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)

    def _seed_subcategories(self):
        self.stdout.write("Создание подкатегорий...")
        for parent_slug, items in SUB_CATEGORIES.items():
            parent = Category.objects.filter(slug=parent_slug, parent__isnull=True).first()
            if not parent:
                self.stdout.write(self.style.WARNING(f"  Родитель не найден: {parent_slug}, пропуск"))
                continue
            for sort, (name_ru, name_en, sub_slug, desc_ru, desc_en) in enumerate(items):
                cat, created, updated = self._ensure_category(
                    slug=sub_slug,
                    name=name_ru,
                    description=desc_ru or name_ru,
                    category_type=parent.category_type,
                    parent=parent,
                    is_active=True,
                    sort_order=sort,
                )
                if created:
                    self.stdout.write(f"  ✓ Подкатегория: {sub_slug} -> {parent_slug}")
                elif updated:
                    self.stdout.write(f"  ↻ Исправлен parent: {sub_slug} -> {parent_slug}")
                _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)

    def _seed_medical_equipment_subcategories(self):
        """Создание подкатегорий медтехники (L2–L4) по MEDICAL_EQUIPMENT_SUBCATEGORIES. Рекурсивно."""
        def create_category(parent, name_ru, name_en, slug, desc_ru, desc_en, sort_order, cat_type):
            cat, created, _ = self._ensure_category(
                slug=slug,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=parent,
                is_active=True,
                sort_order=sort_order,
            )
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            return cat, created

        def process_children(parent_cat, items, level: int, parent_slug: str):
            for sort_i, item in enumerate(items):
                if len(item) == 6:
                    name_ru, name_en, slug, desc_ru, desc_en, children = item
                else:
                    name_ru, name_en, slug, desc_ru, desc_en = item
                    children = []
                cat, created = create_category(
                    parent_cat, name_ru, name_en, slug, desc_ru, desc_en, sort_i, cat_type
                )
                if created:
                    self.stdout.write(f"  ✓ L{level}: {slug} -> {parent_slug}")
                if children:
                    process_children(cat, children, level + 1, slug)

        self.stdout.write("Создание подкатегорий медтехники...")
        root = Category.objects.filter(slug="medical-equipment", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория medical-equipment не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(MEDICAL_EQUIPMENT_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> medical-equipment")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> medical-equipment")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            process_children(cat_l2, children, 3, slug_l2)

    def _seed_accessories_subcategories(self):
        """Создание подкатегорий аксессуаров (L2–L4) по ACCESSORIES_SUBCATEGORIES. Рекурсивно."""
        def create_category(parent, name_ru, name_en, slug, desc_ru, desc_en, sort_order, cat_type):
            cat, created, _ = self._ensure_category(
                slug=slug,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=parent,
                is_active=True,
                sort_order=sort_order,
            )
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            return cat, created

        def process_children(parent_cat, items, level: int, parent_slug: str):
            for sort_i, item in enumerate(items):
                if len(item) == 6:
                    name_ru, name_en, slug, desc_ru, desc_en, children = item
                else:
                    name_ru, name_en, slug, desc_ru, desc_en = item
                    children = []
                cat, created = create_category(
                    parent_cat, name_ru, name_en, slug, desc_ru, desc_en, sort_i, cat_type
                )
                if created:
                    self.stdout.write(f"  ✓ L{level}: {slug} -> {parent_slug}")
                if children:
                    process_children(cat, children, level + 1, slug)

        self.stdout.write("Создание подкатегорий аксессуаров...")
        root = Category.objects.filter(slug="accessories", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория accessories не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(ACCESSORIES_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> accessories")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> accessories")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            process_children(cat_l2, children, 3, slug_l2)

    def _seed_perfumery_subcategories(self):
        """Создание подкатегорий парфюмерии (L2–L4) по PERFUMERY_SUBCATEGORIES. Рекурсивно."""
        def create_category(parent, name_ru, name_en, slug, desc_ru, desc_en, sort_order, cat_type):
            cat, created, _ = self._ensure_category(
                slug=slug,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=parent,
                is_active=True,
                sort_order=sort_order,
            )
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            return cat, created

        def process_children(parent_cat, items, level: int, parent_slug: str):
            for sort_i, item in enumerate(items):
                if len(item) == 6:
                    name_ru, name_en, slug, desc_ru, desc_en, children = item
                else:
                    name_ru, name_en, slug, desc_ru, desc_en = item
                    children = []
                cat, created = create_category(
                    parent_cat, name_ru, name_en, slug, desc_ru, desc_en, sort_i, cat_type
                )
                if created:
                    self.stdout.write(f"  ✓ L{level}: {slug} -> {parent_slug}")
                if children:
                    process_children(cat, children, level + 1, slug)

        self.stdout.write("Создание подкатегорий парфюмерии...")
        root = Category.objects.filter(slug="perfumery", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория perfumery не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(PERFUMERY_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> perfumery")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> perfumery")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            process_children(cat_l2, children, 3, slug_l2)

    def _seed_incense_subcategories(self):
        """Создание подкатегорий благовоний (L2–L4) по INCENSE_SUBCATEGORIES. Рекурсивно."""
        def create_category(parent, name_ru, name_en, slug, desc_ru, desc_en, sort_order, cat_type):
            cat, created, _ = self._ensure_category(
                slug=slug,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=parent,
                is_active=True,
                sort_order=sort_order,
            )
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            return cat, created

        def process_children(parent_cat, items, level: int, parent_slug: str):
            for sort_i, item in enumerate(items):
                if len(item) == 6:
                    name_ru, name_en, slug, desc_ru, desc_en, children = item
                else:
                    name_ru, name_en, slug, desc_ru, desc_en = item
                    children = []
                cat, created = create_category(
                    parent_cat, name_ru, name_en, slug, desc_ru, desc_en, sort_i, cat_type
                )
                if created:
                    self.stdout.write(f"  ✓ L{level}: {slug} -> {parent_slug}")
                if children:
                    process_children(cat, children, level + 1, slug)

        self.stdout.write("Создание подкатегорий благовоний...")
        root = Category.objects.filter(slug="incense", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория incense не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(INCENSE_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> incense")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> incense")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            process_children(cat_l2, children, 3, slug_l2)

    def _seed_headwear_subcategories(self):
        """Создание подкатегорий головных уборов (L2–L4) по HEADWEAR_SUBCATEGORIES. Рекурсивно."""
        def create_category(parent, name_ru, name_en, slug, desc_ru, desc_en, sort_order, cat_type):
            cat, created, _ = self._ensure_category(
                slug=slug,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=parent,
                is_active=True,
                sort_order=sort_order,
            )
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            return cat, created

        def process_children(parent_cat, items, level: int, parent_slug: str):
            for sort_i, item in enumerate(items):
                if len(item) == 6:
                    name_ru, name_en, slug, desc_ru, desc_en, children = item
                else:
                    name_ru, name_en, slug, desc_ru, desc_en = item
                    children = []
                cat, created = create_category(
                    parent_cat, name_ru, name_en, slug, desc_ru, desc_en, sort_i, cat_type
                )
                if created:
                    self.stdout.write(f"  ✓ L{level}: {slug} -> {parent_slug}")
                if children:
                    process_children(cat, children, level + 1, slug)

        self.stdout.write("Создание подкатегорий головных уборов...")
        root = Category.objects.filter(slug="headwear", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория headwear не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(HEADWEAR_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> headwear")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> headwear")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            process_children(cat_l2, children, 3, slug_l2)

    def _seed_underwear_subcategories(self):
        """Создание подкатегорий нижнего белья (L2–L4) по UNDERWEAR_SUBCATEGORIES. Рекурсивно."""
        def create_category(parent, name_ru, name_en, slug, desc_ru, desc_en, sort_order, cat_type):
            cat, created, _ = self._ensure_category(
                slug=slug,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=parent,
                is_active=True,
                sort_order=sort_order,
            )
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            return cat, created

        def process_children(parent_cat, items, level: int, parent_slug: str):
            for sort_i, item in enumerate(items):
                if len(item) == 6:
                    name_ru, name_en, slug, desc_ru, desc_en, children = item
                else:
                    name_ru, name_en, slug, desc_ru, desc_en = item
                    children = []
                cat, created = create_category(
                    parent_cat, name_ru, name_en, slug, desc_ru, desc_en, sort_i, cat_type
                )
                if created:
                    self.stdout.write(f"  ✓ L{level}: {slug} -> {parent_slug}")
                if children:
                    process_children(cat, children, level + 1, slug)

        self.stdout.write("Создание подкатегорий нижнего белья...")
        root = Category.objects.filter(slug="underwear", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория underwear не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(UNDERWEAR_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> underwear")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> underwear")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            process_children(cat_l2, children, 3, slug_l2)

    def _seed_shoes_subcategories(self):
        """Создание подкатегорий обуви (L2 и L3) по схеме из SHOE_SUBCATEGORIES."""
        self.stdout.write("Создание подкатегорий обуви...")
        shoes_root = Category.objects.filter(slug="shoes", parent__isnull=True).first()
        if not shoes_root:
            self.stdout.write(self.style.WARNING("  Корневая категория shoes не найдена, пропуск"))
            return
        cat_type = shoes_root.category_type
        for sort_l2, item in enumerate(SHOE_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=shoes_root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> shoes")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> shoes")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            for sort_l3, child in enumerate(children):
                c_ru, c_en, c_slug, c_desc_ru, c_desc_en = child
                cat_l3, created, updated = self._ensure_category(
                    slug=c_slug,
                    name=c_ru,
                    description=c_desc_ru or c_ru,
                    category_type=cat_type,
                    parent=cat_l2,
                    is_active=True,
                    sort_order=sort_l3,
                )
                if created:
                    self.stdout.write(f"  ✓ L3: {c_slug} -> {slug_l2}")
                elif updated:
                    self.stdout.write(f"  ↻ L3 исправлен: {c_slug} -> {slug_l2}")
                _ensure_category_translations(cat_l3, c_ru, c_en, c_desc_ru or c_ru, c_desc_en or c_en)

    def _seed_clothing_subcategories(self):
        """Создание подкатегорий одежды (L2–L4) по схеме из CLOTHING_SUBCATEGORIES. Рекурсивно."""

        def create_category(parent, name_ru, name_en, slug, desc_ru, desc_en, sort_order, cat_type):
            cat, created, _ = self._ensure_category(
                slug=slug,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=parent,
                is_active=True,
                sort_order=sort_order,
            )
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            return cat, created

        def process_children(parent_cat, items, level: int, parent_slug: str):
            for sort_i, item in enumerate(items):
                if len(item) == 6:
                    name_ru, name_en, slug, desc_ru, desc_en, children = item
                else:
                    name_ru, name_en, slug, desc_ru, desc_en = item
                    children = []
                cat, created = create_category(
                    parent_cat, name_ru, name_en, slug, desc_ru, desc_en, sort_i, cat_type
                )
                if created:
                    self.stdout.write(f"  ✓ L{level}: {slug} -> {parent_slug}")
                if children:
                    process_children(cat, children, level + 1, slug)

        self.stdout.write("Создание подкатегорий одежды...")
        clothing_root = Category.objects.filter(slug="clothing", parent__isnull=True).first()
        if not clothing_root:
            self.stdout.write(self.style.WARNING("  Корневая категория clothing не найдена, пропуск"))
            return
        cat_type = clothing_root.category_type
        for sort_l2, item in enumerate(CLOTHING_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=clothing_root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> clothing")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> clothing")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            process_children(cat_l2, children, 3, slug_l2)

    def _seed_jewelry_subcategories(self):
        """Создание подкатегорий украшений (L2 и L3) по схеме из JEWELRY_SUBCATEGORIES."""
        self.stdout.write("Создание подкатегорий украшений...")
        jewelry_root = Category.objects.filter(slug="jewelry", parent__isnull=True).first()
        if not jewelry_root:
            self.stdout.write(self.style.WARNING("  Корневая категория jewelry не найдена, пропуск"))
            return
        cat_type = jewelry_root.category_type
        for sort_l2, item in enumerate(JEWELRY_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=jewelry_root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> jewelry")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> jewelry")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            for sort_l3, child in enumerate(children):
                c_ru, c_en, c_slug, c_desc_ru, c_desc_en = child
                cat_l3, created, updated = self._ensure_category(
                    slug=c_slug,
                    name=c_ru,
                    description=c_desc_ru or c_ru,
                    category_type=cat_type,
                    parent=cat_l2,
                    is_active=True,
                    sort_order=sort_l3,
                )
                if created:
                    self.stdout.write(f"  ✓ L3: {c_slug} -> {slug_l2}")
                elif updated:
                    self.stdout.write(f"  ↻ Исправлен parent: {c_slug} -> {slug_l2}")
                _ensure_category_translations(cat_l3, c_ru, c_en, c_desc_ru or c_ru, c_desc_en or c_en)

    def _seed_supplements_subcategories(self):
        """Создание подкатегорий БАДов (L2 и L3) по SUPPLEMENTS_SUBCATEGORIES."""
        self.stdout.write("Создание подкатегорий БАДов...")
        root = Category.objects.filter(slug="supplements", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория supplements не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(SUPPLEMENTS_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> supplements")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> supplements")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            for sort_l3, child in enumerate(children):
                c_ru, c_en, c_slug, c_desc_ru, c_desc_en = child
                cat_l3, created, updated = self._ensure_category(
                    slug=c_slug,
                    name=c_ru,
                    description=c_desc_ru or c_ru,
                    category_type=cat_type,
                    parent=cat_l2,
                    is_active=True,
                    sort_order=sort_l3,
                )
                if created:
                    self.stdout.write(f"  ✓ L3: {c_slug} -> {slug_l2}")
                elif updated:
                    self.stdout.write(f"  ↻ Исправлен parent: {c_slug} -> {slug_l2}")
                _ensure_category_translations(cat_l3, c_ru, c_en, c_desc_ru or c_ru, c_desc_en or c_en)

    def _seed_medicines_subcategories(self):
        """Создание подкатегорий медикаментов (L2 и L3) по MEDICINES_SUBCATEGORIES."""
        self.stdout.write("Создание подкатегорий медикаментов...")
        root = Category.objects.filter(slug="medicines", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория medicines не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(MEDICINES_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> medicines")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> medicines")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            for sort_l3, child in enumerate(children):
                c_ru, c_en, c_slug, c_desc_ru, c_desc_en = child
                cat_l3, created, updated = self._ensure_category(
                    slug=c_slug,
                    name=c_ru,
                    description=c_desc_ru or c_ru,
                    category_type=cat_type,
                    parent=cat_l2,
                    is_active=True,
                    sort_order=sort_l3,
                )
                if created:
                    self.stdout.write(f"  ✓ L3: {c_slug} -> {slug_l2}")
                elif updated:
                    self.stdout.write(f"  ↻ Исправлен parent: {c_slug} -> {slug_l2}")
                _ensure_category_translations(cat_l3, c_ru, c_en, c_desc_ru or c_ru, c_desc_en or c_en)

    def _seed_furniture_subcategories(self):
        """Создание подкатегорий мебели (L2 и L3) по FURNITURE_SUBCATEGORIES."""
        self.stdout.write("Создание подкатегорий мебели...")
        root = Category.objects.filter(slug="furniture", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория furniture не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(FURNITURE_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> furniture")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> furniture")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            for sort_l3, child in enumerate(children):
                c_ru, c_en, c_slug, c_desc_ru, c_desc_en = child
                cat_l3, created, updated = self._ensure_category(
                    slug=c_slug,
                    name=c_ru,
                    description=c_desc_ru or c_ru,
                    category_type=cat_type,
                    parent=cat_l2,
                    is_active=True,
                    sort_order=sort_l3,
                )
                if created:
                    self.stdout.write(f"  ✓ L3: {c_slug} -> {slug_l2}")
                elif updated:
                    self.stdout.write(f"  ↻ Исправлен parent: {c_slug} -> {slug_l2}")
                _ensure_category_translations(cat_l3, c_ru, c_en, c_desc_ru or c_ru, c_desc_en or c_en)

    def _seed_auto_parts_subcategories(self):
        """Создание подкатегорий автозапчастей (L2 и L3) по AUTO_PARTS_SUBCATEGORIES."""
        self.stdout.write("Создание подкатегорий автозапчастей...")
        root = Category.objects.filter(slug="auto-parts", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория auto-parts не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(AUTO_PARTS_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> auto-parts")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> auto-parts")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            for sort_l3, child in enumerate(children):
                c_ru, c_en, c_slug, c_desc_ru, c_desc_en = child
                cat_l3, created, updated = self._ensure_category(
                    slug=c_slug,
                    name=c_ru,
                    description=c_desc_ru or c_ru,
                    category_type=cat_type,
                    parent=cat_l2,
                    is_active=True,
                    sort_order=sort_l3,
                )
                if created:
                    self.stdout.write(f"  ✓ L3: {c_slug} -> {slug_l2}")
                elif updated:
                    self.stdout.write(f"  ↻ Исправлен parent: {c_slug} -> {slug_l2}")
                _ensure_category_translations(cat_l3, c_ru, c_en, c_desc_ru or c_ru, c_desc_en or c_en)

    def _seed_tableware_subcategories(self):
        """Создание подкатегорий посуды (L2–L4) по TABLEWARE_SUBCATEGORIES. Рекурсивно."""
        def create_category(parent, name_ru, name_en, slug, desc_ru, desc_en, sort_order, cat_type):
            cat, created, _ = self._ensure_category(
                slug=slug,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=parent,
                is_active=True,
                sort_order=sort_order,
            )
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            return cat, created

        def process_children(parent_cat, items, level: int, parent_slug: str):
            for sort_i, item in enumerate(items):
                if len(item) == 6:
                    name_ru, name_en, slug, desc_ru, desc_en, children = item
                else:
                    name_ru, name_en, slug, desc_ru, desc_en = item
                    children = []
                cat, created = create_category(
                    parent_cat, name_ru, name_en, slug, desc_ru, desc_en, sort_i, cat_type
                )
                if created:
                    self.stdout.write(f"  ✓ L{level}: {slug} -> {parent_slug}")
                if children:
                    process_children(cat, children, level + 1, slug)

        self.stdout.write("Создание подкатегорий посуды...")
        root = Category.objects.filter(slug="tableware", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория tableware не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(TABLEWARE_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> tableware")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> tableware")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            process_children(cat_l2, children, 3, slug_l2)

    def _seed_electronics_subcategories(self):
        """Создание подкатегорий электроники (L2–L4) по ELECTRONICS_SUBCATEGORIES. Рекурсивно."""
        def create_category(parent, name_ru, name_en, slug, desc_ru, desc_en, sort_order, cat_type):
            cat, created, _ = self._ensure_category(
                slug=slug,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=parent,
                is_active=True,
                sort_order=sort_order,
            )
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            return cat, created

        def process_children(parent_cat, items, level: int, parent_slug: str):
            for sort_i, item in enumerate(items):
                if len(item) == 6:
                    name_ru, name_en, slug, desc_ru, desc_en, children = item
                else:
                    name_ru, name_en, slug, desc_ru, desc_en = item
                    children = []
                cat, created = create_category(
                    parent_cat, name_ru, name_en, slug, desc_ru, desc_en, sort_i, cat_type
                )
                if created:
                    self.stdout.write(f"  ✓ L{level}: {slug} -> {parent_slug}")
                if children:
                    process_children(cat, children, level + 1, slug)

        self.stdout.write("Создание подкатегорий электроники...")
        root = Category.objects.filter(slug="electronics", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория electronics не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(ELECTRONICS_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> electronics")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> electronics")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            process_children(cat_l2, children, 3, slug_l2)

    def _seed_sports_subcategories(self):
        """Создание подкатегорий спорттоваров (L2–L4) по SPORTS_SUBCATEGORIES. Рекурсивно."""
        def create_category(parent, name_ru, name_en, slug, desc_ru, desc_en, sort_order, cat_type):
            cat, created, _ = self._ensure_category(
                slug=slug,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=parent,
                is_active=True,
                sort_order=sort_order,
            )
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            return cat, created

        def process_children(parent_cat, items, level: int, parent_slug: str):
            for sort_i, item in enumerate(items):
                if len(item) == 6:
                    name_ru, name_en, slug, desc_ru, desc_en, children = item
                else:
                    name_ru, name_en, slug, desc_ru, desc_en = item
                    children = []
                cat, created = create_category(
                    parent_cat, name_ru, name_en, slug, desc_ru, desc_en, sort_i, cat_type
                )
                if created:
                    self.stdout.write(f"  ✓ L{level}: {slug} -> {parent_slug}")
                if children:
                    process_children(cat, children, level + 1, slug)

        self.stdout.write("Создание подкатегорий спорттоваров...")
        root = Category.objects.filter(slug="sports", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория sports не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(SPORTS_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> sports")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> sports")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            process_children(cat_l2, children, 3, slug_l2)

    def _seed_islamic_clothing_subcategories(self):
        """Создание подкатегорий исламской одежды (L2 и L3) по ISLAMIC_CLOTHING_SUBCATEGORIES."""
        self.stdout.write("Создание подкатегорий исламской одежды...")
        root = Category.objects.filter(slug="islamic-clothing", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория islamic-clothing не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(ISLAMIC_CLOTHING_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> islamic-clothing")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> islamic-clothing")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            for sort_l3, child in enumerate(children):
                c_ru, c_en, c_slug, c_desc_ru, c_desc_en = child
                cat_l3, created, updated = self._ensure_category(
                    slug=c_slug,
                    name=c_ru,
                    description=c_desc_ru or c_ru,
                    category_type=cat_type,
                    parent=cat_l2,
                    is_active=True,
                    sort_order=sort_l3,
                )
                if created:
                    self.stdout.write(f"  ✓ L3: {c_slug} -> {slug_l2}")
                elif updated:
                    self.stdout.write(f"  ↻ Исправлен parent: {c_slug} -> {slug_l2}")
                _ensure_category_translations(cat_l3, c_ru, c_en, c_desc_ru or c_ru, c_desc_en or c_en)

    def _seed_services_subcategories(self):
        """Создание подкатегорий услуг (L2–L5) по SERVICES_SUBCATEGORIES. Рекурсивно."""
        def create_category(parent, name_ru, name_en, slug, desc_ru, desc_en, sort_order, cat_type):
            cat, created, _ = self._ensure_category(
                slug=slug,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=parent,
                is_active=True,
                sort_order=sort_order,
            )
            _ensure_category_translations(cat, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            return cat, created

        def process_children(parent_cat, items, level: int, parent_slug: str):
            for sort_i, item in enumerate(items):
                if len(item) == 6:
                    name_ru, name_en, slug, desc_ru, desc_en, children = item
                else:
                    name_ru, name_en, slug, desc_ru, desc_en = item
                    children = []
                cat, created = create_category(
                    parent_cat, name_ru, name_en, slug, desc_ru, desc_en, sort_i, cat_type
                )
                if created:
                    self.stdout.write(f"  ✓ L{level}: {slug} -> {parent_slug}")
                if children:
                    process_children(cat, children, level + 1, slug)

        self.stdout.write("Создание подкатегорий услуг...")
        root = Category.objects.filter(slug="uslugi", parent__isnull=True).first()
        if not root:
            self.stdout.write(self.style.WARNING("  Корневая категория uslugi не найдена, пропуск"))
            return
        cat_type = root.category_type
        for sort_l2, item in enumerate(SERVICES_SUBCATEGORIES):
            name_ru, name_en, slug_l2, desc_ru, desc_en, children = item
            cat_l2, created, updated = self._ensure_category(
                slug=slug_l2,
                name=name_ru,
                description=desc_ru or name_ru,
                category_type=cat_type,
                parent=root,
                is_active=True,
                sort_order=sort_l2,
            )
            if created:
                self.stdout.write(f"  ✓ L2: {slug_l2} -> uslugi")
            elif updated:
                self.stdout.write(f"  ↻ L2 исправлен: {slug_l2} -> uslugi")
            _ensure_category_translations(cat_l2, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)
            process_children(cat_l2, children, 3, slug_l2)

    def _seed_attribute_keys(self):
        """Создание типов динамических атрибутов (GlobalAttributeKey) по ECOMMERCE_ATTRIBUTES."""
        self.stdout.write("Создание типов динамических атрибутов...")
        for sort_order, item in enumerate(ECOMMERCE_ATTRIBUTES):
            slug, name_ru, name_en, attr_sort, category_slugs = item
            key, created = GlobalAttributeKey.objects.get_or_create(
                slug=slug,
                defaults={
                    "sort_order": attr_sort,
                },
            )
            if created:
                self.stdout.write(f"  ✓ {slug}")
            key.sort_order = attr_sort
            key.save()
            # Переводы
            for locale, name in [("ru", name_ru), ("en", name_en)]:
                trans, _ = GlobalAttributeKeyTranslation.objects.get_or_create(
                    key_obj=key,
                    locale=locale,
                    defaults={"name": name},
                )
                if trans.name != name:
                    trans.name = name
                    trans.save()
            # Категории (M2M)
            categories = list(
                Category.objects.filter(slug__in=category_slugs).values_list("id", flat=True)
            )
            existing = set(key.categories.values_list("id", flat=True))
            to_add = [c for c in categories if c not in existing]
            if to_add:
                key.categories.add(*to_add)

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
        other_brand, other_created = Brand.objects.update_or_create(
            slug="other",
            defaults={
                "name": "Другое",
                "description": "",
                "website": "",
                "is_active": True,
                "primary_category_slug": "",
            },
        )
        BrandTranslation.objects.update_or_create(
            brand=other_brand,
            locale="ru",
            defaults={"name": "Другое", "description": ""},
        )
        BrandTranslation.objects.update_or_create(
            brand=other_brand,
            locale="en",
            defaults={"name": "Other", "description": ""},
        )
        if other_created:
            self.stdout.write("  ✓ Бренд: Другое (other)")


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


def _category_site_label() -> str:
    for attr in ("SITE_NAME", "PROJECT_NAME"):
        value = str(getattr(settings, attr, "") or "").strip()
        if value:
            return value
    return "Mudaroba"


def _normalize_seed_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return text.translate(str.maketrans({
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "İ": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
    }))


def _infer_category_gender(name: str | None, slug: str | None) -> str:
    haystack = f"{name or ''} {slug or ''}".strip().lower()
    normalized = _normalize_seed_text(haystack)
    if re.search(r"(^|[^a-zа-я])(women('?s)?|woman)([^a-zа-я]|$)", haystack) or "жен" in haystack or "kadin" in normalized:
        return "women"
    if re.search(r"(^|[^a-zа-я])(men('?s)?|man)([^a-zа-я]|$)", haystack) or "муж" in haystack or "erkek" in normalized:
        return "men"
    if "unisex" in haystack or "унисекс" in haystack:
        return "unisex"
    if re.search(r"(^|[^a-zа-я])(kids?|children|child|baby)([^a-zа-я]|$)", haystack) or "дет" in haystack or "cocuk" in normalized or "bebek" in normalized:
        return "kids"
    return ""


def _build_category_seo_defaults(*, name: str, slug: str, description: str, parent) -> dict[str, str]:
    site_label = _category_site_label()
    parent_name = str(getattr(parent, "name", "") or "").strip()
    root_name = parent_name
    current_parent = parent
    while getattr(current_parent, "parent", None):
        current_parent = current_parent.parent
        root_name = str(getattr(current_parent, "name", "") or "").strip() or root_name

    keyword_values = []
    for value in (name, parent_name, root_name):
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in keyword_values:
            keyword_values.append(cleaned)

    meta_title_parts = [name]
    if parent_name and parent_name != name:
        meta_title_parts.append(parent_name)
    meta_title_parts.append(site_label)
    meta_title = " | ".join(part for part in meta_title_parts if part)

    if description:
        meta_description = description.strip()
    elif parent_name:
        meta_description = f"{name} в категории {parent_name} на {site_label}."
    else:
        meta_description = f"{name} на {site_label}."

    if root_name and root_name not in keyword_values:
        keyword_values.append(root_name)
    slug_token = str(slug or "").replace("-", " ").strip()
    if slug_token and slug_token not in keyword_values:
        keyword_values.append(slug_token)

    meta_keywords = ", ".join(keyword_values)
    return {
        "meta_title": meta_title[:255],
        "meta_description": meta_description[:500],
        "meta_keywords": meta_keywords[:500],
        "og_title": meta_title[:255],
        "og_description": meta_description[:500],
    }
