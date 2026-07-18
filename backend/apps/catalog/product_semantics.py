"""Проверки согласованности AI-контента с канонической категорией товара."""

from __future__ import annotations

import re
from typing import Any


CATEGORY_TITLE_RULES = {
    "bed-bases": {
        "ru": (r"\bосновани[ея]\s+(?:для\s+)?кроват", r"\bкроватн(?:ое|ая)\s+основан"),
        "en": (r"\bbed\s+base\b", r"\bslatted\s+(?:bed\s+)?base\b"),
    },
}


def title_matches_category(category_slug: str, title: Any, locale: str = "ru") -> bool:
    """Не ограничивать неизвестные категории; проверять только описанные правила."""
    rules = CATEGORY_TITLE_RULES.get(str(category_slug or "").strip())
    if not rules:
        return True
    patterns = rules.get(str(locale or "ru").split("-")[0]) or ()
    text = re.sub(r"<[^>]+>", " ", str(title or "")).strip().lower()
    return bool(text) and any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def looks_untranslated_turkish(value: Any) -> bool:
    text = re.sub(r"<[^>]+>", " ", str(value or "")).strip().lower()
    if not text:
        return False
    if re.search(r"[çğıöşü]", text):
        return True
    tokens = set(re.findall(r"[a-z]+", text))
    markers = {
        "karyola", "yatak", "genislik", "yukseklik", "uzunluk", "malzeme",
        "kisilik", "cekmece", "sunta", "masif", "kanepe", "baza",
    }
    return len(tokens.intersection(markers)) >= 2
