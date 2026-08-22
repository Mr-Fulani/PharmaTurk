"""Языковые проверки контента товара."""

from __future__ import annotations

import re
from typing import Any


def looks_untranslated_turkish(value: Any) -> bool:
    text = re.sub(r"<[^>]+>", " ", str(value or "")).strip()
    if not text:
        return False
    # Official abbreviations and brand names may legitimately retain Turkish
    # letters inside an otherwise complete RU/EN translation.  Inspect the
    # surrounding language after removing URLs and all-caps proper names such
    # as TÜFAM, TİTCK and AUGMENTİN.
    language_sample = re.sub(r"https?://\S+|www\.\S+", " ", text)
    language_sample = re.sub(
        r"\b[A-ZÇĞİÖŞÜ0-9][A-ZÇĞİÖŞÜ0-9._/-]{1,}\b",
        " ",
        language_sample,
    ).lower()
    if re.search(r"[çğıöşü]", language_sample):
        return True
    tokens = set(re.findall(r"[a-z]+", language_sample))
    markers = {
        "karyola", "yatak", "genislik", "yukseklik", "uzunluk", "malzeme",
        "kisilik", "cekmece", "sunta", "masif", "kanepe", "baza",
    }
    return len(tokens.intersection(markers)) >= 2
