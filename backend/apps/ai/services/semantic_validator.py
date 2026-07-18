"""Universal field-level semantic validation before applying AI output."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

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
    return bool(normalized_phrase) and re.search(
        rf"(?:^|\s){re.escape(normalized_phrase)}(?:$|\s)", text
    ) is not None


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


class SemanticValidator:
    def validate_log(self, log) -> SemanticValidationReport:
        product = getattr(log, "product", None)
        if product is None:
            return SemanticValidationReport()
        attrs = getattr(log, "extracted_attributes", None) or {}
        translations = attrs.get("seo_translations") if isinstance(attrs.get("seo_translations"), dict) else {}
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
        policy = build_category_policy(category, product_type)
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
            own_match = max((len(_normalized(alias)) for alias in own_aliases if _contains_phrase(title_text, alias)), default=0)
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
            if locale == "ru" and original_tokens and not original_tokens.issubset(_identity_tokens(title)):
                report.rejected_fields.add("title")
                report.reasons.append("title_identity_lost")
                break

        for row in dynamic_attributes:
            if not isinstance(row, dict):
                continue
            slug = str(row.get("slug") or "").strip().lower()
            if (
                not slug
                or (
                    product_type
                    and get_dynamic_attribute_spec(product_type, slug) is None
                )
                or (
                    policy.allowed_dynamic_attributes
                    and slug not in policy.allowed_dynamic_attributes
                )
            ):
                report.rejected_fields.add(f"dynamic_attributes:{slug or 'unknown'}")
                report.reasons.append("forbidden_attribute")
            if looks_untranslated_turkish(row.get("value_ru")) or looks_untranslated_turkish(row.get("value_en")):
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

        queryset = Category.objects.filter(is_active=True).select_related("parent").prefetch_related(
            "translations", "global_attribute_keys"
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
