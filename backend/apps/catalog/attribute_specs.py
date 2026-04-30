"""Единый реестр правил для динамических атрибутов товаров.

Здесь описываем только те атрибуты, которые:
1. Разрешено автоматически публиковать в dynamic_attributes.
2. Можно безопасно использовать в фильтрах/карточке товара.

Все прочие сырые ключи парсера остаются в external_data.attributes и не
попадают на витрину без явного правила в этом модуле.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


def normalize_product_type(value: str | None) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def normalize_ascii_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    replacements = str.maketrans({
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "İ": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
    })
    return text.translate(replacements)


@dataclass(frozen=True)
class DynamicAttributeSpec:
    slug: str
    name_ru: str
    name_en: str
    sort_order: int
    product_types: tuple[str, ...]
    source_keys: tuple[str, ...] = ()
    source_key_contains: tuple[str, ...] = ()
    value_aliases: tuple[tuple[str, str], ...] = ()
    facet_enabled: bool = True
    display_enabled: bool = True
    auto_apply: bool = True
    max_length: int = 100
    max_words: int = 8


@dataclass(frozen=True)
class ResolvedDynamicAttribute:
    slug: str
    value: str
    value_ru: str
    value_en: str | None
    name_ru: str
    name_en: str
    sort_order: int
    facet_enabled: bool
    display_enabled: bool


ATTRIBUTE_SPECS: tuple[DynamicAttributeSpec, ...] = (
    DynamicAttributeSpec(
        slug="material",
        name_ru="Материал",
        name_en="Material",
        sort_order=1,
        product_types=("shoes", "accessories"),
        source_keys=("material", "malzeme", "материал"),
        source_key_contains=("material", "malzeme", "материал"),
        value_aliases=(
            ("hakiki deri", "Натуральная кожа"),
            ("gercek deri", "Натуральная кожа"),
            ("gerçek deri", "Натуральная кожа"),
            ("suni deri", "Искусственная кожа"),
            ("vegan deri", "Искусственная кожа"),
            ("pamuk", "Хлопок"),
            ("kumas", "Ткань"),
            ("kumaş", "Ткань"),
            ("tekstil", "Текстиль"),
            ("textile", "Текстиль"),
            ("metal", "Металл"),
            ("polar", "Флис"),
            ("hasir", "Соломка"),
            ("hasır", "Соломка"),
            ("rezin", "Резина"),
            ("rubber", "Резина"),
            ("kaucuk", "Каучук"),
            ("kauçuk", "Каучук"),
            ("eva", "EVA"),
            ("poliuretan", "Полиуретан"),
            ("polyurethane", "Полиуретан"),
        ),
        max_words=4,
    ),
    DynamicAttributeSpec(
        slug="sole-material",
        name_ru="Материал подошвы",
        name_en="Sole Material",
        sort_order=20,
        product_types=("shoes",),
        source_keys=("sole_material", "sole-material", "материал_подошвы", "taban_malzeme", "taban_malzemesi"),
        source_key_contains=("taban", "sole", "подошв"),
        value_aliases=(
            ("rezin", "Резина"),
            ("rubber", "Резина"),
            ("kaucuk", "Каучук"),
            ("kauçuk", "Каучук"),
            ("eva", "EVA"),
            ("poliuretan", "Полиуретан"),
            ("polyurethane", "Полиуретан"),
        ),
        max_words=4,
    ),
    DynamicAttributeSpec(
        slug="closure-type",
        name_ru="Тип застёжки",
        name_en="Closure Type",
        sort_order=22,
        product_types=("shoes", "accessories"),
        source_keys=(
            "closure_type",
            "closure-type",
            "тип_застежки",
            "тип_застёжки",
            "baglama_sekli",
            "bağlama_şekli",
            "bağlama_sekli",
            "kapama_tipi",
        ),
        source_key_contains=("bag", "bagc", "kapama", "closure", "zaste", "zastyo", "zast"),
        value_aliases=(
            ("шнурки", "Шнуровка"),
            ("шнурок", "Шнуровка"),
            ("шнур", "Шнуровка"),
            ("bagcik", "Шнуровка"),
            ("bağcık", "Шнуровка"),
            ("lace-up", "Шнуровка"),
            ("laces", "Шнуровка"),
            ("lace", "Шнуровка"),
            ("cirt cirt", "Липучка"),
            ("cırt cırt", "Липучка"),
            ("velcro", "Липучка"),
            ("липуч", "Липучка"),
            ("fermuar", "Молния"),
            ("zipper", "Молния"),
            ("zip", "Молния"),
            ("молн", "Молния"),
            ("tokali", "Пряжка"),
            ("tokalı", "Пряжка"),
            ("buckle", "Пряжка"),
            ("пряж", "Пряжка"),
            ("slip-on", "Без застёжки"),
            ("slip on", "Без застёжки"),
            ("gecirmeli", "Без застёжки"),
            ("geçirmeli", "Без застёжки"),
            ("без заст", "Без застёжки"),
            ("lastik", "Резинка"),
            ("elastic", "Резинка"),
            ("резин", "Резинка"),
        ),
        max_words=3,
    ),
    DynamicAttributeSpec(
        slug="toe-shape",
        name_ru="Форма носка",
        name_en="Toe Shape",
        sort_order=23,
        product_types=("shoes",),
        source_keys=("toe_shape", "toe-shape", "форма_носка", "burun_sekli", "burun_şekli"),
        source_key_contains=("burun", "toe", "носка"),
        value_aliases=(
            ("kруглый", "Круглый"),
            ("yuvarlak", "Круглый"),
            ("round", "Круглый"),
            ("sivri", "Заострённый"),
            ("pointed", "Заострённый"),
            ("kare", "Квадратный"),
            ("square", "Квадратный"),
            ("oval", "Овальный"),
        ),
        max_words=3,
    ),
    DynamicAttributeSpec(
        slug="accessory-type",
        name_ru="Тип аксессуара",
        name_en="Accessory Type",
        sort_order=60,
        product_types=("accessories",),
        source_keys=("accessory_type",),
        value_aliases=(
            ("пояс / ремень", "Пояс / ремень"),
            ("кемер", "Пояс / ремень"),
            ("кепка", "Кепка"),
            ("шапка", "Шапка"),
            ("кошелек", "Кошелек"),
            ("сумка", "Сумка"),
            ("очки", "Очки"),
            ("шаль", "Шаль"),
            ("платок", "Платок"),
        ),
        max_words=4,
    ),
    DynamicAttributeSpec(
        slug="case-material",
        name_ru="Материал корпуса",
        name_en="Case Material",
        sort_order=71,
        product_types=("accessories",),
        source_keys=("case_material", "case-material", "kasa_malzeme", "kasa_malzemesi"),
        source_key_contains=("case", "kasa"),
        max_words=4,
    ),
    DynamicAttributeSpec(
        slug="strap-material",
        name_ru="Материал ремешка",
        name_en="Strap Material",
        sort_order=72,
        product_types=("accessories",),
        source_keys=("strap_material", "strap-material", "kayis_malzeme", "kayış_malzeme", "kordon_malzeme"),
        source_key_contains=("strap", "kayis", "kayış", "kordon"),
        max_words=4,
    ),
)


def _iter_specs(product_type: str | None) -> Iterable[DynamicAttributeSpec]:
    normalized = normalize_product_type(product_type)
    for spec in ATTRIBUTE_SPECS:
        if normalized in spec.product_types:
            yield spec


def get_dynamic_attribute_spec(product_type: str | None, slug: str) -> DynamicAttributeSpec | None:
    normalized_slug = str(slug or "").strip().lower()
    for spec in _iter_specs(product_type):
        if spec.slug == normalized_slug:
            return spec
    return None


def is_facet_attribute_allowed(product_type: str | None, slug: str) -> bool:
    spec = get_dynamic_attribute_spec(product_type, slug)
    if spec:
        return spec.facet_enabled
    if product_type:
        return False
    return any(item.slug == str(slug or "").strip().lower() and item.facet_enabled for item in ATTRIBUTE_SPECS)


def canonicalize_dynamic_attribute_value(slug: str, value: str | None, product_type: str | None = None) -> str:
    raw_value = re.sub(r"\s+", " ", str(value or "").strip()).strip(" ,.;:-")
    if not raw_value:
        return ""
    spec = get_dynamic_attribute_spec(product_type, slug)
    aliases = spec.value_aliases if spec else next((item.value_aliases for item in ATTRIBUTE_SPECS if item.slug == slug), ())
    normalized = normalize_ascii_text(raw_value)
    for needle, canonical in aliases:
        if normalize_ascii_text(needle) in normalized:
            return canonical
    return raw_value[: (spec.max_length if spec else 100)]


def _is_safe_dynamic_attribute_value(spec: DynamicAttributeSpec, value: str) -> bool:
    if not value:
        return False
    compact = value.strip()
    if "http://" in compact.lower() or "https://" in compact.lower():
        return False
    if len(compact) > spec.max_length:
        return False
    if len(compact.split()) > spec.max_words:
        return False
    if compact.count(":") > 1:
        return False
    return True


def _extract_raw_attribute_value(attrs: dict[str, Any], spec: DynamicAttributeSpec) -> str:
    for key in spec.source_keys:
        value = attrs.get(key)
        if value:
            clean = str(value).strip()
            if clean:
                return clean

    if not spec.source_key_contains:
        return ""

    for raw_key, value in attrs.items():
        normalized_key = normalize_ascii_text(str(raw_key or "")).replace(" ", "_")
        if any(marker in normalized_key for marker in spec.source_key_contains):
            clean = str(value or "").strip()
            if clean:
                return clean
    return ""


def extract_dynamic_attribute_candidates(product_type: str | None, attrs: dict[str, Any]) -> list[ResolvedDynamicAttribute]:
    if not isinstance(attrs, dict):
        return []

    candidates: list[ResolvedDynamicAttribute] = []
    for spec in _iter_specs(product_type):
        if not spec.auto_apply:
            continue
        raw_value = _extract_raw_attribute_value(attrs, spec)
        canonical = canonicalize_dynamic_attribute_value(spec.slug, raw_value, product_type=product_type)
        if not _is_safe_dynamic_attribute_value(spec, canonical):
            continue
        candidates.append(
            ResolvedDynamicAttribute(
                slug=spec.slug,
                value=canonical,
                value_ru=canonical,
                value_en=None,
                name_ru=spec.name_ru,
                name_en=spec.name_en,
                sort_order=spec.sort_order,
                facet_enabled=spec.facet_enabled,
                display_enabled=spec.display_enabled,
            )
        )
    return candidates
