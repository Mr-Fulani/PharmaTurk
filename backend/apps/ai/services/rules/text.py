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
FACT_DESCRIPTION_TAIL = {
    "ru": "Оригинальный товар из Турции, заказ через менеджера Mudaroba.",
    "en": "Original product from Turkey, ordered via a Mudaroba manager.",
}
# Турецкое в русском названии: буквы, которых нет в шведских/немецких сериях
# (IKEA LÖNSET), и суффикс фасовки «3'lü» / транслитом «3'ЛЮ».
TURKISH_LEFTOVER_RE = re.compile(r"[çğışÇĞİŞ]|'[lL][iıuüIİUÜ]\b|'Л[ЮИУ]\b")
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
    # «Only&Sons» в каталоге и «Only & Sons» в названии — один бренд, не дважды.
    if brand and re.sub(r"[\W_]+", "", vocab.fold(brand)) in re.sub(r"[\W_]+", "", vocab.fold(model)):
        return model
    return " ".join(part for part in (brand, model) if part)


def _title_descriptors(facts: ProductFacts) -> list[tuple[str, str]]:
    """Материал важнее прочих описательных слов, порядок внутри групп сохраняется.

    Слово, которое уже есть в типе, не повторяется: «туфли на каблуке … на низком
    каблуке», «шлепанцы на пробковой подошве … на пробковой подошве»."""
    kind_words = set(facts.kind.ru.split()) if facts.kind else set()
    descriptors = [pair for pair in facts.descriptors if pair[0].split()[-1] not in kind_words]
    materials = [pair for pair in descriptors if pair[0].startswith("из ")]
    others = [pair for pair in descriptors if not pair[0].startswith("из ")]
    limit = TITLE_DESCRIPTORS_MAX + (1 if facts.extra_descriptor else 0)
    chosen = set((materials + others)[:limit])
    return [pair for pair in descriptors if pair in chosen]


def build_titles(facts: ProductFacts, *, ignore_untranslated: bool = False) -> dict[str, str]:
    """RU/EN-названия; отсутствующий язык — пустая строка (его дополнит LLM).

    ``ignore_untranslated`` — запасное название без непереведённых слов, когда
    LLM-название не годится.
    """
    if facts.product_type == "islamic_clothing":
        return {"ru": "", "en": ""}  # названия — подписи Instagram, нужен пересказ
    if facts.russian_name:
        # Название уже на русском (Zara RU, прошлый AI, ручные правки): RU
        # сохраняем, EN собираем из фактов при известном типе, иначе — LLM.
        # Цвета в RU-названии нет — не добавляем его и в EN.
        # Бренда в русском названии нет («Кепка с вышивкой») — дописываем в конец.
        ru = facts.russian_name
        if TURKISH_LEFTOVER_RE.search(ru):
            ru = ""  # «Мужские боксеры Soft Boxer 3'lü Paket» — переведёт LLM
        elif facts.brand and vocab.fold(facts.brand) not in vocab.fold(ru):
            ru = f"{ru} {facts.brand}"
        return {"ru": ru, "en": _english_title(facts, with_color=False) if facts.kind else ""}
    if facts.kind is None or (facts.untranslated and not ignore_untranslated):
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

    for amount in (facts.volume, facts.pack, facts.heel):
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
    for amount in (facts.volume, facts.pack, facts.heel):
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
    ru.append(FACT_DESCRIPTION_TAIL["ru"])
    en.append(FACT_DESCRIPTION_TAIL["en"])
    # Язык без названия пропускается (описание без типа товара бессмысленно).
    result = {}
    if titles.get("ru"):
        result["ru"] = " ".join(ru)
    if titles.get("en"):
        result["en"] = " ".join(en)
    return result


# Seniorah: описание — только характеристики магазина, собранные кодом (черновики Claude 09.11.2026
# писали «натуральная кожа» вместо экокожи «Cilt» и «цельная колодка» вместо «Tam kalıp»).
# Натуральную кожу магазин подписывает «Gerçek deri» — её различает translate_shoe_material.
SENIORAH_MEASURES = (
    (r"baldir olcusu", "Обхват голенища", "Calf circumference"),
    (r"bilek olcusu", "Обхват по щиколотке", "Ankle circumference"),
    (r"(?:topuk dahil boy olcusu|boy olcusu topuk dahil)", "Высота с каблуком", "Height incl. heel"),
)
# Материал в названии против «Dış materyal»: у Veraloaf «Siyah Rugan Loafer» в характеристиках
# «Süet» (ошибка магазина) — какой верен, не угадываем, строку «Верх» не пишем.
SENIORAH_TITLE_MATERIALS = ("rugan", "suet", "saten", "kroko", "cilt", "deri")
SENIORAH_INSOLES = {"anatomik": ("анатомическая", "anatomic"), "anotomik": ("анатомическая", "anatomic")}
_SENIORAH_CM_RE = re.compile(r"(\d+(?:[.,]\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?)\s*cm", re.IGNORECASE)
# Голое «Deri» у Seniorah неоднозначно: натуральную кожу магазин подписывает «Gerçek deri».
_SENIORAH_BARE_DERI_RE = re.compile(r"(?<!gercek )(?<!hakiki )\bderi\b")
# «Tam kalıptır …» — полномерные; «Tam kalıp değildir, bir numara büyük alınız» — нет.
_SENIORAH_TRUE_TO_SIZE_RE = re.compile(r"^\s*tam ?kalip")
_SENIORAH_SIZE_CAVEATS = ("degil", "buyuk", "kucuk", "dar ")


