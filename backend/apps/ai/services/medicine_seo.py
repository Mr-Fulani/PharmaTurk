"""SEO карточки лекарства — кодом, по SEO-плану медикаментов (docs/SEO_MEDICINES.md).

Модель в SEO теряла вещество и бренд кириллицей, а правила плана (без «без рецепта»,
отметка холодовой цепи, никакой рекламы препаратов строгого учёта) промптом не держатся.
Поэтому title, description и keywords собираются здесь из уже проверенных частей:
названия товара (``build_medicine_title`` + ``title_with_inn``), словаря брендов
кириллицей (память ``medicine_brand``), МНН, типа рецепта и условий хранения источника.
"""

from __future__ import annotations

import re
from typing import Any, Optional

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
        "keyword_turkey": "{brand} Turkey",
        "keyword_leaflet": "{brand} leaflet",
    },
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


def _fit(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(" ,—")


def _title_parts(title: str, brand: str, inn: str) -> tuple[str, list[str]]:
    """«MAJEZIK (флурбипрофен) 100 мг, таблетки, 15 шт.» → ("", ["100 мг", "таблетки", "15 шт."]);
    «ZINCO, сироп, 150 мл» → (",", ["сироп", "150 мл"]): без дозировки форма идёт через запятую."""
    rest = title[len(brand):]
    if inn and rest.startswith(f" ({inn})"):
        rest = rest[len(inn) + 3:]
    return ("," if rest.startswith(",") else ""), [part for part in rest.strip(" ,").split(", ") if part]


def _join(head: str, sep: str, parts: list[str]) -> str:
    return f"{head}{sep} {', '.join(parts)}" if parts else head


def build_medicine_seo(
    title: dict[str, str],
    brand: str,
    brand_ru: str = "",
    inn: Optional[tuple[str, str]] = None,
    prescription: str = "",
    cold_chain: bool = False,
) -> dict[str, dict[str, Any]]:
    """{"ru": {"seo_title", "seo_description", "keywords"}, "en": {...}} из названия товара.

    ``title`` — название кодом (со скобкой МНН или без), ``brand`` — его начало латиницей,
    ``brand_ru`` — бренд кириллицей из словаря (пусто — только латиница), ``inn`` — МНН
    в скобках названия (RU, EN), ``prescription`` — ``prescription_kind``.
    SEO title — первый вариант, который укладывается в SEO_TITLE_MAX: с веществом и формой,
    затем короче. Description — начало и предложения по важности, пока помещаются в
    SEO_DESCRIPTION_MAX. Для препаратов строгого учёта нет «из Турции», цены, заявки и
    доставки: их не продвигаем (SEO-план, «Ограничения»).
    """
    controlled = prescription == "controlled"
    result = {}
    for index, locale in enumerate(("ru", "en")):
        texts = dict(_TEXTS[locale])
        if controlled:
            texts.update(turkey="", leaflet="", order="")
        inn_text = inn[index] if inn else ""
        sep, parts = _title_parts(title[locale], brand, inn_text)
        name = brand_ru if locale == "ru" and brand_ru and brand_ru.lower() != brand.lower() else ""
        # «Мажезик (MAJEZIK, флурбипрофен)», «MAJEZIK (flurbiprofen)», «Мажезик (MAJEZIK)», «MAJEZIK».
        inside = [brand] if name else []
        head = f"{name or brand} ({', '.join(inside + [inn_text])})" if inn_text else (f"{name} ({brand})" if name else brand)
        head_short = f"{name} ({brand})" if name else brand

        turkey, leaflet = texts["turkey"], texts["leaflet"]
        candidates = []
        for start in (head, head_short):
            two, one = _join(start, sep, parts[:2]), _join(start, sep, parts[:1])
            candidates += [two + turkey + leaflet, two + turkey, one + turkey + leaflet, one + turkey]
        seo_title = next((c for c in candidates if len(c) <= SEO_TITLE_MAX), _fit(candidates[-1], SEO_TITLE_MAX))

        lead = _join(head, sep, parts[:2]) + turkey + "."
        with_inn = bool(inn_text)
        if len(lead) > _LEAD_MAX:
            lead, with_inn = _join(head_short, sep, parts[:2]) + turkey + ".", False
        description = _fit(lead, SEO_DESCRIPTION_MAX)
        sentences = [
            texts["controlled"] if controlled else texts["rx"] if prescription == "rx" else "",
            texts["cold"] if cold_chain else "",
            texts["instruction"],
            texts["order"],
            texts["inn"].format(inn=inn_text) if inn_text and not with_inn else "",
        ]
        for sentence in sentences:
            if sentence and len(description) + 1 + len(sentence) <= SEO_DESCRIPTION_MAX:
                description = f"{description} {sentence}"

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
