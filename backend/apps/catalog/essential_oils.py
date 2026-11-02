"""Эфирные масла и гидролаты из раздела БАДов источника — кодом, без LLM.

ilacfiyati.com выкладывает линейку PHYTOIL (Elentra İlaç: эфирные масла, гидролаты,
цветочные воды) в «Takviye edici gıda», и парсер сохранял её БАДами: карточка
писала «биологически активная добавка к пище» про масло, которое не едят, а
семантическая проверка AI отклоняла тексты (title_category_mismatch). Место этих
товаров — раздел «Эфирные масла» (essential-oils, тип incense).

Правило: в названии есть явный признак эфирного масла или гидролата (или линейка
PHYTOIL) и нет формы, которую принимают внутрь (капсулы, таблетки…). Просто «yağı»
не признак: масло чёрного тмина, рыбий жир, масло зародышей пшеницы — БАДы.
Используют команда ``move_essential_oils_from_supplements`` и парсер ilacfiyati
для новых товаров (``scrapers.medicine_categories``).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from apps.ai.services.medicine_reference import fold_tr

ROOT_SLUG = "essential-oils"
SINGLE_SLUG = "single-essential-oils"
PRODUCT_TYPE = "incense"


def _re(*words: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(words) + r")(?![a-z0-9])")


_MARKERS = _re(
    r"ucucu yag\w*", r"esansiyel yag\w*", r"essential oils?", r"hidrolat\w*", r"hydrosol\w*",
    r"cicek suyu", r"floral water", r"phytoil",
)
_MARKERS_RU = re.compile(r"эфирн\w* масл|гидролат|цветочн\w* вод", re.IGNORECASE)
# Внутрь: такое масло — БАД («PHYTOIL … KAPSUL» остался бы в БАДах).
_INGESTED = _re(
    r"kapsul\w*", r"capsules?", r"softgel\w*", r"tablet\w*", r"sase\w*", r"sachets?", r"pastil\w*",
    r"surup\w*", r"syrup", r"gida takviye\w*",
    # Источник сам называет пищевой добавкой: «VACROL DAMLA ESANSIYEL YAGLAR ICEREN TAKVIYE EDICI GIDA».
    r"takviye edici gida",
)
_INGESTED_RU = re.compile(r"капсул|таблет|саше|сироп|пастил", re.IGNORECASE)
_WATER = _re(r"\w+ suyu", r"hidrolat\w*", r"hydrosol\w*", r"floral water", r"\w+ water")
_WATER_RU = re.compile(r"гидролат|вод[аы]", re.IGNORECASE)
# Подразделы «Одиночных масел» (constants.py). Товар уходит в подраздел, только если
# растение одно; смесь, другое растение или вода — раздел выше.
PLANT_SLUGS: tuple[tuple[str, re.Pattern], ...] = (
    ("lavender-oil", _re(r"lavanta\w*", r"lavender", r"lavandula")),
    ("peppermint-oil", _re(r"nane\w*", r"peppermint", r"mentha")),
    ("eucalyptus-oil", _re(r"okaliptus\w*", r"eucalyptus")),
    ("rose-oil", _re(r"gul", r"rose", r"rosa")),
    ("tea-tree-oil", _re(r"cay agac\w*", r"tea tree", r"melaleuca")),
)


def essential_oil_category_slug(source_name: Any, name_ru: Any = "") -> Optional[str]:
    """Slug раздела «Эфирные масла» для товара или None, если это не эфирное масло/гидролат."""
    text = fold_tr(source_name)
    ru = str(name_ru or "")
    # RU-название — только если турецкого нет: «CHINA OEL Эфирное масло» и «VACROL Капли с
    # эфирными маслами» источник продаёт как takviye edici gıda (решение владельца, 02.11.2026).
    latin = bool(re.search(r"[a-z]", text))
    if latin:
        if not _MARKERS.search(text):
            return None
    elif not _MARKERS_RU.search(ru):
        return None
    if _INGESTED.search(text) or _INGESTED_RU.search(ru):
        return None
    if _WATER.search(text) or (not latin and _WATER_RU.search(ru)):
        return ROOT_SLUG
    plants = {slug for slug, pattern in PLANT_SLUGS if pattern.search(text)}
    return plants.pop() if len(plants) == 1 else SINGLE_SLUG


def essential_oil_category(slug: Optional[str]):
    """Активная категория по slug правила; нет подраздела — ближайший раздел выше (до essential-oils)."""
    from apps.catalog.models import Category

    if not slug:
        return None
    chain = [ROOT_SLUG] if slug == ROOT_SLUG else [slug, SINGLE_SLUG, ROOT_SLUG]
    found = {row.slug: row for row in Category.objects.filter(slug__in=chain, is_active=True)}
    return next((found[item] for item in chain if item in found), None)
