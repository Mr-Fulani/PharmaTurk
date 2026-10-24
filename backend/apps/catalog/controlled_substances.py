"""Препараты, ввоз которых в Россию и СНГ запрещён или ограничен (TD-024).

Справочник — ``data/controlled_substances.json``: вещество (МНН), ключи действующего
вещества как в каталоге (``split_inn``, турецкое написание без диакритики) и по каждой
стране — список, источник и редакция. Собран 24.10.2026 по официальным перечням
(РФ — ПП № 681 и № 964; Казахстан, Узбекистан — национальные списки); формулировки и
полноту проверяет юрист (docs/CONTROLLED_SUBSTANCES.md).

Лекарство с таким веществом отмечается полями ``import_restricted_countries`` и
``import_restriction_note``: красная плашка и фильтр в админке, не попадает в хиты,
подборки и рекламные фиды. Покупателю — метка «Ввоз ограничен» на карточке, плашка на
странице и в «Списке заявки» (поле API ``import_restricted_countries`` — список кодов стран).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent / "data" / "controlled_substances.json"
COUNTRY_NAMES = {"RU": "Россия", "KZ": "Казахстан", "UZ": "Узбекистан"}


@lru_cache(maxsize=1)
def _index() -> dict[str, dict]:
    entries = json.loads(DATA_PATH.read_text(encoding="utf-8")) if DATA_PATH.exists() else []
    return {key: entry for entry in entries for key in entry.get("tr_keys") or []}


def restrictions(active_ingredient: Any) -> tuple[str, str]:
    """(страны через запятую, основание построчно) для действующего вещества; ("", "") — нет."""
    from apps.ai.services.medicine_memory import split_inn

    countries: set[str] = set()
    notes: list[str] = []
    for key in split_inn(active_ingredient):
        entry = _index().get(key)
        if not entry:
            continue
        for country, info in sorted((entry.get("countries") or {}).items()):
            countries.add(country)
            notes.append(f"{COUNTRY_NAMES.get(country, country)}: {entry.get('inn_ru') or key} — {info.get('list', '')}")
    return ",".join(sorted(countries)), "\n".join(dict.fromkeys(notes))


def refresh_medicine(medicine) -> bool:
    """Пересчитать отметку у лекарства (без save()); True — изменилась."""
    countries, note = restrictions(getattr(medicine, "active_ingredient", ""))
    changed = (medicine.import_restricted_countries, medicine.import_restriction_note) != (countries, note)
    medicine.import_restricted_countries, medicine.import_restriction_note = countries, note
    return changed


def country_codes(value: Any) -> list[str]:
    """«KZ,RU» → ["KZ", "RU"] (поле API ``import_restricted_countries``)."""
    return [code for code in str(value or "").split(",") if code]


def product_restricted_countries(product) -> list[str]:
    """Коды стран с запретом ввоза для базового товара (только лекарства)."""
    from django.core.exceptions import ObjectDoesNotExist

    if product is None or getattr(product, "product_type", "") != "medicines":
        return []
    try:
        medicine = product.medicine_item
    except ObjectDoesNotExist:
        return []
    return country_codes(medicine.import_restricted_countries)
