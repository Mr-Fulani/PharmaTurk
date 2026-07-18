"""Языковые проверки контента товара."""

from __future__ import annotations

import re
from typing import Any


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
