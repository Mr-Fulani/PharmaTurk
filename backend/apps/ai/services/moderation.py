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
from apps.ai.services.semantic_validator import SemanticValidator, medicine_paragraph_findings
from apps.ai.services.size_inventory import (
    current_product_sizes,
    merge_confirmed_sizes,
    strip_size_inventory_sentences,
    supports_size_inventory,
)
from apps.ai.services.medicine_fact_check import strip_proper_name_lines
from apps.catalog.product_semantics import looks_untranslated_turkish


MODERATION_REASON_LABELS = {
    "low_confidence": "Низкая уверенность в выбранной категории",
    "category_change_suggested": (
        "AI предлагает другую категорию; заданная категория не меняется автоматически"
    ),
    "suspicious_price": "Подозрительно низкая цена во входных данных",
    "sensitive_content": "В описании найдена подозрительная формулировка",
    "garbled_text": (
        "В тексте испорченные символы «�», слово из двух алфавитов, обрыв «...» или чужой вкус в описании "
        "(сбой ответа модели) — перезапустите AI или исправьте текст"
    ),
    "short_description": "Описание содержит меньше 20 слов",
    "description_meta_text": (
        "Описание лекарства рассуждает о данных («в исходных данных не указано», «см. в инструкции») — "
        "перезапустите AI или исправьте описание"
    ),
    "title_category_mismatch": "Название не соответствует категории товара",
    "title_identity_lost": "В названии потеряна модель или серия товара",
    "title_untranslated": "В названии остались турецкие слова или их транслитерация",
    "title_truncated": (
        "Название обрезано: в конце число без единицы («MOUNJARO 7» вместо «7,5 мг») — "
        "исправьте название по источнику"
    ),
    "title_source_translated": (
        "Название скопировано из исходника, уже переведённого прежней обработкой "
        "(кириллица): турецкого оригинала нет — исправьте название по источнику"
    ),
    "forbidden_attribute": "AI предложил атрибут, недопустимый для этого типа товара",
    "untranslated_attribute": "Атрибут содержит непереведённый турецкий текст",
    "incomplete_medicine_translation": (
        "Медицинский раздел переведён не полностью и не будет применён"
    ),
    "medicine_fact_mismatch": (
        "Дозировка, МНН или тип рецепта в переводе не совпадают с исходником"
    ),
    "untranslated_medicine_field": (
        "Русское поле лекарства содержит непереведённый турецкий текст"
    ),
    "medicine_paragraph_mismatch": (
        "Абзацы медицинского раздела похожи на чужой перевод (сдвиг или расхождение "
        "с исходником) — раздел не будет применён"
    ),
    "supplement_title_number_lost": (
        "В названии БАДа пропало число из названия источника (дозировка, «Omega 1000», «B12») — "
        "название не будет применено"
    ),
    "supplement_ingredient_mistranslated": (
        "В названии БАДа нет перевода вещества из словаря (supplement_glossary): модель перевела "
        "турецкое слово иначе — название не будет применено"
    ),
    "supplement_unsourced_number": (
        "В описании БАДа есть число, которого нет в источнике — описание не будет применено"
    ),
    "supplement_form_mismatch": (
        "В описании БАДа другая форма выпуска, чем в фасовке (капсулы вместо таблеток и т. п.) — "
        "описание не будет применено"
    ),
    "supplement_health_claim": (
        "В описании БАДа обещание лечения или профилактики болезней — описание не будет применено"
    ),
    "ambiguous_variant_sizes": (
        "У товара есть варианты: размеры нужно привязать к конкретному варианту вручную"
    ),
    "unsupported_sizes": "Этот тип товара не поддерживает автоматическое применение размеров",
    "manual_review": "Результат вручную отправлен на проверку",
}


APPLICATION_LABELS = {
    AIApplicationStatus.UNKNOWN: "Нет надёжных данных (старый лог)",
    AIApplicationStatus.NOT_APPLIED: "Товар ещё не изменён",
    AIApplicationStatus.PARTIAL: (
        "Разрешённые поля применены; заблокированные оставлены на проверке"
    ),
    AIApplicationStatus.APPLIED: "Результат применён к товару",
    AIApplicationStatus.FAILED: "Ошибка при применении к товару",
}


REJECTED_FIELD_LABELS = {
    "title": "название RU/EN",
    "sizes": "размеры и наличие",
}

