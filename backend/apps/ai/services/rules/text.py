"""Названия, SEO и описания-из-фактов по шаблонам (без LLM)."""

from __future__ import annotations

import re
from typing import Any

from apps.ai.services.rules import vocab
from apps.ai.services.rules.facts import ProductFacts

# Описание источника, в котором кроме названия и атрибутов меньше стольких
# значимых слов, переводить моделью незачем: текст собирается из фактов.
THIN_SOURCE_MAX_WORDS = 6
META_TITLE_MAX = 70
META_DESCRIPTION_MAX = 160
# В названии — не больше двух описательных слов: остальные факты в описании.
TITLE_DESCRIPTORS_MAX = 2
# Семейства, где название без бренда/модели бессмысленно («Духи»): нужен LLM.
_REQUIRES_IDENTITY = frozenset({"perfumery"})


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def truncate_at_word(text: str, limit: int) -> str:
    """Обрезка по границе слова (как limitTitle/truncateAtWord на фронте)."""
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(clean) <= limit:
        return clean
    cut = clean[: limit - 1].rsplit(" ", 1)[0].rstrip(",.;:—- ")
    return f"{cut}…"


def _ru_head(facts: ProductFacts) -> str:
    kind = facts.kind
    if facts.audience is None:
        return kind.ru
    audience = facts.audience[0]
    if audience.startswith("="):
        return f"{kind.ru} {audience[1:]}"
    return f"{vocab.ru_adjective(audience, kind.gender)} {kind.ru}"


def _identity(facts: ProductFacts) -> str:
    brand, model = facts.brand.strip(), facts.model.strip()
    if brand and vocab.fold(brand) in vocab.fold(model):
        return model
    return " ".join(part for part in (brand, model) if part)


def _title_descriptors(facts: ProductFacts) -> list[tuple[str, str]]:
    """Материал важнее прочих описательных слов, порядок внутри групп сохраняется."""
    materials = [pair for pair in facts.descriptors if pair[0].startswith("из ")]
    others = [pair for pair in facts.descriptors if not pair[0].startswith("из ")]
    chosen = set((materials + others)[:TITLE_DESCRIPTORS_MAX])
    return [pair for pair in facts.descriptors if pair in chosen]


def build_titles(facts: ProductFacts) -> dict[str, str]:
    """RU/EN-названия; отсутствующий язык — пустая строка (его дополнит LLM)."""
    if facts.product_type == "islamic_clothing":
        return {"ru": "", "en": ""}  # названия — подписи Instagram, нужен пересказ
    if facts.russian_name:
        # Название уже на русском (Zara RU, прошлый AI, ручные правки): RU
        # сохраняем, EN собираем из фактов при известном типе, иначе — LLM.
        # Цвета в RU-названии нет — не добавляем его и в EN.
        return {"ru": facts.russian_name, "en": _english_title(facts, with_color=False) if facts.kind else ""}
    if facts.kind is None or facts.untranslated:
        return {"ru": "", "en": ""}
    identity = _identity(facts)
    if facts.product_type in _REQUIRES_IDENTITY and not identity:
        return {"ru": "", "en": ""}

    if facts.product_type == "furniture":
        ru = f"{_capitalize(facts.kind.ru)} {identity}".strip()
        en = f"{identity} {facts.kind.en}".strip()
        if facts.finish:
            ru, en = f"{ru}, {facts.finish[0]}", f"{en}, {facts.finish[1]}"
        return {"ru": ru, "en": en}

    ru_parts = [_capitalize(_ru_head(facts))]
    if identity:
        ru_parts.append(identity)
    ru_parts.extend(ru for ru, _ in _title_descriptors(facts))
    ru = " ".join(part for part in ru_parts if part)

    for amount in (facts.volume, facts.pack):
        if amount:
            ru = f"{ru}, {amount[0]}"
    if facts.color:
        ru = f"{ru}, {facts.color.ru_for(facts.kind.gender)}"
    return {"ru": ru, "en": _english_title(facts)}


def _english_title(facts: ProductFacts, *, with_color: bool = True) -> str:
    """«LC Waikiki Men's Faux Leather Belt, Black», «IKEA HAVBERG Armchair»."""
    identity = _identity(facts)
    if facts.product_type == "furniture":
        en = f"{identity} {facts.kind.en}".strip()
        return f"{en}, {facts.finish[1]}" if facts.finish and with_color else en
    parts = [identity, facts.audience[1] if facts.audience else ""]
    parts.extend(en for _, en in _title_descriptors(facts))
    parts.append(facts.kind.en)
    en = " ".join(part for part in parts if part)
    for amount in (facts.volume, facts.pack):
        if amount:
            en = f"{en}, {amount[1]}"
    if facts.color and with_color:
        en = f"{en}, {facts.color.en}"
    return en


def _significant_words(text: str) -> list[str]:
    return [word for word in re.findall(r"[^\W\d_]{2,}", text, re.UNICODE)]


