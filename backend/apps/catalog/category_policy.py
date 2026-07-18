"""Policy-driven contract for AI processing of any catalog category."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.catalog.attribute_specs import get_dynamic_attribute_spec


# Data, not validator branches. New category semantics are added here or in
# Category.external_data["semantic_policy"] without changing the engine.
CATEGORY_POLICY_OVERRIDES: dict[str, dict[str, Any]] = {
    "bed-bases": {
        "aliases": {
            "ru": ("основание кровати", "кроватное основание", "реечное основание"),
            "en": ("bed base", "slatted bed base"),
        },
    },
    "beds": {
        "aliases": {"ru": ("кровать",), "en": ("bed", "bed frame")},
    },
    "mattresses": {
        "aliases": {"ru": ("матрас",), "en": ("mattress",)},
    },
}


@dataclass(frozen=True)
class CategoryPolicy:
    category_id: int
    canonical_product_kind: str
    aliases: dict[str, tuple[str, ...]]
    allowed_dynamic_attributes: frozenset[str]
    immutable_fields: frozenset[str]
    ai_mutable_fields: frozenset[str]


def _lineage(category) -> list[Any]:
    rows, current, guard = [], category, 0
    while current is not None and guard < 20:
        rows.append(current)
        current = getattr(current, "parent", None)
        guard += 1
    return rows


def build_category_policy(category, product_type: str | None = None) -> CategoryPolicy | None:
    if category is None or not getattr(category, "slug", None):
        return None
    external_data = getattr(category, "external_data", {})
    external_data = external_data if isinstance(external_data, dict) else {}
    stored = external_data.get("semantic_policy") if isinstance(external_data.get("semantic_policy"), dict) else {}
    override = CATEGORY_POLICY_OVERRIDES.get(category.slug, {})

    aliases: dict[str, list[str]] = {"ru": [], "en": []}
    if getattr(category, "name", None):
        aliases["ru"].append(category.name)
    translation_manager = getattr(category, "translations", None)
    for translation in translation_manager.all() if translation_manager is not None else ():
        locale = str(translation.locale or "").split("-")[0]
        if locale in aliases and translation.name:
            aliases[locale].append(translation.name)
    for source in (override.get("aliases") or {}, stored.get("aliases") or {}):
        for locale, values in source.items():
            locale = str(locale).split("-")[0]
            if locale in aliases:
                aliases[locale].extend(str(value) for value in values if str(value).strip())

    allowed = set()
    for node in _lineage(category):
        key_manager = getattr(node, "global_attribute_keys", None)
        for key in key_manager.all() if key_manager is not None else ():
            if get_dynamic_attribute_spec(product_type, key.slug) is not None:
                allowed.add(key.slug)

    immutable = stored.get("immutable_fields") or (
        "category", "canonical_product_kind", "brand", "external_id", "price", "currency",
        "stock_quantity", "is_available",
    )
    mutable = stored.get("ai_mutable_fields") or (
        "title", "description", "seo", "dynamic_attributes", "translations",
    )
    return CategoryPolicy(
        category_id=getattr(category, "pk", 0) or 0,
        canonical_product_kind=str(stored.get("canonical_product_kind") or category.slug),
        aliases={locale: tuple(dict.fromkeys(values)) for locale, values in aliases.items()},
        allowed_dynamic_attributes=frozenset(allowed),
        immutable_fields=frozenset(immutable),
        ai_mutable_fields=frozenset(mutable),
    )