MEDICINE_TRANSLATION_FIELD_LABELS = {
    "indications": "показания RU/EN",
    "usage_instructions": "способ применения RU/EN",
    "side_effects": "побочные эффекты RU/EN",
    "contraindications": "противопоказания RU/EN",
    "storage_conditions": "условия хранения RU/EN",
    "administration_route": "путь введения RU/EN",
    "shelf_life": "срок годности RU/EN",
    "sgk_status": "статус SGK RU/EN",
    "prescription_type": "тип рецепта RU/EN",
    "special_notes": "особые указания RU/EN",
    "origin_country": "страна происхождения RU/EN",
    "dosage_form": "лекарственная форма RU/EN",
    "active_ingredient": "действующее вещество RU/EN",
    "volume": "объём RU/EN",
}


# Причины section_paragraph_problems — для модератора.
PARAGRAPH_PROBLEM_LABELS = {
    "shifted": "перевод соседнего абзаца (сдвиг)",
    "number_mismatch": "числа не совпадают с исходником",
    "length_mismatch": "длина не совпадает с исходником",
    "ru_en_mismatch": "RU и EN расходятся",
    "concept_mismatch": "нет понятий исходника",
    "frequency_mismatch": "другая частота побочного эффекта",
    "heading_mismatch": "другой номер заголовка",
    "fact_mismatch": "дозировка не совпадает с исходником",
    "brand_token_missing": "потеряно название препарата",
    "ru_not_russian": "RU не переведён на русский",
    "en_has_cyrillic": "кириллица в EN",
    "too_short": "перевод намного короче исходника",
    "missing": "нет перевода",
    "paragraph_count_mismatch": "число абзацев перевода не совпадает с исходником",
}


def _number_ranges(numbers: list[int]) -> str:
    """[4, 7, 8, 9] → «4, 7–9»."""
    ranges: list[list[int]] = []
    for number in sorted(set(numbers)):
        if ranges and number == ranges[-1][1] + 1:
            ranges[-1][1] = number
        else:
            ranges.append([number, number])
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in ranges)


def describe_paragraph_findings(findings: list[dict[str, Any]]) -> str:
    """Абзацы одного раздела → «абзацы 4, 7–9 похожи на чужой перевод: сдвиг; числа…»."""
    numbers = [item["number"] for item in findings if item.get("number")]
    problems = list(dict.fromkeys(problem for item in findings for problem in item.get("problems") or ()))
    reasons = "; ".join(PARAGRAPH_PROBLEM_LABELS.get(problem, problem) for problem in problems)
    if not numbers:
        return reasons
    return f"абзац{'ы' if len(numbers) > 1 else ''} {_number_ranges(numbers)} похож{'и' if len(numbers) > 1 else ''} на чужой перевод: {reasons}"


def get_rejected_field_labels(fields: list[str] | set[str] | tuple[str, ...]) -> list[str]:
    """Translate internal field gates into compact moderator-facing labels."""
    labels: list[str] = []
    for field_name in fields:
        label = REJECTED_FIELD_LABELS.get(field_name)
        if label is None and field_name.startswith("medicine_translation:"):
            medicine_field = field_name.split(":", 1)[1]
            label = MEDICINE_TRANSLATION_FIELD_LABELS.get(
                medicine_field,
                f"медицинское поле «{medicine_field}» RU/EN",
            )
        if label is None and field_name.startswith("dynamic_attributes:"):
            label = f"атрибут «{field_name.split(':', 1)[1]}»"
        labels.append(label or field_name)
    return labels


