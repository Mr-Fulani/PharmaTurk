"""Бренды БАДов для SEO: как их пишут в поиске (SEO-ядро 07.11.2026).

Источник — подсказки Яндекса и Google и Google Trends RU
(``reports/supplement-seo-core-2026-11-07.md``). Название на карточке (H1) не меняется:
там бренд как в источнике. Словарь меняет только SEO title, description и keywords:

- латиница — как пишет производитель («Solgar», «Nature's Bounty»); у линейки Ocean
  добавлен производитель Orzax: ищут «орзакс оушен экстрамаг», «orzax ocean d3 k2»;
- кириллица — только как её ищут («Доппельгерц», а не «Доппельхерц»; «Орзакс Оушен»);
  пустая строка — бренд кириллицей не ищут или слово занято («вунка» — фильм «Вонка»,
  «суда»), в SEO он только латиницей.

Бренда нет в словаре — SEO как раньше: бренд источника и кириллица из памяти переводов.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from apps.ai.services.medicine_reference import fold_tr

# Ключ — слова бренда источника без знаков, нижним регистром ASCII.
BRANDS: dict[str, tuple[str, str]] = {
    # Ищут кириллицей.
    "solgar": ("Solgar", "Солгар"),
    "natures bounty": ("Nature's Bounty", "Натурес Баунти"),
    "doppelherz": ("Doppelherz", "Доппельгерц"),
    "ocean": ("Orzax Ocean", "Орзакс Оушен"),
    "orzax": ("Orzax", "Орзакс"),
    "orzax ocean": ("Orzax Ocean", "Орзакс Оушен"),
    "zade vital": ("Zade Vital", "Заде Витал"),
    "venatura": ("Venatura", "Венатура"),
    "nutraxin": ("Nutraxin", "Нутраксин"),
    "vitabiotics": ("Vitabiotics", "Витабиотикс"),
    "vitabiotics pregnacare": ("Vitabiotics Pregnacare", "Витабиотикс Прегнакеа"),
    "vitabiotics wellman": ("Vitabiotics Wellman", "Витабиотикс Велмен"),
    "vitabiotics wellwoman": ("Vitabiotics Wellwoman", "Витабиотикс Велвумен"),
    "vitabiotics perfectil": ("Vitabiotics Perfectil", "Витабиотикс Перфектил"),
    "day2day": ("Day2Day", "Дэй Ту Дэй"),
    # Модель берёт в бренд артикль линейки «THE COLLAGEN»; в SEO он не нужен.
    "day2day the": ("Day2Day", "Дэй Ту Дэй"),
    "natrol": ("Natrol", "Натрол"),
    "maxigal": ("Maxigal", "Максигал"),
    "argivit": ("Argivit", "Аргивит"),
    "avicenna": ("Avicenna", "Авиценна"),
    "nutrigen": ("Nutrigen", "Нутриген"),
    "magnimore": ("Magnimore", "Магнимор"),
    "velavit": ("Velavit", "Велавит"),
    "swiss energy": ("Swiss Energy", "Свисс Энерджи"),
    "aptamil": ("Aptamil", "Аптамил"),
    "hipp": ("HiPP", "Хипп"),
    "bebelac": ("Bebelac", "Бебелак"),
    # Ищут только латиницей.
    "voonka": ("Voonka", ""),
    "suda": ("Suda", ""),
    "suda vitamin": ("Suda Vitamin", ""),
    "nbtlife": ("NBTLife", ""),
    "dynavit": ("Dynavit", ""),
    "goodday": ("GoodDay", ""),
    "imuneks": ("Imuneks", ""),
    "swiss bork": ("Swiss Bork", ""),
    "nouplus": ("NouPlus", ""),
    "lipozone": ("Lipozone", ""),
    "osende": ("Osende", ""),
    "natuwell": ("Natuwell", ""),
    "viapecia": ("Viapecia", ""),
    "naturalnest": ("NaturalNest", ""),
    "ligone": ("Ligone", ""),
    "apidemica": ("Apidemica", ""),
    "potiogarden": ("PotioGarden", ""),
    "gummylab": ("GummyLab", ""),
    "pure encapsulations": ("Pure Encapsulations", ""),
    "storm vitals": ("Storm Vitals", ""),
    "dr thomson": ("Dr. Thomson", ""),
}

_MAX_KEY_WORDS = 3


def _word_key(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", fold_tr(word))


def _title_part(part: str) -> str:
    # Обозначения и аббревиатуры остаются заглавными: «EPA-DHA», «MSM», «NAC», «Q10» (ревью #333).
    from apps.ai.services.supplement_content import _ACRONYMS_RE, _ALLOWED_LATIN

    if len(part) <= 2 or re.search(r"\d", part) or _ACRONYMS_RE.fullmatch(part) or _ALLOWED_LATIN.match(part):
        return part
    # Турецкая «İ»: str.lower() даёт «i» с точкой сверху (U+0307) — «Bi̇oti̇n» (ревью #333).
    part = part.replace("İ", "I")
    return part[:1] + part[1:].lower()


def _title_word(word: str) -> str:
    """Слово линейки после бренда: «FIXMIX» → «Fixmix», «EASY-C» → «Easy-C», «BİOTİN» → «Biotin»;
    «D3», «GS», «EPA-DHA» — как есть."""
    if not word.isupper():
        return word
    return "-".join(_title_part(part) for part in word.split("-"))


class SeoBrand(NamedTuple):
    latin: str  # бренд латиницей целиком: «Orzax Ocean Gummies»
    ru: str  # кириллицей или ""
    latin_for_ru: str  # часть латиницы, которую передаёт кириллица: «Orzax Ocean»


def seo_brand(brand: str, brand_ru: str) -> SeoBrand:
    """Бренд для SEO; бренда нет в словаре — бренд источника и кириллица из памяти без изменений.

    Слова линейки после бренда остаются: «OCEAN EXTRAMAG» + «Оушен Экстрамаг» →
    «Orzax Ocean Extramag» / «Орзакс Оушен Экстрамаг». Если кириллица из памяти не делится
    по словам так же, как латиница, кириллицей пишется только бренд из словаря, и в скобках —
    те же слова: «Велавит (Velavit) Phytoglow …», а не «Велавит (Velavit Phytoglow)».
    """
    words = str(brand or "").split()
    keys = [_word_key(word) for word in words]
    for size in range(min(_MAX_KEY_WORDS, len(words)), 0, -1):
        entry = BRANDS.get(" ".join(keys[:size]))
        if entry:
            break
    else:
        return SeoBrand(brand, brand_ru, brand)
    latin, ru = entry
    rest = words[size:]
    display = " ".join([latin, *(_title_word(word) for word in rest)])
    if not ru or not rest:
        return SeoBrand(display, ru, display)
    ru_words = str(brand_ru or "").split()
    if len(ru_words) == len(words):
        return SeoBrand(display, " ".join([ru, *ru_words[size:]]), display)
    return SeoBrand(display, ru, latin)
