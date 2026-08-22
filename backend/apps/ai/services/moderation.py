"""Human-facing AI moderation workflow and product-change preview.

The preview is deliberately read-only and category-agnostic. It reads the
actual domain object selected by ``Product.domain_item`` and never changes the
application routing used by ``AIResultApplier``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.ai.models import AIApplicationStatus, AIProcessingStatus
from apps.ai.services.quality_checker import get_moderation_reasons
from apps.ai.services.semantic_validator import SemanticValidator
from apps.ai.services.size_inventory import (
    current_product_sizes,
    merge_confirmed_sizes,
    strip_size_inventory_sentences,
    supports_size_inventory,
)


MODERATION_REASON_LABELS = {
    "low_confidence": "Низкая уверенность в выбранной категории",
    "suspicious_price": "Подозрительно низкая цена во входных данных",
    "sensitive_content": "В описании найдена подозрительная формулировка",
    "short_description": "Описание содержит меньше 20 слов",
    "title_category_mismatch": "Название не соответствует категории товара",
    "title_identity_lost": "В названии потеряна модель или серия товара",
    "forbidden_attribute": "AI предложил атрибут, недопустимый для этого типа товара",
    "untranslated_attribute": "Атрибут содержит непереведённый турецкий текст",
    "ambiguous_variant_sizes": (
        "У товара есть варианты: размеры нужно привязать к конкретному варианту вручную"
    ),
    "unsupported_sizes": "Этот тип товара не поддерживает автоматическое применение размеров",
    "manual_review": "Результат вручную отправлен на проверку",
}


APPLICATION_LABELS = {
    AIApplicationStatus.UNKNOWN: "Нет надёжных данных (старый лог)",
    AIApplicationStatus.NOT_APPLIED: "Товар ещё не изменён",
    AIApplicationStatus.PARTIAL: "Безопасные поля применены частично",
    AIApplicationStatus.APPLIED: "Результат применён к товару",
    AIApplicationStatus.FAILED: "Ошибка при применении к товару",
}


@dataclass(frozen=True)
class PreviewRow:
    section: str
    label: str
    current: str
    proposed: str
    decision: str
    decision_label: str
    reason: str = ""


def _display(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, dict):
        return ", ".join(
            f"{key}: {_display(item)}" for key, item in value.items() if item not in (None, "")
        ) or "—"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value if item not in (None, "")) or "—"
    return str(value)


def _comparable(value: Any) -> str:
    return " ".join(_display(value).casefold().split())


def _translation(target: Any, locale: str):
    manager = getattr(target, "translations", None)
    if manager is None:
        return None
    try:
        return manager.filter(locale=locale).first()
    except Exception:
        return None


def _current_seo_value(target: Any, translation: Any, field: str):
    if translation is not None and hasattr(translation, field):
        value = getattr(translation, field, None)
        if value not in (None, ""):
            return value
    fallback_fields = {
        "meta_title": ("meta_title", "seo_title"),
        "meta_description": ("meta_description", "seo_description"),
        "meta_keywords": ("meta_keywords", "keywords"),
        "og_title": ("og_title",),
        "og_description": ("og_description",),
    }
    for candidate in fallback_fields.get(field, (field,)):
        value = getattr(target, candidate, None)
        if value not in (None, "", [], {}):
            return value
    return None


def _decision(
    current: Any,
    proposed: Any,
    *,
    blocked_reason: str = "",
    fill_empty_only: bool = False,
) -> tuple[str, str, str]:
    if blocked_reason:
        return "blocked", "Не будет применено", blocked_reason
    if proposed in (None, "", [], {}):
        return "empty", "AI не предложил значение", ""
    if fill_empty_only and current not in (None, ""):
        return "preserved", "Сохранится текущее значение", "Поле заполняется только если оно пустое"
    if _comparable(current) == _comparable(proposed):
        return "unchanged", "Без изменений", ""
    return "apply", "Будет изменено", ""


_DISPLAY_UNSET = object()


def _row(
    rows: list[PreviewRow],
    section: str,
    label: str,
    current: Any,
    proposed: Any,
    *,
    blocked_reason: str = "",
    fill_empty_only: bool = False,
    proposed_display: Any = _DISPLAY_UNSET,
) -> None:
    if proposed in (None, "", [], {}) and current in (None, "", [], {}):
        return
    decision, decision_label, reason = _decision(
        current,
        proposed,
        blocked_reason=blocked_reason,
        fill_empty_only=fill_empty_only,
    )
    rows.append(
        PreviewRow(
            section=section,
            label=label,
            current=_display(current),
            proposed=_display(
                proposed if proposed_display is _DISPLAY_UNSET else proposed_display
            ),
            decision=decision,
            decision_label=decision_label,
            reason=reason,
        )
    )


def _current_dynamic_attributes(target: Any) -> dict[str, Any]:
    manager = getattr(target, "dynamic_attributes", None)
    if manager is None:
        return {}
    try:
        return {
            str(item.attribute_key.slug or "").strip().lower().replace("_", "-"): (
                item.value_ru or item.value or item.value_en
            )
            for item in manager.select_related("attribute_key").all()
            if item.attribute_key_id and item.attribute_key
        }
    except Exception:
        return {}


def _book_rows(rows: list[PreviewRow], target: Any, attrs: dict[str, Any]) -> None:
    if getattr(target, "_domain_product_type", "") != "books":
        return
    mapping = (
        ("ISBN", "isbn", "isbn", False),
        ("Издательство", "publisher", "publisher", False),
        ("Тип обложки", "cover_type", "cover_type", True),
        ("Язык книги", "language", "language", True),
        ("Год издания", "publication_date", "publication_year", True),
    )
    for label, model_field, attr_key, fill_empty_only in mapping:
        current = getattr(target, model_field, None)
        if model_field == "publication_date" and current is not None:
            current = getattr(current, "year", current)
        _row(
            rows,
            "Поля книги",
            label,
            current,
            attrs.get(attr_key),
            fill_empty_only=fill_empty_only,
        )
    authors = attrs.get("authors")
    if authors and hasattr(target, "book_authors"):
        try:
            current_authors = [
                f"{first} {last}".strip()
                for first, last in target.book_authors.select_related("author").values_list(
                    "author__first_name", "author__last_name"
                )
            ]
        except Exception:
            current_authors = []
        _row(rows, "Поля книги", "Авторы", current_authors, authors)


def _jewelry_rows(rows: list[PreviewRow], target: Any, attrs: dict[str, Any]) -> None:
    if getattr(target, "_domain_product_type", "") != "jewelry":
        return
    labels = {
        "jewelry_type": "Тип украшения",
        "material": "Материал",
        "metal_purity": "Проба металла",
        "stone_type": "Тип камня",
        "carat_weight": "Вес камней (карат)",
        "gender": "Пол",
    }
    for field, label in labels.items():
        _row(rows, "Поля украшения", label, getattr(target, field, None), attrs.get(field))


def _medicine_rows(
    rows: list[PreviewRow],
    target: Any,
    attrs: dict[str, Any],
    translations: dict[str, Any],
) -> None:
    if getattr(target, "_domain_product_type", "") != "medicines":
        return
    model_labels = {
        "barcode": "Штрихкод",
        "atc_code": "ATC-код",
        "nfc_code": "NFC-код",
        "sgk_equivalent_code": "Код эквивалента SGK",
        "sgk_active_ingredient_code": "Код действующего вещества SGK",
        "sgk_public_no": "Публичный номер SGK",
    }
    for field, label in model_labels.items():
        _row(
            rows,
            "Поля лекарства",
            label,
            getattr(target, field, None),
            attrs.get(field),
            fill_empty_only=True,
        )

    translation_labels = {
        "indications": "Показания",
        "usage_instructions": "Способ применения",
        "side_effects": "Побочные эффекты",
        "contraindications": "Противопоказания",
        "storage_conditions": "Условия хранения",
        "administration_route": "Путь введения",
        "shelf_life": "Срок годности",
        "sgk_status": "Статус SGK",
        "prescription_type": "Тип рецепта",
        "special_notes": "Особые указания",
        "origin_country": "Страна происхождения",
        "dosage_form": "Лекарственная форма",
        "active_ingredient": "Действующее вещество",
        "volume": "Объём",
    }
    translations_data = attrs.get("translations_data") or {}
    for locale in ("ru", "en"):
        current_translation = translations.get(locale)
        proposed_translation = translations_data.get(locale) or {}
        for field, label in translation_labels.items():
            _row(
                rows,
                f"Лекарство {locale.upper()}",
                label,
                getattr(current_translation, field, None) if current_translation else None,
                proposed_translation.get(field),
            )


def build_change_preview(
    log,
    *,
    semantic_report=None,
) -> list[PreviewRow]:
    """Return the exact human-facing candidate fields for any product type."""
    product = log.product
    target = product.domain_item
    product_type = getattr(product, "product_type", None)
    attrs = merge_confirmed_sizes(
        log.extracted_attributes or {},
        log.input_data or {},
        product_type,
        allow_moderator_override=True,
    )
    seo = attrs.get("seo_translations") or {}
    seo_ru = seo.get("ru") or {}
    seo_en = seo.get("en") or attrs.get("seo_en") or {}
    translations = {
        "ru": _translation(target, "ru"),
        "en": _translation(target, "en"),
    }
    semantic_report = semantic_report or SemanticValidator().validate_log(log)
    rejected = semantic_report.rejected_fields
    title_reason_code = next(
        (
            reason
            for reason in semantic_report.reasons
            if reason in {"title_category_mismatch", "title_identity_lost"}
        ),
        "",
    )
    title_reason = MODERATION_REASON_LABELS.get(title_reason_code, title_reason_code)
    clean_size_prose = (
        strip_size_inventory_sentences
        if supports_size_inventory(product_type)
        else lambda value: value
    )
    rows: list[PreviewRow] = []

    current_category = getattr(target, "category", None) or product.category
    proposed_category = log.suggested_category
    confidence = log.category_confidence
    category_reason = ""
    category_changes = (
        proposed_category is not None
        and getattr(proposed_category, "pk", None) != getattr(current_category, "pk", None)
    )
    if category_changes and (confidence is None or confidence < 0.75):
        category_reason = "Категория применяется только при уверенности не ниже 75%"
    proposed_category_text = None
    if proposed_category is not None:
        confidence_text = f"{confidence:.0%}" if confidence is not None else "нет оценки"
        proposed_category_text = f"{proposed_category} ({confidence_text})"
    _row(
        rows,
        "Основные поля",
        "Категория",
        current_category,
        proposed_category,
        blocked_reason=category_reason,
        proposed_display=proposed_category_text,
    )

    ru = translations["ru"]
    en = translations["en"]
    _row(
        rows,
        "Контент RU",
        "Название",
        getattr(ru, "name", None) or getattr(target, "name", None) or product.name,
        seo_ru.get("generated_title") or log.generated_title,
        blocked_reason=title_reason,
    )
    _row(
        rows,
        "Контент RU",
        "Описание",
        getattr(ru, "description", None) or getattr(target, "description", None),
        clean_size_prose(seo_ru.get("generated_description") or log.generated_description),
    )
    _row(
        rows,
        "Контент EN",
        "Название",
        getattr(en, "name", None),
        seo_en.get("generated_title") or log.generated_title,
        blocked_reason=title_reason,
    )
    _row(
        rows,
        "Контент EN",
        "Описание",
        getattr(en, "description", None),
        clean_size_prose(seo_en.get("generated_description") or log.generated_description),
    )

    seo_fields = (
        ("SEO title", "meta_title", "meta_title", "generated_seo_title"),
        ("SEO description", "meta_description", "meta_description", "generated_seo_description"),
        ("Ключевые слова", "meta_keywords", "meta_keywords", "generated_keywords"),
        ("OG title", "og_title", "og_title", None),
        ("OG description", "og_description", "og_description", None),
    )
    for locale, translation, payload in (("RU", ru, seo_ru), ("EN", en, seo_en)):
        for label, model_field, payload_key, fallback_field in seo_fields:
            proposed = payload.get(payload_key)
            if model_field == "og_title" and proposed in (None, ""):
                proposed = payload.get("meta_title")
            if model_field == "og_description" and proposed in (None, ""):
                proposed = payload.get("meta_description")
            if proposed in (None, "") and fallback_field:
                proposed = getattr(log, fallback_field)
            if proposed in (None, "") and model_field == "og_title":
                proposed = log.generated_seo_title
            if proposed in (None, "") and model_field == "og_description":
                proposed = log.generated_seo_description
            if model_field in {"meta_description", "og_description"}:
                proposed = clean_size_prose(proposed)
            _row(
                rows,
                f"SEO {locale}",
                label,
                _current_seo_value(target, translation, model_field),
                proposed,
            )

    current_dynamic = _current_dynamic_attributes(target)
    for item in attrs.get("dynamic_attributes") or []:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "").strip().lower().replace("_", "-")
        if not slug:
            continue
        rejected_key = f"dynamic_attributes:{slug}"
        reason = ""
        if rejected_key in rejected:
            reason_code = next(
                (
                    code
                    for code in ("forbidden_attribute", "untranslated_attribute")
                    if code in semantic_report.reasons
                ),
                "forbidden_attribute",
            )
            reason = MODERATION_REASON_LABELS[reason_code]
        proposed = item.get("value_ru") or item.get("value") or item.get("value_en")
        _row(
            rows,
            "Динамические атрибуты",
            slug,
            current_dynamic.get(slug),
            proposed,
            blocked_reason=reason,
        )

    proposed_sizes = [row["size"] for row in attrs.get("sizes") or []]
    size_reason = ""
    if "sizes" in rejected:
        size_reason_code = next(
            (
                reason
                for reason in semantic_report.reasons
                if reason in {"ambiguous_variant_sizes", "unsupported_sizes"}
            ),
            "unsupported_sizes",
        )
        size_reason = MODERATION_REASON_LABELS[size_reason_code]
    _row(
        rows,
        "Размеры и наличие",
        "Доступные размеры",
        current_product_sizes(target),
        proposed_sizes,
        blocked_reason=size_reason,
    )

    _book_rows(rows, target, attrs)
    _jewelry_rows(rows, target, attrs)
    _medicine_rows(rows, target, attrs, translations)
    return rows


def get_moderation_reason_labels(log, *, semantic_report=None) -> list[str]:
    return [
        MODERATION_REASON_LABELS.get(reason, reason)
        for reason in get_moderation_reasons(log, semantic_report=semantic_report)
    ]


def get_workflow_title(log) -> tuple[str, str]:
    if log.status == AIProcessingStatus.PENDING:
        return "Ожидает запуска AI", "neutral"
    if log.status == AIProcessingStatus.PROCESSING:
        return "AI обрабатывает товар", "neutral"
    if log.status == AIProcessingStatus.FAILED:
        return "Обработка завершилась ошибкой", "danger"
    if log.status == AIProcessingStatus.REJECTED:
        return "Результат отклонён", "danger"
    if log.status == AIProcessingStatus.APPROVED:
        return "Результат применён к товару", "success"
    if log.status == AIProcessingStatus.MODERATION:
        if log.application_status == AIApplicationStatus.PARTIAL:
            return "Применено частично — требуется проверка", "warning"
        return "Требуется проверка модератора", "warning"
    return "Готово к проверке — товар ещё не изменён", "info"


def reject_log(log, *, user=None, notes: str = ""):
    """Reject a reviewable log and consistently close its queue item."""
    if log.status not in (AIProcessingStatus.COMPLETED, AIProcessingStatus.MODERATION):
        raise ValueError("Отклонить можно только завершённый результат или результат на модерации.")
    resolved_at = timezone.now()
    with transaction.atomic():
        log.status = AIProcessingStatus.REJECTED
        if user is not None:
            log.processed_by = user
        log.moderation_date = resolved_at
        if notes:
            log.moderation_notes = notes
        log.save(
            update_fields=[
                "status",
                "processed_by",
                "moderation_date",
                "moderation_notes",
                "updated_at",
            ]
        )
        task = getattr(log, "moderation_queue", None)
        if task and task.resolved_at is None:
            task.resolved_at = resolved_at
            task.save(update_fields=["resolved_at"])
    return log