def get_incomplete_medicine_field_messages(
    log,
    rejected_fields: list[str] | set[str] | tuple[str, ...],
    *,
    paragraph_findings: dict[str, list[dict[str, Any]]] | None = None,
) -> list[str]:
    """Explain missing medicine locales and confirm what happened to current data."""
    if getattr(getattr(log, "product", None), "product_type", None) != "medicines":
        return []
    if paragraph_findings is None:
        paragraph_findings = medicine_paragraph_findings(log)
    attrs = log.extracted_attributes if isinstance(log.extracted_attributes, dict) else {}
    translations_data = (
        attrs.get("translations_data")
        if isinstance(attrs.get("translations_data"), dict)
        else {}
    )
    quality = (
        attrs.get("medicine_translation_quality")
        if isinstance(attrs.get("medicine_translation_quality"), dict)
        else {}
    )
    target = getattr(log.product, "domain_item", None)
    current_translations = {}
    manager = getattr(target, "translations", None)
    if manager is not None:
        for locale in ("ru", "en"):
            current_translations[locale] = manager.filter(locale=locale).first()

    messages = []
    for rejected_field in sorted(rejected_fields):
        if not rejected_field.startswith("medicine_translation:"):
            continue
        field_name = rejected_field.split(":", 1)[1]
        details = quality.get(field_name) if isinstance(quality, dict) else {}
        details = details if isinstance(details, dict) else {}
        missing = []
        incomplete = []
        existing = []
        for locale in ("ru", "en"):
            candidate = str(
                ((translations_data.get(locale) or {}).get(field_name) or "")
            ).strip()
            complete = details.get(f"{locale}_complete")
            if not candidate:
                missing.append(locale.upper())
            elif complete is False:
                incomplete.append(locale.upper())
            current_translation = current_translations.get(locale)
            if current_translation is not None and str(
                getattr(current_translation, field_name, "") or ""
            ).strip():
                existing.append(locale.upper())

        label = MEDICINE_TRANSLATION_FIELD_LABELS.get(
            field_name,
            field_name,
        ).removesuffix(" RU/EN")
        problems = []
        if missing:
            problems.append("AI не создал " + "/".join(missing))
        if incomplete:
            problems.append("AI создал неполный " + "/".join(incomplete))
        if field_name in paragraph_findings:
            problems.append(describe_paragraph_findings(paragraph_findings[field_name]))
        problem_text = "; ".join(problems) or "полнота RU/EN не подтверждена"
        preserved_text = (
            " Текущие " + "/".join(existing) + " товара сохранены без изменений."
            if existing
            else ""
        )
        advice = (
            " Исправьте эти абзацы RU и EN в форме лога; если перевод верный, выберите "
            "«Проверено — применить RU и EN как есть»; либо оставьте текущий раздел товара "
            "или перезапустите AI."
            if field_name in paragraph_findings
            else ""
        )
        messages.append(
            f"Для «{label}»: {problem_text}. Раздел не применён ни в одном языке."
            f"{preserved_text}{advice}"
        )
    return messages


