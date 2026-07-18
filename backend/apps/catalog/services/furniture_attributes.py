"""Детерминированная нормализация сырых характеристик мебели для витрины."""

from __future__ import annotations

import re
from html import unescape
from typing import Any

from django.contrib.contenttypes.models import ContentType

from apps.catalog.attribute_specs import get_dynamic_attribute_spec
from apps.catalog.models import (
    FurnitureProduct,
    GlobalAttributeKey,
    GlobalAttributeKeyTranslation,
    ProductAttributeValue,
)


FURNITURE_TYPE_ALIASES = {
    "cift-kisilik-baza": ("Двуспальное основание кровати", "Double bed base"),
    "tek-kisilik-baza": ("Односпальное основание кровати", "Single bed base"),
    "baza": ("Основание кровати", "Bed base"),
    "karyola": ("Кровать", "Bed frame"),
    "yatakli-kanepe": ("Диван-кровать", "Sofa bed"),
}

DIMENSION_LABELS = {
    "uzunluk": "length",
    "genislik": "width",
    "yukseklik": "height",
    "derinlik": "depth",
    "yatak-uzunlugu": "mattress-length",
    "yatak-genisligi": "mattress-width",
    "karyola-basligi-yuksekligi": "headboard-height",
    "karyola-ayak-ucu-yuksekligi": "footboard-height",
}

MATERIAL_ALIASES = (
    ("mdf", "МДФ", "MDF"),
    ("sunta", "ДСП", "Particleboard"),
    ("masif cam", "массив сосны", "solid pine"),
    ("celik", "сталь", "steel"),
    ("plastik", "пластик", "plastic"),
    ("polyester", "полиэстер", "polyester"),
)


def _ascii_key(value: Any) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).strip().lower()
    text = text.translate(str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"}))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _dimension_rows(raw: Any) -> list[tuple[str, str, str]]:
    text = str(raw or "")
    parts = re.findall(r"<p[^>]*>(.*?)</p>", text, flags=re.IGNORECASE | re.DOTALL)
    if not parts:
        parts = re.split(r"[;\n]+", text)
    rows = []
    for part in parts:
        plain = unescape(re.sub(r"<[^>]+>", " ", part)).strip()
        if ":" not in plain:
            continue
        label, value = (item.strip() for item in plain.split(":", 1))
        slug = DIMENSION_LABELS.get(_ascii_key(label))
        match = re.search(r"-?\d+(?:[.,]\d+)?\s*(?:cm|mm|m)\b", value, flags=re.IGNORECASE)
        if not slug or not match:
            continue
        normalized = re.sub(r"\s+", " ", match.group(0)).replace(",", ".")
        ru_value = re.sub(r"\bcm\b", "см", normalized, flags=re.IGNORECASE)
        en_value = re.sub(r"\bсм\b", "cm", normalized, flags=re.IGNORECASE)
        rows.append((slug, ru_value, en_value))
    return rows


def _localized_furniture_type(raw: Any) -> tuple[str, str] | None:
    key = _ascii_key(raw)
    if not key:
        return None
    if key in FURNITURE_TYPE_ALIASES:
        return FURNITURE_TYPE_ALIASES[key]
    for alias, translations in FURNITURE_TYPE_ALIASES.items():
        if alias in key:
            return translations
    return None


def _localized_material_summary(raw: Any) -> tuple[str, str] | None:
    normalized = _ascii_key(raw).replace("-", " ")
    if not normalized:
        return None
    ru_values, en_values = [], []
    for needle, ru, en in MATERIAL_ALIASES:
        if needle in normalized and ru not in ru_values:
            ru_values.append(ru)
            en_values.append(en)
    if not ru_values:
        return None
    return ", ".join(ru_values), ", ".join(en_values)


def build_furniture_dynamic_attributes(raw_attributes: dict[str, Any]) -> list[dict[str, str]]:
    """Вернуть только подтверждённые и локализованные shopper-facing значения."""
    attrs = raw_attributes if isinstance(raw_attributes, dict) else {}
    rows: list[dict[str, str]] = []
    furniture_type = _localized_furniture_type(attrs.get("furniture_type"))
    if furniture_type:
        rows.append({"slug": "furniture-type", "value": furniture_type[0], "value_ru": furniture_type[0], "value_en": furniture_type[1]})
    material = _localized_material_summary(attrs.get("material"))
    if material:
        rows.append({"slug": "material", "value": material[0], "value_ru": material[0], "value_en": material[1]})
    for slug, value_ru, value_en in _dimension_rows(attrs.get("dimensions")):
        rows.append({"slug": slug, "value": value_ru, "value_ru": value_ru, "value_en": value_en})
    return rows


def sync_furniture_dynamic_attributes(
    product: FurnitureProduct,
    raw_attributes: dict[str, Any],
    *,
    overwrite: bool = False,
) -> int:
    """Идемпотентно создать локализованные характеристики, сохраняя ручные значения."""
    rows = build_furniture_dynamic_attributes(raw_attributes)
    if not rows:
        return 0
    content_type = ContentType.objects.get_for_model(product)
    changed = 0
    for row in rows:
        spec = get_dynamic_attribute_spec("furniture", row["slug"])
        if spec is None:
            continue
        key, _ = GlobalAttributeKey.objects.get_or_create(slug=spec.slug, defaults={"sort_order": spec.sort_order})
        for locale, name in (("ru", spec.name_ru), ("en", spec.name_en)):
            GlobalAttributeKeyTranslation.objects.get_or_create(key_obj=key, locale=locale, defaults={"name": name})
        if product.category_id:
            key.categories.add(product.category_id)
        current = ProductAttributeValue.objects.filter(
            content_type=content_type,
            object_id=product.pk,
            attribute_key=key,
        ).first()
        if current and not overwrite:
            continue
        if current is None:
            ProductAttributeValue.objects.create(
                content_object=product,
                attribute_key=key,
                value=row["value"][:500],
                value_ru=row["value_ru"][:500],
                value_en=row["value_en"][:500],
                sort_order=spec.sort_order,
            )
            changed += 1
            continue
        updates = []
        for field in ("value", "value_ru", "value_en"):
            value = row[field][:500]
            if getattr(current, field) != value:
                setattr(current, field, value)
                updates.append(field)
        if current.sort_order != spec.sort_order:
            current.sort_order = spec.sort_order
            updates.append("sort_order")
        if updates:
            current.save(update_fields=updates)
            changed += 1
    return changed
