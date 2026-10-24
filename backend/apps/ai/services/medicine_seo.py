"""SEO карточки лекарства — кодом, по SEO-плану медикаментов (docs/SEO_MEDICINES.md).

Модель в SEO теряла вещество и бренд кириллицей, а правила плана (без «без рецепта»,
отметка холодовой цепи, никакой рекламы препаратов строгого учёта) промптом не держатся.
Поэтому title, description и keywords собираются здесь из уже проверенных частей:
названия товара (``build_medicine_title`` + ``title_with_inn``), словаря брендов
кириллицей (память ``medicine_brand``), МНН, типа рецепта и условий хранения источника.
"""

from __future__ import annotations

import re
from typing import Any, Optional, Sequence

from apps.ai.services.medicine_reference import fold_tr

BRAND_NAMESPACE = "medicine_brand"
SEO_TITLE_MAX = 70
SEO_DESCRIPTION_MAX = 160

# «2-8 °C», «2 °C ile 8 °C arasında», «2°C - 8°C», «+2 ila +8 ºC»; «buzdolabında saklayınız».
# «Buzdolabında saklamayınız» (не хранить в холодильнике) холодовой цепью не считается.
_COLD_RANGE = re.compile(r"(?<![\d.,])\+?2\s*(?:°|º|o)?\s*C?\s*(?:-|–|ile|ila|ve|ve\s+arası)\s*\+?8\s*(?:°|º|o)\s*C", re.I)
_FRIDGE = re.compile(r"buzdolab[ıi]nda\s+(?:\(\s*2.{0,12}8.{0,6}\)\s*)?saklay", re.I)

_TEXTS = {
    "ru": {
        "turkey": " из Турции",
        "leaflet": " — инструкция, цена",
        "inn": "Действующее вещество — {inn}.",
        "rx": "Отпускается по рецепту.",
        "controlled": "Препарат строгого учёта, отпускается по специальному рецепту.",
        "cold": "Хранение и перевозка при 2–8 °C.",
        "instruction": "Инструкция на русском.",
        "order": "Заявка менеджеру, доставка 7–21 рабочий день.",
        "restricted": "Ввоз в {countries} ограничен.",
        "and": "и",
        "keyword_turkey": "{brand} из Турции",
        "keyword_leaflet": "{brand} инструкция",
    },
    "en": {
        "turkey": " from Turkey",
        "leaflet": " — leaflet, price",
        "inn": "Active ingredient: {inn}.",
        "rx": "Prescription medicine.",
        "controlled": "Controlled medicine, dispensed on a special prescription.",
        "cold": "Store and ship at 2–8 °C.",
        "instruction": "Patient leaflet in English.",
        "order": "Send a request, delivery in 7–21 business days.",
        "restricted": "Import to {countries} is restricted.",
        "and": "and",
        "keyword_turkey": "{brand} Turkey",
        "keyword_leaflet": "{brand} leaflet",
    },
}
# Страны с запретом ввоза (controlled_substances) — как в предложении «Ввоз в … ограничен».
_COUNTRIES = {
    "ru": {"RU": "Россию", "KZ": "Казахстан", "UZ": "Узбекистан"},
    "en": {"RU": "Russia", "KZ": "Kazakhstan", "UZ": "Uzbekistan"},
}
# Длинное начало описания («бренд (вещество) доза, форма из Турции.») — без вещества в скобках.
_LEAD_MAX = 100


def needs_cold_chain(storage_source: Any) -> bool:
    """Условия хранения источника требуют 2–8 °C (Оземпик, Мунджаро, инсулины, вакцины)."""
    text = str(storage_source or "")
    return bool(_COLD_RANGE.search(text) or _FRIDGE.search(fold_tr(text)))


def prescription_kind(prescription_en: Any) -> str:
    """Перевод типа рецепта (``PRESCRIPTION_TYPES``) → "controlled" / "rx" / "otc" / ""."""
    value = str(prescription_en or "").lower()
    if "controlled" in value:
        return "controlled"
    if "over-the-counter" in value:
        return "otc"
    return "rx" if "prescription" in value else ""


# Обрезанный по слову заголовок не кончается предлогом или союзом: «…, раствор для».
_DANGLING = {"для", "с", "со", "в", "во", "и", "на", "по", "из", "от", "for", "with", "in", "and", "of", "from", "—"}


