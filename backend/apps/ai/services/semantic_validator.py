"""Universal field-level semantic validation before applying AI output."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from apps.catalog.attribute_specs import get_dynamic_attribute_spec
from apps.catalog.category_policy import CATEGORY_POLICY_OVERRIDES, build_category_policy
from apps.catalog.product_semantics import looks_untranslated_turkish


@dataclass
class SemanticValidationReport:
    rejected_fields: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)
    canonical_product_kind: str = ""

    @property
    def needs_moderation(self) -> bool:
        return bool(self.reasons)


def _normalized(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or "")).casefold()
    return re.sub(r"[^a-zа-яё0-9]+", " ", text).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalized(phrase)
    return (
        bool(normalized_phrase)
        and re.search(rf"(?:^|\s){re.escape(normalized_phrase)}(?:$|\s)", text) is not None
    )


def _identity_tokens(value: Any) -> set[str]:
    # Stable model/series tokens, not ordinary title words.
    return {
        token.upper()
        for token in re.findall(r"[A-Za-z0-9ÅÄÖÜ][A-Za-z0-9ÅÄÖÜ/_-]{2,}", str(value or ""))
        if (
            any(char.isdigit() for char in token)
            or "/" in token
            or (len(token) >= 3 and token == token.upper())
        )
    }


class CategorySemanticIndex:
    """In-memory category policy index for bulk semantic validation.

    Request-time validation can keep using the lazy database path. Management
    commands that validate many products should build this index once and
    reuse it to avoid loading the complete category tree for every product.
    """

    def __init__(self, categories: Iterable[Any]):
        rows = list(categories)
        self._categories = {
            category.pk: category for category in rows if getattr(category, "pk", None) is not None
        }
        self._active_ids = {
            category.pk
            for category in rows
            if getattr(category, "pk", None) is not None and getattr(category, "is_active", False)
        }
        # Link parents to the already loaded objects. This makes lineage walks
        # in build_category_policy query-free regardless of tree depth.
        for category in rows:
            parent_id = getattr(category, "parent_id", None)
            if parent_id in self._categories:
                category._state.fields_cache["parent"] = self._categories[parent_id]
            elif parent_id is None:
                category._state.fields_cache["parent"] = None

        self._ancestor_cache: dict[int, frozenset[int]] = {}
        self._policy_cache: dict[tuple[int, str], Any] = {}
        self._alias_cache: dict[str, tuple[tuple[int, str, str], ...]] = {}

    @classmethod
    def from_database(cls) -> "CategorySemanticIndex":
        from apps.catalog.models import Category

        categories = Category.objects.all().prefetch_related(
            "translations",
            "global_attribute_keys",
        )
        return cls(categories)

    def policy_for(self, category: Any, product_type: str | None = None):
        category_id = getattr(category, "pk", None)
        indexed_category = self._categories.get(category_id)
        if indexed_category is None:
            return build_category_policy(category, product_type)
        cache_key = (category_id, str(product_type or ""))
        if cache_key not in self._policy_cache:
            self._policy_cache[cache_key] = build_category_policy(
                indexed_category,
                product_type,
            )
        return self._policy_cache[cache_key]

    def longest_conflicting_match(
        self,
        current_category: Any,
        title_text: str,
        locale: str,
        own_match: int,
    ) -> str:
        best = self._configured_override_match(
            current_category,
            title_text,
            locale,
            own_match,
        )
        current_id = getattr(current_category, "pk", None)
        if current_id is None:
            return best

        current_lineage_ids = self._ancestor_ids(current_id)
        for candidate_id, alias, normalized_alias in self._aliases(locale):
            if candidate_id in current_lineage_ids:
                continue
            # A more specific descendant is compatible with the current kind.
            if current_id in self._ancestor_ids(candidate_id):
                continue
            if len(normalized_alias) <= own_match or len(normalized_alias) <= len(best):
                continue
            if _contains_phrase(title_text, alias):
                best = normalized_alias
        return best

    def _ancestor_ids(self, category_id: int) -> frozenset[int]:
        if category_id in self._ancestor_cache:
            return self._ancestor_cache[category_id]
        result: set[int] = set()
        current_id: int | None = category_id
        guard = 0
        while current_id is not None and current_id not in result and guard < 20:
            result.add(current_id)
            current = self._categories.get(current_id)
            current_id = getattr(current, "parent_id", None) if current is not None else None
            guard += 1
        frozen = frozenset(result)
        self._ancestor_cache[category_id] = frozen
        return frozen

    def _aliases(self, locale: str) -> tuple[tuple[int, str, str], ...]:
        if locale not in self._alias_cache:
            rows: list[tuple[int, str, str]] = []
            for category_id in self._active_ids:
                category = self._categories[category_id]
                policy = self.policy_for(category)
                if policy is None:
                    continue
                for alias in policy.aliases.get(locale, ()):
                    normalized_alias = _normalized(alias)
                    if normalized_alias:
                        rows.append((category_id, alias, normalized_alias))
            self._alias_cache[locale] = tuple(rows)
        return self._alias_cache[locale]

    @staticmethod
    def _configured_override_match(
        current_category: Any,
        title_text: str,
        locale: str,
        own_match: int,
    ) -> str:
        best = ""
        current_slug = getattr(current_category, "slug", "")
        for canonical_kind, config in CATEGORY_POLICY_OVERRIDES.items():
            if canonical_kind == current_slug:
                continue
            for alias in (config.get("aliases") or {}).get(locale, ()):
                normalized_alias = _normalized(alias)
                if len(normalized_alias) > own_match and len(normalized_alias) > len(best):
                    if _contains_phrase(title_text, alias):
                        best = normalized_alias
        return best


class SemanticValidator:
    def __init__(self, category_index: CategorySemanticIndex | None = None):
        self.category_index = category_index

    @classmethod
    def with_preloaded_categories(cls) -> "SemanticValidator":
        return cls(category_index=CategorySemanticIndex.from_database())

    def validate_log(self, log) -> SemanticValidationReport:
        product = getattr(log, "product", None)
        if product is None:
            return SemanticValidationReport()
        attrs = getattr(log, "extracted_attributes", None) or {}
        translations = (
            attrs.get("seo_translations") if isinstance(attrs.get("seo_translations"), dict) else {}
        )
        return self.validate(
            product,
            generated_titles={
                "ru": getattr(log, "generated_title", ""),
                "en": (translations.get("en") or {}).get("generated_title", ""),
            },
            dynamic_attributes=attrs.get("dynamic_attributes") or [],
        )

    def validate(
        self,
        product,
        *,
        generated_titles: dict[str, Any],
        dynamic_attributes: list[dict[str, Any]],
    ) -> SemanticValidationReport:
        category = getattr(product, "category", None)
        product_type = getattr(product, "product_type", None)
        policy = (
            self.category_index.policy_for(category, product_type)
            if self.category_index is not None
            else build_category_policy(category, product_type)
        )
        report = SemanticValidationReport(
            canonical_product_kind=policy.canonical_product_kind if policy else ""
        )
        if policy is None:
            return report

        original_tokens = _identity_tokens(getattr(product, "name", ""))
        for locale, title in generated_titles.items():
            if not str(title or "").strip():
                continue
            title_text = _normalized(title)
            own_aliases = policy.aliases.get(locale, ())
            own_match = max(
                (
                    len(_normalized(alias))
                    for alias in own_aliases
                    if _contains_phrase(title_text, alias)
                ),
                default=0,
            )
            conflicting_match = self._longest_conflicting_category_match(
                category,
                title_text,
                locale,
                own_match,
            )
            if conflicting_match:
                report.rejected_fields.add("title")
                report.reasons.append("title_category_mismatch")
                break
            if (
                locale == "ru"
                and original_tokens
                and not original_tokens.issubset(_identity_tokens(title))
            ):
                report.rejected_fields.add("title")
                report.reasons.append("title_identity_lost")
                break

        for row in dynamic_attributes:
            if not isinstance(row, dict):
                continue
            slug = str(row.get("slug") or "").strip().lower()
            if (
                not slug
                or (product_type and get_dynamic_attribute_spec(product_type, slug) is None)
                or (
                    policy.allowed_dynamic_attributes
                    and slug not in policy.allowed_dynamic_attributes
                )
            ):
                report.rejected_fields.add(f"dynamic_attributes:{slug or 'unknown'}")
                report.reasons.append("forbidden_attribute")
            if looks_untranslated_turkish(row.get("value_ru")) or looks_untranslated_turkish(
                row.get("value_en")
            ):
                report.rejected_fields.add(f"dynamic_attributes:{slug or 'unknown'}")
                report.reasons.append("untranslated_attribute")

        report.reasons = list(dict.fromkeys(report.reasons))
        return report

    def _longest_conflicting_category_match(
        self,
        current_category,
        title_text: str,
        locale: str,
        own_match: int,
    ) -> str:
        if self.category_index is not None:
            return self.category_index.longest_conflicting_match(
                current_category,
                title_text,
                locale,
                own_match,
            )

        from apps.catalog.models import Category

        current_lineage_ids = set()
        node = current_category
        while node is not None:
            node_pk = getattr(node, "pk", None)
            if node_pk is not None:
                current_lineage_ids.add(node_pk)
            node = getattr(node, "parent", None)

        best = ""
        # Configured semantic kinds also participate when the corresponding
        # catalog category has not been created in this particular database.
        for canonical_kind, config in CATEGORY_POLICY_OVERRIDES.items():
            if canonical_kind == current_category.slug:
                continue
            for alias in (config.get("aliases") or {}).get(locale, ()):
                normalized_alias = _normalized(alias)
                if len(normalized_alias) > own_match and len(normalized_alias) > len(best):
                    if _contains_phrase(title_text, alias):
                        best = normalized_alias

        # Lightweight test/detached objects still receive configured policy
        # validation without requiring a database identity.
        if not getattr(current_category, "pk", None):
            return best

        queryset = (
            Category.objects.filter(is_active=True)
            .select_related("parent")
            .prefetch_related("translations", "global_attribute_keys")
        )
        for candidate in queryset:
            if candidate.pk in current_lineage_ids:
                continue
            # A more specific descendant is compatible with the current kind.
            ancestor = candidate.parent
            is_descendant = False
            while ancestor is not None:
                if ancestor.pk == current_category.pk:
                    is_descendant = True
                    break
                ancestor = ancestor.parent
            if is_descendant:
                continue
            candidate_policy = build_category_policy(candidate)
            if candidate_policy is None:
                continue
            for alias in candidate_policy.aliases.get(locale, ()):
                normalized_alias = _normalized(alias)
                if len(normalized_alias) <= own_match or len(normalized_alias) <= len(best):
                    continue
                if _contains_phrase(title_text, alias):
                    best = normalized_alias
        return best
