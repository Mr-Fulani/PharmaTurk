"""
Маппинг категории (slug/название) → Category и product_type для парсеров и нормалайзера.

Единый источник правды: по строке из ScrapedProduct.category или ProductData.category
получаем объект Category и product_type для создания/обновления Product без дублирования
логики в catalog и scrapers.

Все корневые категории из ROOT_CATEGORIES попадают в маппинг автоматически (slug + name_ru,
name_en). Дополнительные алиасы (book, книга, jewellery и т.д.) задаются в EXTRA_ALIASES.
Обработчики по типам (sync_metadata, get_domain, update_attributes) добавляются по мере
появления парсеров для этих типов.
"""
import re
import unicodedata
from typing import Tuple, Optional

from django.utils.text import slugify

from .constants import ROOT_CATEGORIES, get_or_create_root_category
from .models import Category
from transliterate import slugify as trans_slugify


def _normalize_category_alias_key(value: str) -> str:
    """Нормализует ключ категории для устойчивого матчинга алиасов."""
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold().replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _build_category_aliases() -> dict:
    """Строит алиасы из ROOT_CATEGORIES: slug и названия (ru/en) → slug."""
    # Формат: (slug, name_ru, name_en, desc_ru, desc_en, category_type_slug)
    aliases = {}
    for row in ROOT_CATEGORIES:
        cat_slug = row[0]
        name_ru = (row[1] or "").strip().lower()
        name_en = (row[2] or "").strip().lower()
        if cat_slug:
            aliases[_normalize_category_alias_key(cat_slug)] = cat_slug
        if name_ru:
            aliases[_normalize_category_alias_key(name_ru)] = cat_slug
        if name_en:
            aliases[_normalize_category_alias_key(name_en)] = cat_slug
    return aliases


# Дополнительные алиасы: варианты, которых нет в name_ru/name_en (единственное число,
# сокращения, альтернативное написание). «книги» уже есть из ROOT_CATEGORIES, «книга» — отдельно.
EXTRA_ALIASES = {
    "книга": "books",   # единственное число; «книги» даёт _build_category_aliases()
    "book": "books",    # en единственное число; «books» даёт build
    "jewellery": "jewelry",
    "aksesuar": "accessories",
    "canta": "accessories",
    "çanta": "accessories",
    "kemer": "accessories",
    "cuzdan": "accessories",
    "cüzdan": "accessories",
    "saat": "accessories",
    "seyahat": "accessories",
    "travel": "accessories",
    "taki": "jewelry",
    "takı": "jewelry",
    "kozmetik": "perfumery",
    "kisisel bakim": "perfumery",
    "kişisel bakım": "perfumery",
    "kozmetik | kisisel bakim": "perfumery",
    "kozmetik | kişisel bakım": "perfumery",
    "makyaj": "perfumery",
    "cilt bakim": "perfumery",
    "cilt bakım": "perfumery",
    "gunes bakim": "perfumery",
    "güneş bakım": "perfumery",
    "vucut bakim": "perfumery",
    "vücut bakım": "perfumery",
    "parfum": "perfumery",
    "parfüm": "perfumery",
    "бады": "supplements",
    "медицина": "medicines",
    "медтехника": "medical-equipment",
    "автозапчасти": "auto-parts",
    "услуги": "uslugi",
    "спорт": "sports",
    "спорттовары": "sports",
    "нижнее белье": "underwear",
    "головные уборы": "headwear",
    "исламская одежда": "islamic-clothing",
    "благовония": "incense",
}

CATEGORY_NAME_ALIASES = {
    **_build_category_aliases(),
    **{_normalize_category_alias_key(key): value for key, value in EXTRA_ALIASES.items()},
}
ALLOWED_ROOT_SLUGS = {r[0] for r in ROOT_CATEGORIES}


def resolve_category_and_product_type(category_value: str) -> Tuple[Optional[Category], Optional[str]]:
    """
    По строке (slug или название категории) возвращает (Category | None, product_type | None).

    Используется в CatalogNormalizer.normalize_product и в ScraperIntegrationService
    при обновлении существующего товара. Гарантирует один маппинг для всех слоёв.
    """
    if not category_value or not isinstance(category_value, str):
        return None, None

    raw = category_value.strip()
    if not raw:
        return None, None

    normalized_name = _normalize_category_alias_key(raw)
    # Сначала проверяем алиасы
    slug_from_alias = CATEGORY_NAME_ALIASES.get(normalized_name)
    if slug_from_alias:
        cat_slug = slug_from_alias
    else:
        cat_slug = (trans_slugify(raw, language_code="ru") or slugify(raw) or "").lower()
        if not cat_slug:
            return None, None
        # Нормализуем в формат корневых категорий (с дефисом)
        cat_slug = cat_slug.replace("_", "-")

    category = Category.objects.filter(
        slug=cat_slug
    ).first()
    if not category and cat_slug in ALLOWED_ROOT_SLUGS:
        category = get_or_create_root_category(cat_slug)

    if not category:
        return None, None

    # product_type в модели Product с подчёркиваниями (medical_equipment, auto_parts)
    current_cat = category
    product_type = None
    
    # 1. Ищем category_type вверх по дереву
    while current_cat:
        if getattr(current_cat, "category_type", None) and current_cat.category_type:
            product_type = (current_cat.category_type.slug or "").replace("-", "_")
            break
        current_cat = current_cat.parent
        
    # 2. Если category_type нигде нет, берём slug корневой категории
    if not product_type:
        current_cat = category
        while current_cat.parent:
            current_cat = current_cat.parent
        product_type = (current_cat.slug or "").replace("-", "_")

    return category, product_type or None
