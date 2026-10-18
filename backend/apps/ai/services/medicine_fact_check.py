"""Сверка фактов перевода лекарства с турецким исходником.

Проверяются только факты, ошибка в которых опасна и которые можно сравнить
без LLM: дозировки с единицами, МНН и цвет/тип рецепта. Поле с расхождением
помечается в medicine_translation_quality как неполное и уходит в модерацию.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

# Единицы TR/RU/EN → каноническое имя.
_UNIT_ALIASES = {
    "mg": "mg", "мг": "mg",
    "mcg": "mcg", "µg": "mcg", "μg": "mcg", "мкг": "mcg",
    "g": "g", "gr": "g", "г": "g",
    "ml": "ml", "мл": "ml",
    "iu": "iu", "ui": "iu", "ме": "iu",
    "mmol": "mmol", "ммоль": "mmol",
    "kg": "kg", "кг": "kg",
    "%": "%",
}
_UNIT_PATTERN = "|".join(
    sorted((re.escape(unit) for unit in _UNIT_ALIASES if unit != "%"), key=len, reverse=True)
)
# Число: с разделителем тысяч («1.000», «1 000») или десятичное («2,5»).
_NUMBER = r"[1-9]\d{0,2}(?:[ \u00a0.,]\d{3})+|\d+(?:[.,]\d+)?"
_DOSE_RE = re.compile(
    rf"(?<![\w.,])({_NUMBER})\s*({_UNIT_PATTERN})(?![^\W\d_])",
    re.IGNORECASE,
)
# Турецкий процент пишется перед числом: «%5», в RU/EN — после: «5%».
_PERCENT_RE = re.compile(r"%\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*%")

# Цвет/тип турецкого рецепта → обязательные основы в RU и EN.
_PRESCRIPTION_MARKERS = {
    "kısıtlanmış": ("огранич", "restrict"),
    "beyaz": ("бел", "white"),
    "kırmızı": ("красн", "red"),
    "yeşil": ("зел", "green"),
    "mor": ("фиолет", "purple"),
    "turuncu": ("оранж", "orange"),
}


def _normalize_number(raw: str) -> str:
    value = re.sub(r"[ \u00a0]", "", raw)
    if re.fullmatch(r"[1-9]\d{0,2}(?:[.,]\d{3})+", value):
        return re.sub(r"[.,]", "", value)
    value = value.replace(",", ".")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value or "0"


def extract_doses(text: Any) -> set[tuple[str, str]]:
    """Дозировки вида (число, единица) из текста на любом из трёх языков."""
    text = str(text or "")
    doses = {
        (_normalize_number(number), _UNIT_ALIASES[unit.lower()])
        for number, unit in _DOSE_RE.findall(text)
    }
    for prefix, suffix in _PERCENT_RE.findall(text):
        doses.add((_normalize_number(prefix or suffix), "%"))
    return doses


def doses_match(source: Any, translation: Any) -> bool:
    """В переводе те же дозировки, что в исходнике: ничего не потеряно и не добавлено."""
    return extract_doses(source) == extract_doses(translation)


def _latin_letters(value: Any, locale: str) -> str:
    text = str(value or "").lower()
    if locale == "ru":
        try:
            from transliterate import translit

            text = translit(text, "ru", reversed=True)
        except Exception:
            pass
    text = text.translate(str.maketrans("ıçğöşü", "icgosu"))
    return re.sub(r"[^a-z]", "", text)


def inn_matches(source: Any, translation: Any, locale: str) -> bool:
    """МНН в переводе — то же вещество (с поправкой на транслитерацию)."""
    source_letters = _latin_letters(source, "tr")
    translated_letters = _latin_letters(translation, locale)
    if not source_letters or not translated_letters:
        return True
    return SequenceMatcher(None, source_letters, translated_letters).ratio() >= 0.6


def prescription_matches(source: Any, translation: Any, locale: str) -> bool:
    """Цвет и ограничения турецкого рецепта сохранены в переводе."""
    source_text = str(source or "").lower()
    translated = str(translation or "").lower()
    if not source_text or not translated:
        return True
    index = 0 if locale == "ru" else 1
    for marker, stems in _PRESCRIPTION_MARKERS.items():
        if re.search(rf"\b{marker}\b", source_text) and stems[index] not in translated:
            return False
    return True


def check_medicine_short_fields(
    source: dict[str, Any],
    translations: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Проверка коротких полей: МНН, тип рецепта, объём/дозировка упаковки.

    Возвращает {field: {"complete": False, "fact_mismatch": [...]}} только для
    полей с расхождением.
    """
    checks = {
        "active_ingredient": inn_matches,
        "prescription_type": prescription_matches,
        "volume": lambda src, value, _locale: doses_match(src, value),
    }
    problems: dict[str, dict[str, Any]] = {}
    for field, check in checks.items():
        source_value = source.get(field)
        if not source_value:
            continue
        failed_locales = [
            locale
            for locale in ("ru", "en")
            if (translations.get(locale) or {}).get(field)
            and not check(source_value, translations[locale][field], locale)
        ]
        if failed_locales:
            problems[field] = {"complete": False, "fact_mismatch": failed_locales}
    return problems