def is_thin_source(source_text: str, name: str, facts: ProductFacts) -> bool:
    """Текст источника не несёт ничего сверх названия и атрибутов."""
    if not source_text:
        return True
    known = set(vocab.fold(name).split()) | set(vocab.fold(facts.brand).split())
    known |= set(vocab.fold(facts.model).split())
    known |= set(vocab.KINDS) | set(vocab.AUDIENCE) | set(vocab.COLORS) | set(vocab.FIBERS)
    known |= {"organik", "kumas", "beden", "renk", "cinsiyet", "erkek", "kadin", "unisex"}
    words = [word for word in _significant_words(source_text) if vocab.fold(word) not in known]
    return len(words) < THIN_SOURCE_MAX_WORDS


def build_fact_description(facts: ProductFacts, titles: dict[str, str]) -> dict[str, str]:
    """Описание из подтверждённых фактов: без выдуманных свойств и «воды»."""
    ru = [f"{titles['ru'].split(', ')[0]}."] if titles.get("ru") else []
    en = [f"{titles['en'].split(', ')[0]}."] if titles.get("en") else []
    if not ru and not en:
        return {}
    if facts.composition:
        ru.append(f"Состав: {facts.composition[0]}.")
        en.append(f"Composition: {facts.composition[1]}.")
    for label_ru, label_en, value in (
        ("Верх", "Upper", facts.upper),
        ("Подкладка", "Lining", facts.lining),
        ("Подошва", "Sole", facts.sole),
        ("Материал", "Material", facts.material),
    ):
        if value:
            ru.append(f"{label_ru}: {value[0]}.")
            en.append(f"{label_en}: {value[1]}.")
    if facts.volume:
        ru.append(f"Объем: {facts.volume[0]}.")
        en.append(f"Volume: {facts.volume[1]}.")
    if facts.color:
        ru.append(f"Цвет: {vocab.ru_masculine(facts.color.ru)}.")
        en.append(f"Color: {facts.color.en.lower()}.")
    ru.append("Оригинальный товар из Турции, заказ через менеджера Mudaroba.")
    en.append("Original product from Turkey, ordered via a Mudaroba manager.")
    # Язык без названия пропускается (описание без типа товара бессмысленно).
    result = {}
    if titles.get("ru"):
        result["ru"] = " ".join(ru)
    if titles.get("en"):
        result["en"] = " ".join(en)
    return result


def _first_sentence(description: str) -> str:
    plain = re.sub(r"<[^>]+>", " ", str(description or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    match = re.match(r"(.+?[.!?])(\s|$)", plain)
    return match.group(1) if match else plain


def build_seo(facts: ProductFacts, titles: dict[str, str], descriptions: dict[str, str]) -> dict[str, dict[str, Any]]:
    """meta_title / meta_description / keywords по шаблону сайта."""
    templates = {
        "ru": ("{title} — купить с доставкой из Турции", "{title} из Турции", "Заказать {title} из Турции. {lead}"),
        "en": ("{title} — buy with delivery from Turkey", "{title} from Turkey", "Order {title} from Turkey. {lead}"),
    }
    result: dict[str, dict[str, Any]] = {}
    for locale, (long_title, short_title, description_template) in templates.items():
        title = str(titles.get(locale) or "").strip()
        if not title:
            continue
        meta_title = long_title.format(title=title)
        if len(meta_title) > META_TITLE_MAX:
            meta_title = short_title.format(title=title)
        meta_title = truncate_at_word(meta_title, META_TITLE_MAX)
        lead = _first_sentence(descriptions.get(locale) or "")
        if vocab.fold(lead).rstrip(".") == vocab.fold(title.split(", ")[0]):
            lead = ""
        meta_description = truncate_at_word(
            description_template.format(title=title, lead=lead).strip(), META_DESCRIPTION_MAX
        )
        result[locale] = {
            "seo_title": meta_title,
            "seo_description": meta_description,
            "keywords": build_keywords(facts, locale, title),
        }
    return result


def build_keywords(facts: ProductFacts, locale: str, title: str) -> list[str]:
    base = title.split(", ")[0]
    words: list[str] = [base]
    identity = _identity(facts)
    if facts.kind:
        kind = facts.kind.ru if locale == "ru" else facts.kind.en.lower()
        words.append(kind)
        if facts.audience and locale == "ru":
            words.append(_ru_head(facts))
        elif facts.audience:
            words.append(f"{facts.audience[1]} {kind}")
        if identity:
            words.append(f"{kind} {identity}")
        words.append(f"{kind} из Турции" if locale == "ru" else f"{kind} from Turkey")
    if facts.brand:
        words.append(facts.brand)
    seen, result = set(), []
    for word in words:
        clean = re.sub(r"\s+", " ", word).strip()
        if clean and clean.casefold() not in seen:
            seen.add(clean.casefold())
            result.append(clean)
    return result[:8]