def _cm(value: str, locale: str) -> str:
    match = _SENIORAH_CM_RE.search(str(value or "").replace("\xa0", " "))
    if not match:
        return ""
    number = re.sub(r"\s*[-–]\s*", "–", match.group(1))
    number = number.replace(".", ",") if locale == "ru" else number.replace(",", ".")
    return f"{number} {'см' if locale == 'ru' else 'cm'}"


def _seniorah_material(value: tuple[str, str] | None, raw: Any) -> tuple[str, str] | None:
    return None if value is None or _SENIORAH_BARE_DERI_RE.search(vocab.fold(raw)) else value


def build_seniorah_description(
    facts: ProductFacts, titles: dict[str, str], attrs: dict, source_text: str, name: str = "",
) -> dict[str, str]:
    """Описание Seniorah из характеристик: верх, подкладка, стелька, каблук, обхваты, «полномерные»,
    детали из названия. Незнакомое или противоречивое значение не переводится наугад — строка пропускается.
    Без названия первая фраза — тип товара («Женские сандалии Seniorah.»), а не пустота."""
    if titles.get("ru"):
        ru = [f"{titles['ru'].split(', ')[0]}."]
    else:
        ru = [f"{_capitalize(_ru_head(facts))} {facts.brand}".strip() + "."] if facts.kind else []
    if titles.get("en"):
        en = [f"{titles['en'].split(', ')[0]}."]
    else:
        en = [f"{facts.brand} {facts.audience[1] if facts.audience else ''} {facts.kind.en}".replace("  ", " ").strip() + "."] if facts.kind else []
    title, material = vocab.fold(name), vocab.fold(attrs.get("material"))
    upper = _seniorah_material(facts.upper, attrs.get("material"))
    if any(word in title and word not in material for word in SENIORAH_TITLE_MATERIALS):
        upper = None
    lining = _seniorah_material(facts.lining, attrs.get("lining"))
    for label_ru, label_en, value in (("Верх", "Upper", upper), ("Подкладка", "Lining", lining)):
        if value:
            ru.append(f"{label_ru}: {value[0]}.")
            en.append(f"{label_en}: {value[1]}.")
    insole = SENIORAH_INSOLES.get(vocab.fold(attrs.get("insole")).split(" ")[0]) if attrs.get("insole") else None
    if insole:
        ru.append(f"Стелька: {insole[0]}.")
        en.append(f"Insole: {insole[1]}.")
    heel_ru, heel_en = _cm(attrs.get("heel_height"), "ru"), _cm(attrs.get("heel_height"), "en")
    if heel_ru:
        ru.append(f"Высота каблука: {heel_ru}.")
        en.append(f"Heel height: {heel_en}.")
    text = vocab.fold(source_text)
    for pattern, label_ru, label_en in SENIORAH_MEASURES:
        match = re.search(rf"37 numara icin {pattern}\s*:\s*([0-9.,]+\s*cm)", text)
        if match:
            # Без слова «размер»: strip_size_inventory_sentences вырезает фразы «размер + число»
            # как обещание наличия (на проде 09.11.2026 обхваты и «полномерные» пропали).
            ru.append(f"{label_ru} (EU 37): {_cm(match.group(1), 'ru')}.")
            en.append(f"{label_en} (EU 37): {_cm(match.group(1), 'en')}.")
    # Детали, которых нет в первой фразе (название срезает их до двух-трёх).
    lead = ru[0] if ru else ""
    details = [pair for pair in facts.descriptors if pair[0] and not pair[0].startswith("из ") and pair[0] not in lead]
    if details:
        ru.append(f"Особенности: {', '.join(pair[0] for pair in details)}.")
        en.append(f"Details: {', '.join(pair[1].lower() for pair in details)}.")
    advice = vocab.fold(attrs.get("size_advice"))
    if _SENIORAH_TRUE_TO_SIZE_RE.match(advice) and not any(word in f"{advice} " for word in _SENIORAH_SIZE_CAVEATS):
        ru.append("Полномерные, по размерной сетке — выбирайте как обычно.")
        en.append("Standard fit — order as usual.")
    ru.append(FACT_DESCRIPTION_TAIL["ru"])
    en.append(FACT_DESCRIPTION_TAIL["en"])
    return {"ru": " ".join(ru), "en": " ".join(en)}