def _fit(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    words = text[:limit].rsplit(" ", 1)[0].rstrip(" ,—").split(" ")
    while len(words) > 1 and words[-1].lower() in _DANGLING:
        words.pop()
    return " ".join(words).rstrip(" ,—")


def cyrillic_brand(brand: str, short: str, found: dict) -> str:
    """Бренд названия кириллицей по словарю брендов (ключи — бренд абзацев ``short``).

    «MAJEZIK» → «Мажезик». Бренд названия длиннее: «PHYSIONEAL 40» → «Физионеал 40».
    Короче: «EXTRANEFROL» при «EXTRANEFROL PERITON DIYALIZ» («Экстранефрол Перитонеальный
    Диализ») → «Экстранефрол». Хвост с латиницей («POLIFLEKS 1/3 POLIDEKS») кириллицей не
    записать — пусто, бренд в SEO остаётся латиницей.
    """
    if found.get(brand):
        return found[brand]["ru"]
    entry = found.get(short) if short else None
    if not entry:
        return ""
    if brand.startswith(short):
        tail = brand[len(short):]
        return "" if re.search(r"[A-Za-z]", tail) else entry["ru"] + tail
    words, count = entry["ru"].split(), len(brand.split())
    if short.startswith(brand + " ") and len(words) == len(short.split()):
        return " ".join(words[:count])
    return ""


def _title_parts(title: str, brand: str, inn: str) -> tuple[str, list[str]]:
    """«MAJEZIK (флурбипрофен) 100 мг, таблетки, 15 шт.» → ("", ["100 мг", "таблетки", "15 шт."]);
    «ZINCO, сироп, 150 мл» → (",", ["сироп", "150 мл"]): без дозировки форма идёт через запятую."""
    rest = title[len(brand):]
    if inn and rest.startswith(f" ({inn})"):
        rest = rest[len(inn) + 3:]
    return ("," if rest.startswith(",") else ""), [part for part in rest.strip(" ,").split(", ") if part]


def _countries(locale: str, codes: Sequence[str]) -> str:
    """«Россию, Казахстан и Узбекистан» для «Ввоз в … ограничен»; '' — ограничений нет."""
    names = [name for code, name in _COUNTRIES[locale].items() if code in codes]
    return f" {_TEXTS[locale]['and']} ".join([", ".join(names[:-1]), names[-1]] if len(names) > 1 else names)


def fallback_seo(
    seo_title: str, title: str, locale: str, prescription: str = "", restricted_countries: Sequence[str] = ()
) -> dict[str, str]:
    """SEO препарата строгого учёта или запрещённого к ввозу, когда название собрала модель.

    Шаблон кодом название не разобрал, и SEO — от модели: в нём бывают «из Турции», заявка и
    доставка. Description собирается заново из названия модели и правил ``build_medicine_seo``;
    у строгого учёта из SEO title убираются «из Турции» и «— инструкция, цена».
    """
    texts = _TEXTS[locale]
    controlled = prescription == "controlled"
    if controlled:
        for part in (texts["leaflet"], texts["turkey"]):
            seo_title = seo_title.replace(part, "")
    lead = _fit(title.replace(texts["turkey"], "").rstrip(" ."), _LEAD_MAX)
    lead += "" if controlled else texts["turkey"]
    countries = _countries(locale, restricted_countries)
    required = [
        texts["controlled"] if controlled else "",
        texts["restricted"].format(countries=countries) if countries else "",
    ]
    description = _with_sentences(_lead([lead + "."], required), [
        texts["controlled"] if controlled else texts["rx"] if prescription == "rx" else "",
        required[1],
        texts["instruction"],
    ], required)
    return {"seo_title": seo_title.strip(), "seo_description": description}


def _lead(leads: list[str], required: list[str]) -> str:
    """Первое начало описания, после которого ещё помещается ``required``; иначе последнее, обрезанное."""
    room = SEO_DESCRIPTION_MAX - sum(len(sentence) + 1 for sentence in required if sentence)
    return next((lead for lead in leads if len(lead) <= room), None) or _fit(leads[-1].rstrip("."), room - 1) + "."


def _with_sentences(description: str, sentences: list[str], required: list[str]) -> str:
    """Предложения по важности, пока помещаются в SEO_DESCRIPTION_MAX; место под ``required`` — всегда."""
    pending = [sentence for sentence in required if sentence]
    for sentence in sentences:
        if not sentence:
            continue
        if sentence in pending:
            pending.remove(sentence)
        reserve = sum(len(other) + 1 for other in pending)
        if len(description) + 1 + len(sentence) + reserve <= SEO_DESCRIPTION_MAX:
            description = f"{description} {sentence}"
    return description


def _join(head: str, sep: str, parts: list[str]) -> str:
    return f"{head}{sep} {', '.join(parts)}" if parts else head


def build_medicine_seo(
    title: dict[str, str],
    brand: str,
    brand_ru: str = "",
    inn: Optional[tuple[str, str]] = None,
    prescription: str = "",
    cold_chain: bool = False,
    restricted_countries: Sequence[str] = (),
) -> dict[str, dict[str, Any]]:
    """{"ru": {"seo_title", "seo_description", "keywords"}, "en": {...}} из названия товара.

    ``title`` — название кодом (со скобкой МНН или без), ``brand`` — его начало латиницей,
    ``brand_ru`` — бренд кириллицей из словаря (пусто — только латиница), ``inn`` — МНН
    в скобках названия (RU, EN), ``prescription`` — ``prescription_kind``.
    SEO title — первый вариант, который укладывается в SEO_TITLE_MAX: с веществом и формой,
    затем короче. Description — начало и предложения по важности, пока помещаются в
    SEO_DESCRIPTION_MAX. Для препаратов строгого учёта нет «из Турции», цены, заявки и
    доставки: их не продвигаем (SEO-план, «Ограничения»). Препарат, ввоз которого запрещён
    (``restricted_countries`` — коды стран, TD-024): без заявки и доставки, с «Ввоз в … ограничен».
    """
    controlled = prescription == "controlled"
    result = {}
    for index, locale in enumerate(("ru", "en")):
        texts = dict(_TEXTS[locale])
        if controlled:
            texts.update(turkey="", leaflet="", order="")
        if restricted_countries:
            texts["order"] = ""
        countries = _countries(locale, restricted_countries)
        inn_text = inn[index] if inn else ""
        sep, parts = _title_parts(title[locale], brand, inn_text)
        name = brand_ru if locale == "ru" and brand_ru and brand_ru.lower() != brand.lower() else ""
        # «Мажезик (MAJEZIK, флурбипрофен)», «MAJEZIK (flurbiprofen)», «Мажезик (MAJEZIK)», «MAJEZIK».
        inside = [brand] if name else []
        head = f"{name or brand} ({', '.join(inside + [inn_text])})" if inn_text else (f"{name} ({brand})" if name else brand)
        head_short = f"{name} ({brand})" if name else brand

        turkey, leaflet = texts["turkey"], texts["leaflet"]

        def variants(start: str) -> list[str]:
            two, one = _join(start, sep, parts[:2]), _join(start, sep, parts[:1])
            return [two + turkey + leaflet, two + turkey, one + turkey + leaflet, one + turkey]

        candidates = variants(head) + variants(head_short)
        if name:
            # Бренд кириллицей важнее «из Турции»; не помещается и так — бренд латиницей.
            candidates.append(_join(head_short, sep, parts[:1]))
            candidates += variants(f"{brand} ({inn_text})" if inn_text else brand) + variants(brand)
        seo_title = next((c for c in candidates if len(c) <= SEO_TITLE_MAX), None) or _fit(
            " ".join([brand, ", ".join(parts[:1])]).strip(), SEO_TITLE_MAX
        )

        leads = [_join(head, sep, parts[:2]) + turkey + "."]
        if len(leads[0]) > _LEAD_MAX:
            leads = []
        leads += [_join(head_short, sep, parts[:2]) + turkey + ".", _join(head_short, sep, parts[:1]) + turkey + "."]
        # Строгий учёт и запрет ввоза помещаются всегда: начало описания при нужде короче.
        required = [
            texts["controlled"] if controlled else "",
            texts["restricted"].format(countries=countries) if countries else "",
        ]
        lead = _lead(leads, required)
        with_inn = bool(inn_text) and lead == _join(head, sep, parts[:2]) + turkey + "."
        description = _with_sentences(lead, [
            texts["controlled"] if controlled else texts["rx"] if prescription == "rx" else "",
            required[1],
            texts["cold"] if cold_chain else "",
            texts["instruction"],
            texts["order"],
            texts["inn"].format(inn=inn_text) if inn_text and not with_inn else "",
        ], required)

        form = next((part for part in parts if not re.search(r"\d", part)), "")
        keywords = [brand, name, inn_text, form, texts["keyword_leaflet"].format(brand=name or brand)]
        if not controlled:
            keywords.insert(4, texts["keyword_turkey"].format(brand=name or brand))
        result[locale] = {
            "seo_title": seo_title,
            "seo_description": description,
            "keywords": list(dict.fromkeys(k for k in keywords if k)),
        }
    return result