def get_unblock_actions(
    reasons: list[str] | set[str] | tuple[str, ...],
    rejected_fields: list[str] | set[str] | tuple[str, ...],
) -> list[str]:
    """Что сделать модератору, чтобы снять каждую оставшуюся блокировку."""
    reasons = set(reasons or ())
    rejected = set(rejected_fields or ())
    actions = []
    if "title" in rejected:
        actions.append(
            "Название: исправьте «Название (RU)» и «Заголовок (EN)» либо, если название "
            "верное, отметьте «Название проверено модератором» и снова нажмите "
            "«Сохранить и применить»."
        )
    if "description" in rejected:
        actions.append(
            "Описание БАДа: уберите из «Описания» RU/EN число, которого нет в источнике, или "
            "обещание лечения/профилактики и снова нажмите «Сохранить и применить»."
        )
    medicine_fields = sorted(
        field_name.split(":", 1)[1]
        for field_name in rejected
        if field_name.startswith("medicine_translation:")
    )
    if medicine_fields:
        labels = ", ".join(
            MEDICINE_TRANSLATION_FIELD_LABELS.get(field_name, field_name).removesuffix(" RU/EN")
            for field_name in medicine_fields
        )
        actions.append(
            f"Медицинские разделы ({labels}): исправьте RU/EN в форме лога или, если перевод "
            "верный, выберите действие «Проверено — применить RU и EN как есть»; "
            "чтобы оставить раздел товара прежним — «Не менять этот раздел товара»."
        )
    if "category_change_suggested" in reasons:
        actions.append(
            "Категория: AI предлагает другую. Если текущая категория товара верна, очистите "
            "поле «Предложенная категория» в логе; если нет — смените категорию в карточке товара."
        )
    if "untranslated_attribute" in reasons:
        actions.append(
            "Атрибуты: переведите или удалите непереведённое значение в блоке "
            "«Извлечённые атрибуты (JSON)»."
        )
    if "sizes" in rejected:
        actions.append(
            "Размеры: очистите поле «Доступные размеры» и укажите размеры в вариантах товара вручную."
        )
    return actions


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
    preserved_reason: str = "",
    fill_empty_only: bool = False,
) -> tuple[str, str, str]:
    if blocked_reason:
        return "blocked", "Не будет применено", blocked_reason
    if preserved_reason:
        return "preserved", "Сохранится текущее значение", preserved_reason
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
    preserved_reason: str = "",
    fill_empty_only: bool = False,
    proposed_display: Any = _DISPLAY_UNSET,
    note: str = "",
) -> None:
    if proposed in (None, "", [], {}) and current in (None, "", [], {}):
        return
    decision, decision_label, reason = _decision(
        current,
        proposed,
        blocked_reason=blocked_reason,
        preserved_reason=preserved_reason,
        fill_empty_only=fill_empty_only,
    )
    if note and not reason:
        reason = note
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
    paragraph_findings: dict[str, list[dict[str, Any]]],
    reviewed_fields: set[str] = frozenset(),
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
        "dosage_form": "Лекарственная форма (исходное значение)",
        "active_ingredient": "Действующее вещество (исходное значение)",
        "volume": "Объём/количество (исходное значение)",
        "origin_country": "Происхождение (исходное значение)",
        "administration_route": "Путь введения (исходное значение)",
        "shelf_life": "Срок годности (исходное значение)",
        "storage_conditions": "Хранение (исходное значение)",
        "sgk_status": "Статус SGK (исходное значение)",
        "prescription_type": "Тип рецепта (исходное значение)",
        "special_notes": "Особые указания (исходное значение)",
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
    quality = attrs.get("medicine_translation_quality") or {}
    moderator_decisions = attrs.get("medicine_moderator_decisions") or {}
    for locale in ("ru", "en"):
        current_translation = translations.get(locale)
        proposed_translation = translations_data.get(locale) or {}
        for field, label in translation_labels.items():
            proposed = proposed_translation.get(field)
            blocked_reason = ""
            preserved_reason = ""
            quality_note = ""
            if moderator_decisions.get(field) == "keep_current":
                preserved_reason = "Модератор выбрал «Оставить текущее значение товара»"
            preserved_locales = attrs.get("medicine_moderator_preserved_locales") or {}
            if locale in (preserved_locales.get(field) or []):
                preserved_reason = (
                    f"Использовано текущее значение {locale.upper()} товара; "
                    "AI не создал этот язык"
                )
            details = quality.get(field) if isinstance(quality, dict) else None
            reviewed = f"medicine_translation:{field}" in reviewed_fields
            if reviewed and not preserved_reason:
                quality_note = "Проверено модератором — применится как есть"
            elif isinstance(details, dict) and not preserved_reason:
                quality_note = (
                    f"Источник: {details.get('source_length', 0)} симв.; "
                    f"RU: {details.get('ru_length', 0)}; EN: {details.get('en_length', 0)}"
                )
                if not details.get("complete", False):
                    blocked_reason = (
                        "Полнота перевода не подтверждена; поле оставлено для проверки"
                    )
            if (
                locale == "ru"
                and not preserved_reason
                and not reviewed
                and looks_untranslated_turkish(strip_proper_name_lines(proposed))
            ):
                blocked_reason = "Поле содержит непереведённый турецкий текст"
            if field in paragraph_findings and not preserved_reason:
                description = describe_paragraph_findings(paragraph_findings[field])
                # Не capitalize(): он опустил бы «RU и EN» в «ru и en».
                blocked_reason = description[:1].upper() + description[1:] + " — раздел не будет применён"
            _row(
                rows,
                f"Лекарство {locale.upper()}",
                label,
                getattr(current_translation, field, None) if current_translation else None,
                proposed,
                blocked_reason=blocked_reason,
                preserved_reason=preserved_reason,
                note=quality_note,
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
    title_reason = ""
    title_note = ""
    if "title" in rejected:
        title_reason_code = next(
            (reason for reason in semantic_report.reasons if reason.startswith("title_")),
            "",
        )
        title_reason = (
            MODERATION_REASON_LABELS.get(title_reason_code, title_reason_code)
            or "Название не прошло проверку"
        )
    elif "title" in semantic_report.moderator_reviewed_fields:
        title_note = "Проверено модератором — применится как есть"
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
    if category_changes and current_category is not None:
        category_reason = "Заданная категория не меняется автоматически — смените вручную"
    elif category_changes and (confidence is None or confidence < 0.75):
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
        note=title_note,
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
        note=title_note,
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
    _medicine_rows(
        rows,
        target,
        attrs,
        translations,
        semantic_report.paragraph_findings,
        semantic_report.moderator_reviewed_fields,
    )
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
        if log.application_status == AIApplicationStatus.UNKNOWN:
            return "Одобрено — применение не подтверждено (старый лог)", "warning"
        if log.application_status == AIApplicationStatus.NOT_APPLIED:
            return "Одобрено — товар ещё не изменён", "warning"
        if log.application_status == AIApplicationStatus.FAILED:
            return "Одобрено, но применение завершилось ошибкой", "danger"
        return "Результат применён к товару", "success"
    if log.status == AIProcessingStatus.MODERATION:
        if log.application_status == AIApplicationStatus.PARTIAL:
            if (log.application_report or {}).get("product_updated") is False:
                return "Товар не изменён — требуется решение по полям", "warning"
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