def _sentences(description: str) -> list[str]:
    plain = re.sub(r"<[^>]+>", " ", str(description or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    return [part.strip() for part in re.findall(r"[^.!?]+[.!?]?", plain) if part.strip()]


def _lead(description: str, title: str, locale: str) -> str:
    """Первое предложение описания, которое не повторяет название и не служебное."""
    base = vocab.fold(title.split(", ")[0])
    for sentence in _sentences(description):
        if vocab.fold(sentence).rstrip(".") == base or sentence == FACT_DESCRIPTION_TAIL[locale]:
            continue
        if sentence.startswith(("Цвет:", "Color:")):
            continue  # цвет уже в названии
        return sentence
    return ""


def _meta_title(title: str, long_template: str, middle_template: str, short_template: str) -> str:
    """Полное название с «купить…», затем без цвета, затем короче — без «купить», без «оригинал»."""
    base = title.split(", ")[0]
    for candidate in (
        long_template.format(title=title),
        long_template.format(title=base),
        middle_template.format(title=base),
        short_template.format(title=base),
    ):
        if len(candidate) <= META_TITLE_MAX:
            return candidate
    return truncate_at_word(short_template.format(title=base), META_TITLE_MAX)


def build_seo(facts: ProductFacts, titles: dict[str, str], descriptions: dict[str, str]) -> dict[str, dict[str, Any]]:
    """meta_title / meta_description / keywords по шаблону сайта.

    Description начинается с названия в именительном падеже («Заказать
    мужская футболка» было ошибкой), затем факт «из Турции» и первое
    содержательное предложение описания.
    """
    # «оригинал» — частое уточнение к бренду и модели в рунете («nike air force 1 белые
    # оригинал», «угги ugg оригинал»; подсказки Яндекса 05.11.2026), чаще «доставки».
    templates = {
        "ru": ("{title} — купить оригинал из Турции", "{title} — оригинал из Турции", "{title} из Турции", "{title}. Оригинальный товар из Турции с доставкой."),
        "en": ("{title} — buy original from Turkey", "{title} — original from Turkey", "{title} from Turkey", "{title}. Original product from Turkey with delivery."),
    }
    # Унисекс ищут как «мужские …» и «женские …»: говорим об этом в description.
    unisex_note = {"ru": "Модель унисекс — для мужчин и женщин.", "en": "Unisex: for men and women."}
    result: dict[str, dict[str, Any]] = {}
    for locale, (long_title, middle_title, short_title, description_head) in templates.items():
        title = str(titles.get(locale) or "").strip()
        if not title:
            continue
        lead = _lead(descriptions.get(locale) or "", title, locale)
        head = description_head.format(title=title)
        if _is_unisex(facts):
            head = f"{title}. {unisex_note[locale]} {head[len(title) + 2:]}"
        meta_description = truncate_at_word(f"{head} {lead}".strip(), META_DESCRIPTION_MAX)
        result[locale] = {
            "seo_title": _meta_title(title, long_title, middle_title, short_title),
            "seo_description": meta_description,
            "keywords": build_keywords(facts, locale, title),
        }
    return result


def _is_unisex(facts: ProductFacts) -> bool:
    return bool(facts.audience) and facts.audience[1] == "Unisex"


def build_keywords(facts: ProductFacts, locale: str, title: str) -> list[str]:
    base = title.split(", ")[0]
    words: list[str] = [base]
    identity = _identity(facts)
    brand_ru = vocab.BRAND_RU.get(vocab.fold(facts.brand)) if locale == "ru" else None
    if facts.kind:
        kind = facts.kind.ru if locale == "ru" else facts.kind.en.lower()
        words.append(kind)
        if _is_unisex(facts) and locale == "ru":
            words.extend(f"{vocab.ru_adjective(audience, facts.kind.gender)} {kind}" for audience in ("мужской", "женский"))
        elif facts.audience and locale == "ru":
            words.append(_ru_head(facts))
        elif facts.audience:
            words.append(f"{facts.audience[1]} {kind}")
        if identity:
            words.append(f"{kind} {identity}")
        if brand_ru:
            words.append(f"{kind} {brand_ru}")
        if identity and locale == "ru":
            words.append(f"{identity} оригинал")
        words.append(f"{kind} из Турции" if locale == "ru" else f"{kind} from Turkey")
    if facts.brand:
        words.append(facts.brand)
    seen, result = set(), []
    for word in words:
        clean = re.sub(r"\s+", " ", word).strip()
        if clean and clean.casefold() not in seen:
            seen.add(clean.casefold())
            result.append(clean)
    return result[:10]
