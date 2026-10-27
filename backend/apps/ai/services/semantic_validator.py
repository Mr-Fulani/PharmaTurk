"""Universal field-level semantic validation before applying AI output."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

from apps.catalog.attribute_specs import get_dynamic_attribute_spec
from apps.catalog.category_policy import CATEGORY_POLICY_OVERRIDES, build_category_policy
from apps.catalog.product_semantics import looks_untranslated_turkish
from apps.ai.services.medicine_fact_check import strip_proper_name_lines
from apps.ai.services.medicine_memory import section_paragraph_problems
from apps.ai.services.medicine_reference import fold_tr
from apps.ai.services.medicine_title import (
    CYRILLIC_RE,
    FORM_PHRASES,
    MODIFIERS,
    TRUNCATED_TITLE_RE,
    is_form_word,
    is_title_descriptor_word,
    medicine_source_name,
    paragraph_brand,
    title_brand,
)
from apps.ai.services.rules.facts import supplier_code_tokens
from apps.ai.services.rules.vocab import fold, generic_title_words
from apps.ai.services import supplement_content, supplement_glossary
from apps.ai.services.size_inventory import (
    merge_confirmed_sizes,
    size_inventory_block_reason,
)


# These words are legitimate medicine dosage forms, but they also exist as
# unrelated catalog categories (most notably English ``tablets`` in the
# electronics tree).  A medicine title must not be rejected merely because it
# contains its dosage form; brand/strength/pack identity is validated below.
_MEDICINE_DOSAGE_FORM_CATEGORY_ALIASES = {
    "ru": frozenset(
        {
            "таблетка",
            "таблетки",
            "капсула",
            "капсулы",
            "сироп",
            "крем",
            "гель",
            "капли",
            "спрей",
            "мазь",
            "порошок",
            "инъекция",
            "суппозиторий",
            "суспензия",
            # Упаковка лекарства, а не товар медтехники «Шприцы» (партия Claude 1047, 25.10.2026).
            "шприц",
            "шприцы",
            "шприца",
            "шприцев",
            "шприц-ручка",
            "шприц-ручки",
        }
    ),
    "en": frozenset(
        {
            "tablet",
            "tablets",
            "syringe",
            "syringes",
            "pen",
            "pens",
            "capsule",
            "capsules",
            "syrup",
            "cream",
            "gel",
            "drops",
            "spray",
            "ointment",
            "powder",
            "injection",
            "suppository",
            "suppositories",
            "suspension",
            "suspensions",
        }
    ),
}
# Дозировочные формы законны и в названиях БАДов («Melatonin Tablets»).
_DOSAGE_FORM_PRODUCT_TYPES = frozenset({"medicines", "supplements"})

# Категории-аудитории и материалы («Мужские», «Men's», «Leather») — не тип
# товара: «Мужские джинсы» не противоречат категории «Джинсы».
_NON_KIND_CATEGORY_ALIASES = {
    "ru": frozenset(
        {
            "мужские", "мужская", "мужской", "мужское", "для мужчин",
            "женские", "женская", "женский", "женское", "для женщин",
            "детские", "детская", "детский", "детское", "для детей",
            "унисекс", "кожа", "натуральная кожа", "кожаные",
            # Общие слова названий разделов других каталогов (волна 1 мебели, 26.10.2026).
            "аксессуары",
            # «жидкая форма», «классические пастилки» у БАДов — не спортивная форма и не бельё
            # (очередь модерации 26.10.2026).
            "форма", "классические", "классический", "классическая",
            # Подкатегории-аудитории и признаки («Буркини для девочек», «ортопедические
            # шлепанцы», «воротник из искусственного меха») — очередь модерации 27.10.2026.
            "для девочек", "для мальчиков", "ортопедические", "из искусственного меха",
        }
    ),
    "en": frozenset(
        {
            "men", "men s", "mens", "man", "women", "women s", "womens", "woman", "kids", "unisex", "leather",
            # «Children's Wardrobe» — не детские ходунки, «Storage System» — не накопители ПК,
            # «Light Grey» — не термобельё, «Suspension Rail» — не подвеска автомобиля.
            "children", "children s", "childrens", "storage", "light", "suspension", "gaming", "accessories",
            # «Classic Lozenges», «Medium-Chain Triglycerides» (очередь модерации 26.10.2026).
            "classic", "medium",
            # «Sports Belt», «Jewelry Box» — не корни «Спорттовары»/«Украшения»,
            # «Orthopedic Slippers» — не стельки (очередь модерации 27.10.2026).
            "sports", "jewelry", "orthopedic",
        }
    ),
}

# Категории услуг описывают работы, а не товары: их алиасы («Gas» у газовых
# варочных панелей) не должны конфликтовать с названиями товаров.
_SERVICE_ROOT_SLUGS = frozenset({"uslugi"})
# Подкатегории БАДов делят товары по веществам (supplement_taxonomy): вещество соседней
# подкатегории в названии — состав, а не другой товар («Кальций и витамин D» в «Минералах»).
_INGREDIENT_ROOT_SLUGS = frozenset({"supplements"})


@dataclass
class SemanticValidationReport:
    rejected_fields: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)
    canonical_product_kind: str = ""
    # Поле лекарства → абзацы с признаками чужого перевода (medicine_paragraph_findings).
    paragraph_findings: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Поля, проверку которых снял модератор («title», «medicine_translation:<поле>»).
    moderator_reviewed_fields: set[str] = field(default_factory=set)

    @property
    def needs_moderation(self) -> bool:
        return bool(self.reasons)


# Поле перевода лекарства → раздел source_tabs, из которого оно переведено
# (как в ContentGenerator._build_medicine_source_sections).
_MEDICINE_SOURCE_TABS = {
    "indications": "indications",
    "contraindications": "before_use_warnings",
    "usage_instructions": "usage_instructions",
    "side_effects": "side_effects",
    "storage_conditions": "storage_conditions",
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def moderator_reviewed_title(log, attrs: dict[str, Any]) -> bool:
    """Модератор подтвердил именно текущие RU/EN-названия лога.

    Отметка хранит проверенный текст (``moderator_title_review``): новое
    название от AI или правка после отметки снова проходят все проверки.
    """
    review = attrs.get("moderator_title_review")
    if not isinstance(review, dict):
        return False
    translations = attrs.get("seo_translations") if isinstance(attrs.get("seo_translations"), dict) else {}
    en_title = (translations.get("en") or {}).get("generated_title") if isinstance(translations.get("en"), dict) else ""
    ru_title = _clean_text(getattr(log, "generated_title", ""))
    return bool(ru_title) and (
        _clean_text(review.get("ru")) == ru_title and _clean_text(review.get("en")) == _clean_text(en_title)
    )


def moderator_reviewed_medicine_fields(attrs: dict[str, Any]) -> set[str]:
    """Разделы лекарства с решением «Проверено — применить как есть».

    Решение действует, пока RU/EN раздела совпадают с текстом, который видел
    модератор (``medicine_moderator_overrides``).
    """
    decisions = attrs.get("medicine_moderator_decisions")
    overrides = attrs.get("medicine_moderator_overrides")
    translations = attrs.get("translations_data")
    if not isinstance(decisions, dict) or not isinstance(overrides, dict) or not isinstance(translations, dict):
        return set()
    ru_data = translations.get("ru") if isinstance(translations.get("ru"), dict) else {}
    en_data = translations.get("en") if isinstance(translations.get("en"), dict) else {}
    reviewed = set()
    for field_name, decision in decisions.items():
        override = overrides.get(field_name)
        if decision != "reviewed" or not isinstance(override, dict):
            continue
        ru, en = _clean_text(ru_data.get(field_name)), _clean_text(en_data.get(field_name))
        if ru and en and _clean_text(override.get("ru")) == ru and _clean_text(override.get("en")) == en:
            reviewed.add(field_name)
    return reviewed


def medicine_paragraph_findings(log, attrs: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Клинические разделы лога лекарства, где перевод абзацев похож на чужой.

    Перевод сверяется с исходником, из которого он сделан (``input_data`` лога),
    теми же правилами, что и абзацы в памяти (``section_paragraph_problems``).
    Не проверяются: раздел без исходника в логе (перевод сделан не по абзацам),
    раздел, который модератор решил не менять или принял как есть, и текст,
    исправленный модератором в форме лога (``paragraphs_reviewed``).
    """
    if attrs is None:
        attrs = getattr(log, "extracted_attributes", None)
    attrs = attrs if isinstance(attrs, dict) else {}
    input_data = getattr(log, "input_data", None)
    input_data = input_data if isinstance(input_data, dict) else {}
    source_attrs = input_data.get("attributes") if isinstance(input_data.get("attributes"), dict) else {}
    tabs = source_attrs.get("source_tabs") if isinstance(source_attrs.get("source_tabs"), dict) else {}
    translations = attrs.get("translations_data") if isinstance(attrs.get("translations_data"), dict) else {}
    ru_data = translations.get("ru") if isinstance(translations.get("ru"), dict) else {}
    en_data = translations.get("en") if isinstance(translations.get("en"), dict) else {}
    quality = attrs.get("medicine_translation_quality")
    quality = quality if isinstance(quality, dict) else {}
    decisions = attrs.get("medicine_moderator_decisions")
    decisions = decisions if isinstance(decisions, dict) else {}
    brand = paragraph_brand(input_data.get("name"), input_data.get("active_ingredient"))
    reviewed = moderator_reviewed_medicine_fields(attrs)
    findings = {}
    for field_name, tab in _MEDICINE_SOURCE_TABS.items():
        payload = tabs.get(tab)
        source = str((payload.get("text") if isinstance(payload, dict) else payload) or "").strip()
        ru, en = str(ru_data.get(field_name) or ""), str(en_data.get(field_name) or "")
        details = quality.get(field_name) if isinstance(quality.get(field_name), dict) else {}
        if (
            not source
            or not (ru.strip() or en.strip())
            or decisions.get(field_name) == "keep_current"
            or field_name in reviewed
            or details.get("paragraphs_reviewed")
        ):
            continue
        problems = section_paragraph_problems(source, ru, en, brand=brand)
        if problems:
            findings[field_name] = problems
    return findings


def _ancestor_ids(category: Any) -> set[int]:
    ids: set[int] = set()
    parent = getattr(category, "parent", None)
    while parent is not None and parent.pk not in ids and len(ids) < 20:
        ids.add(parent.pk)
        parent = getattr(parent, "parent", None)
    return ids


# Турецкие слова каталога, которые модель оставляет в названии латиницей или
# транслитерирует кириллицей («Эркек сандалии», «TAKVIYE EDICI GIDA»).
_TURKISH_TITLE_WORDS = re.compile(
    r"\b(erkek|kadın|kadin|çocuk|cocuk|takviye|edici|gıda|gida|ayakkabı|ayakkabi|"
    r"tişört|tisort|gömlek|gomlek|pantolon|elbise|çanta|canta|kemer|sandalet|terlik|"
    # Фарма и БАДы: формы, фасовка и служебные слова источника.
    r"kapsül|kapsul|şurup|surup|merhem|damla|damlası|damlasi|suspansiyon|süspansiyon|"
    r"giderici|saşe|sase|şişe|sise|efervesan|çiğneme|cigneme|tableti|kapsülü|ağız|agiz|"
    r"sprey|spreyi|losyon|içeren|iceren|ekstresi|yağı|yagi|balık|balik|"
    # Вкус лечебного питания (_TURKISH_FLAVOUR_WORDS): «FORTINI … CILEK AROMALI».
    r"aromal[iı]|aromas[iı]z|[cç]ilek|vanilya|[cç]ikolata|kahve|portakal|ahududu|muz|meyve)\b",
    re.IGNORECASE,
)
# Вкус лечебного питания («FORTINI COMPACT … CILEK AROMALI», «ENSURE … VANILYA AROMALI»)
# переводится («со вкусом клубники») и не входит в бренд (очередь модерации 26.10.2026).
_TURKISH_FLAVOUR_WORDS = frozenset({
    "AROMALI", "AROMASIZ", "CILEK", "ÇILEK", "VANILYA", "CIKOLATA", "ÇIKOLATA", "KAHVE",
    "PORTAKAL", "AHUDUDU", "MUZ", "MEYVE", "TROPIK",
})
_TURKISH_TITLE_TRANSLITERATIONS = re.compile(
    r"(эркек|кадын|кадин|чоджук|чочук|айаккаб|аяккаб|тишорт|гёмлек|гомлек|пантолон|"
    r"элбисе|такви|эдиджи|гыда|ортофед|"
    # «саше» и «балык» — нормальные русские слова, их не включаем.
    r"дамла|гидерич|гидериджи|суспансийон|суспансиён|шурубу|шуруп|шише|"
    r"эфервесан|чигнеме|ичерен|экстреси|"
    # «балик яги» — транслитерация «balık yağı» (рыбий жир).
    r"\bбалик\b|\bяг[иы]\b)",
    re.IGNORECASE,
)
# Латинские единицы в RU-названии БАДа: промпт требует «мл».
_SUPPLEMENT_RU_TITLE_LATIN_UNITS = re.compile(r"(?<![A-Za-z])ml\b", re.IGNORECASE)


# RU-название лекарства: транслитерация турецких форм («ДИЛАЛТИ», «ФИЛЬМ-…»,
# «80 ТАБЛЕТ») — брак; «капсул», «ампул», «флакон» — нормальные русские слова.
_MEDICINE_RU_TITLE_TRANSLITERATIONS = re.compile(
    r"(дилалт|фил[ьл]?м|таблет(?![а-яё])|(?<![а-яё])тоз(?![а-яё])|[чц][её]зелти|жексий|"
    r"инфюз|лиофилизе(?![а-яё])|(?<![а-яё])помад|(?<![а-яё])д?жел(?![а-яё])|"
    r"(?<![а-яё])г[её]з(?![а-яё])|(?<![а-яё])бурун|солюсй|сусп[ае]нсий|"
    # Пилот 20.10.2026: «УЗАТИЛМИШ САЛИМЛИ», «Топикальный», «СЕРТ КАПСУЛЫ», «И.М./ОРОЛЬ»,
    # «(50 ТБ)», «ЭНТЕРИК», «ФИЛЬМ-КАПЛИ ТАБЛЕТКИ» (kaplı — «покрытые», а не «капли»).
    r"узатил|салимл|топикал|(?<![а-яё])серт(?![а-яё])|(?<![а-яё])орол|(?<![а-яё])тб(?![а-яё])|"
    r"(?<![а-яё])энтерик|капли[\s-]+таблет|"
    # AIRun 3, лог 1036: «%8 АМИНОКИСЛОТ ИВ ИНФУЗИЯ 500 МЛ (СЕТ)» — «ИВ», «СЕТ» и
    # турецкая запись процента «%8» (по-русски «8%»; «1% 1%» и «10% 100 мг» — русская).
    r"(?<![а-яё])ив(?![а-яё])|(?<![а-яё])сет(?![а-яё])|(?<![\d.,])%\s*\d)",
    re.IGNORECASE,
)
# Латиница в RU-названии лекарства допустима только в бренде источника и в этих обозначениях.
_MEDICINE_RU_TITLE_LATIN_OK = frozenset({
    "IV", "IM", "SC", "SR", "XR", "MR", "CR", "XL", "LA", "ER", "EC", "ODT", "RETARD", "FORTE",
    "FORT", "PLUS", "MITE", "DEPOT", "DUO", "JUNIOR", "MAX",
    "XA",  # «анти-Xa МЕ» у эноксапарина
})


# Единицы источника: в RU-названии они пишутся по-русски («мг», «МЕ», «ТЕ»), латиницей — брак.
# Английские слова формы и фасовки в названиях импортных лекарств — тоже переводятся.
_MEDICINE_SOURCE_UNIT_WORDS = frozenset({
    "MG", "MCG", "MKG", "ML", "G", "GR", "IU", "UI", "TU", "TSU", "MIU", "MMOL", "MEQ", "MCI", "U", "L", "ADET",
    "OZ", "TUP", "INJECTION", "SUSPENSION", "DROPS", "CREAM", "EYE", "EAR", "SYRUP", "KIT", "SACHET", "SACHETS",
    "SPRAY", "GEL", "PATCH", "PATCHES", "AMPOULE", "AMPOULES", "BOTTLE", "PEN", "PENS", "FOR", "AND", "WITH",
})


def _medicine_ru_title_untranslated(title: Any, source_name: Any) -> bool:
    """В RU-названии лекарства осталась латиница не из бренда (MG, ML, TU) или транслитерация."""
    text = str(title or "")
    if _MEDICINE_RU_TITLE_TRANSLITERATIONS.search(text):
        return True
    # Бренд — слова до первой дозировки; цифра внутри бренда («B6 VIGEN», «D-3») — не дозировка.
    prefix = re.split(r"(?=(?<![\w-])\d|%)", str(source_name or ""), maxsplit=1)[0]
    # Бренд шаблона бывает и с числом: «CAPD 4 STAY SAFE», «POLIFLEKS 1/3 POLIDEKS» (title_brand).
    prefix += " " + title_brand(source_name)
    brand = {fold_tr(token.strip(".'-")).upper() for token in re.findall(r"[^\W_][\w.'-]*", prefix)}
    # Часть бренда после цифры («MILUPA UCD 2 PRIMA», «ENSURE 2 CAL», «HUMAN ALBUMIN %20 BEHRING»): латинское
    # слово источника, кроме единиц, слов формы и турецких слов (очередь модерации 26.10.2026).
    brand |= {
        word
        for word in (fold_tr(token.strip(".'-")).upper() for token in re.findall(r"[^\W\d_][\w'-]*", str(source_name or "")))
        if word not in _MEDICINE_SOURCE_UNIT_WORDS
        and not is_form_word(word)
        and not _title_has_turkish_words(word)
    }
    for token in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü][A-Za-z0-9ÇĞİÖŞÜçğıöşü.'-]*", text):
        word = fold_tr(token.strip(".'-")).upper()
        # Буква — часть МНН: «полимиксин B», «витамин E»; римское число — «фактор VIII», «IX».
        if (
            word in brand
            or word in _MEDICINE_RU_TITLE_LATIN_OK
            or re.search(r"\d", word)
            or len(word) == 1
            or re.fullmatch(r"[IVX]{2,5}", word)
        ):
            continue
        return True
    return False


def _medicine_title_problem(title: Any, source_name: Any) -> str:
    """Причина брака названия лекарства, которую не ловят общие проверки, или ''.

    У старых товаров название в БД уже переведено прежней обработкой
    («DISAVER 50 MG ФИЛЬМ-КАПЛИ ТАБЛЕТКИ») или обрезано («MOUNJARO 7»): шаблон
    из такого названия не строится, а модель копирует его как есть.
    Исправленное модератором название проходит: проверяется сам результат.
    """
    text = str(title or "")
    if TRUNCATED_TITLE_RE.search(text):
        return "title_truncated"
    if CYRILLIC_RE.search(str(source_name or "")) and _normalized(text) == _normalized(source_name):
        return "title_source_translated"
    return ""


# Вкус лечебного питания: TR-слово источника → основа RU-перевода. Модель путала вкусы:
# FORTINI «MUZ» (банан) → «ваниль», FORTIMEL ENERGY «MUZ» → «мята» (очередь 27.10.2026).
_MEDICINE_FLAVOURS = {
    "muz": "банан", "cilek": "клубни", "vanilya": "ванил", "cikolata": "шоколад", "kahve": "коф",
    "portakal": "апельсин", "ahududu": "малин", "kayisi": "абрикос", "limon": "лимон", "nane": "мят",
}


def _medicine_flavour_lost(title: Any, source_name: Any) -> str:
    """«title_identity_lost», если вкус источника («MUZ AROMALI») в RU-названии назван иначе."""
    source = fold_tr(source_name)
    if "aromal" not in source:
        return ""
    text = str(title or "").lower().replace("ё", "е")
    for word, stem in _MEDICINE_FLAVOURS.items():
        if re.search(rf"(?<![a-z]){word}(?![a-z])", source) and stem not in text and word not in fold_tr(title):
            return "title_identity_lost"
    return ""


def _without_medicine_forms(title_text: str, locale: str) -> str:
    """Название без лекарственной формы: «gastro-resistant tablets» — не категория «gastro»."""
    for form_text in _MEDICINE_FORM_TEXTS[locale]:
        title_text = re.sub(rf"(?:^|\s){re.escape(form_text)}(?=$|\s)", " ", title_text)
    return title_text


def _medicine_category_text(title: Any, locale: str) -> str:
    """Название лекарства для сверки с категориями: без формы, вещества в скобках и уточнений.

    «INFERJECT (железо) …», «MULTIBIC …, with potassium» — вещество, а не категория БАДов «Железо»/«Калий».
    """
    text = _without_medicine_forms(_normalized(re.sub(r"\([^)]*\)", " ", str(title or ""))), locale)
    for modifier_text in _MEDICINE_MODIFIER_TEXTS[locale]:
        text = re.sub(rf"(?:^|\s){re.escape(modifier_text)}(?=$|\s)", " ", text)
    return text


def _alias_in_source(alias: str, source_name: Any, locale: str) -> bool:
    """Слово чужой категории взято из названия источника, а не придумано моделью.

    Латиницей как есть («CALCIUM FOLINATE», «SPINAL HEAVY», «FORTINI COMPACT», «TEA TREE»)
    или переводом турецкого слова по словарю БАДов и форм лекарств («KALSIYUM» → «кальций»,
    «GOZ VE KULAK DAMLASI» → «ушные капли»). Очередь модерации 26.10.2026: 173 лекарства и
    БАДа с верным названием ждали модерации из-за таких слов. Вещество не из источника
    («EISEFERON железо …») по-прежнему конфликт.
    """
    folded = fold_tr(source_name)
    if _contains_phrase(_normalized(folded), alias):
        return True
    index = 0 if locale == "ru" else 1
    texts = [supplement_glossary.GLOSSARY[key][index] for key in supplement_glossary.found_terms(folded)]
    texts += [
        labels[index]
        for phrase, labels in FORM_PHRASES.items()
        if re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", folded)
    ]
    return any(_contains_phrase(_normalized(text), alias) for text in texts)


def _title_has_turkish_words(title: Any) -> bool:
    text = str(title or "")
    return bool(_TURKISH_TITLE_WORDS.search(text) or _TURKISH_TITLE_TRANSLITERATIONS.search(text))


def _normalized(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or "")).casefold()
    return re.sub(r"[^a-zа-яё0-9]+", " ", text).strip()


# Подписи лекарственных форм шаблона названия (нормализованные), длинные — первыми.
_MEDICINE_FORM_TEXTS = {
    locale: sorted(
        {_normalized(labels[index]) for labels in FORM_PHRASES.values()}, key=len, reverse=True
    )
    for index, locale in enumerate(("ru", "en"))
}


_MEDICINE_MODIFIER_TEXTS = {
    locale: sorted({_normalized(labels[index]) for labels in MODIFIERS.values()}, key=len, reverse=True)
    for index, locale in enumerate(("ru", "en"))
}


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalized(phrase)
    return (
        bool(normalized_phrase)
        and re.search(rf"(?:^|\s){re.escape(normalized_phrase)}(?:$|\s)", text) is not None
    )


_KIND_TAIL_RE = re.compile(r"\s(?:с|со|with|для|for|из)\s")


def _kind_text(title_text: str) -> str:
    """Нормализованное название до « с / with / для / for / из »: дальше — детали, а не тип."""
    return _KIND_TAIL_RE.split(title_text, maxsplit=1)[0]


def _alias_specificity(value: str) -> tuple[int, int]:
    """Prefer multi-word product kinds; character length only breaks ties."""
    normalized = _normalized(value)
    return len(normalized.split()), len(normalized)


_TURKISH_ONLY_LETTERS_RE = re.compile(r"[ÇĞİŞçğış]")
# «100ML» в названии Zara — объём, в RU-названии он «100 мл»; «2X100», «3X30ML» —
# набор флаконов («2 × 100 мл»).
_VOLUME_TOKEN_RE = re.compile(r"(?:\d+X)?\d+(?:[.,]\d+)?(?:ML|GR|G|CM|MM|KG)|\d+X\d+(?:[.,]\d+)?")


def _without_marks(token: str) -> str:
    """«UTSÅDD» → «UTSADD»: диакритика не меняет модель."""
    return "".join(
        char for char in unicodedata.normalize("NFKD", token) if not unicodedata.combining(char)
    )


def _identity_tokens(value: Any) -> set[str]:
    # Stable model/series tokens, not ordinary title words.
    result: set[str] = set()
    for token in re.findall(
        r"[A-Za-z0-9ÅÄÖÜ][A-Za-z0-9ÅÄÖÜ/_-]{2,}",
        str(value or ""),
    ):
        upper = token.upper()
        if re.fullmatch(r"(?:[2-9]XL|X{1,4}[SML]|ONE[-_]?SIZE)", upper):
            continue
        # Код «J5SM-TST7325» санитайзер вырезает из любого названия
        # (strip_price_and_codes_from_title) — требовать его нельзя.
        if re.fullmatch(r"(?=[A-Z-]*\d)[A-Z0-9]{2,}-[A-Z0-9]+", upper):
            continue
        is_alphanumeric_model = any(char.isdigit() for char in token) and any(
            char.isalpha() for char in token
        )
        is_uppercase_code = (
            len(token) >= 3
            and any(char.isalpha() for char in token)
            and token == upper
        )
        if is_alphanumeric_model or "/" in token or is_uppercase_code:
            result.add(upper)
    return result


def _medicine_identity_tokens(value: Any) -> set[str]:
    """Identity facts for localized medicine titles.

    Turkish dosage-form words may legitimately become Russian or English, so
    the medicine gate preserves brand/series, strength and pack size instead
    of requiring every uppercase source word verbatim.
    """
    text = str(value or "")
    upper = text.upper()
    result: set[str] = set()
    generic_prefix_words = {
        "TABLET",
        "TABLETLER",
        "KAPSUL",
        "KAPSÜL",
        "KREM",
        "JEL",
        "SURUP",
        "ŞURUP",
        "SPREY",
        "DAMLA",
        "MERHEM",
        "ILAC",
        "İLAÇ",
        # Связки и уточнения источника: «… COZELTI ICEREN FLAKON», «SISE SETSIZ».
        "ICEREN",
        "İÇEREN",
        "SETLI",
        "SETSIZ",
        "USP",  # «DILAUDID TABLETS, USP 4 MG» — отметка фармакопеи, не бренд
    }
    prefix = re.split(r"(?=\d|%)", upper, maxsplit=1)[0]
    for token in re.findall(r"[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9_-]{2,}", prefix):
        token = token.rstrip("-_")  # «D-COLEFOR-1000-IU-…» — дефис перед дозировкой не часть бренда
        # Слова лекарственной формы («FILM TABLET») переводятся — это не бренд.
        # И вещества в/в раствора («IZOTONIK SODYUM KLORUR»): шаблон переводит их в форму.
        if (
            token not in generic_prefix_words
            and token not in _TURKISH_FLAVOUR_WORDS
            and not is_form_word(token)
            and not is_title_descriptor_word(token)
        ):
            result.add(f"BRAND:{token}")

    unit_aliases = {
        "MG": "MG",
        "МГ": "MG",
        "MCG": "MCG",
        "МCG": "MCG",
        "МКГ": "MCG",
        "G": "G",
        "GR": "G",
        "Г": "G",
        "ГР": "G",
        "ML": "ML",
        "МЛ": "ML",
    }
    for match in re.finditer(
        r"(\d+(?:[.,]\d+)?)\s*(MG|MCG|G|GR|ML|МГ|МКГ|Г|ГР|МЛ)\b",
        upper,
    ):
        number = match.group(1).replace(",", ".")
        result.add(f"DOSE:{number}:{unit_aliases[match.group(2)]}")
    # Миллионы единиц: «3 MIU» = «3 млн МЕ»; «3 МЕ» в названии — ошибка в миллион раз (пилот 27.10.2026).
    for match in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(?:MIU|M\.I\.U\.?|МЛН\.?\s*МЕ|MLN\.?\s*IU|MILLION\s+IU)(?!\w)", upper):
        result.add(f"DOSE:{match.group(1).replace(',', '.')}:MIU")
    # «DIANEFROL 137 %2.27» — турецкая запись «%2.27» относится к числу после знака;
    # «10% 100 МГ» — русская: знак вплотную к числу перед ним (очередь 26.10.2026).
    for match in re.finditer(
        r"(\d+(?:[.,]\d+)?)%|(?<![\d.,])%\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*%(?!\s*\d)", upper
    ):
        number = (match.group(1) or match.group(2) or match.group(3)).replace(",", ".")
        result.add(f"DOSE:{number}:%")
    pack_match = re.search(
        r"(?:\(|\b)(\d+)\s*(?:ADET|TABLET|TABLETS|KAPSUL|KAPSÜL|CAPSULES?|ШТ|ШТУК|ТАБЛЕТ(?:ОК|КИ)?|КАПСУЛ(?:А|Ы)?)\b",
        upper,
    )
    # «1 ADET», «(1 FLAKON)» — одна упаковка; название пишет её без числа («туба 5 г», «флакон»).
    if pack_match and pack_match.group(1) != "1":
        result.add(f"PACK:{pack_match.group(1)}")
    return result


def _supplement_identity_tokens(value: Any, *, source: bool = False) -> set[str]:
    """Идентичность БАДа: бренд, дозировки и фасовка.

    Название БАДа в источнике — турецкое описание («… TAKVIYE EDICI GIDA
    KAPSUL»), его слова при переводе обязаны исчезнуть. Сохраняться должны
    бренд (первое слово источника), дозировки и количество в упаковке.
    """
    text = str(value or "")
    facts = {token for token in _medicine_identity_tokens(text) if token.startswith("DOSE:")}
    # Фасовка: до двух слов между числом и формой («100 мягких желатиновых капсул»).
    packs = re.findall(
        r"(?<![\w.,])(\d+)\s*(?:[A-ZА-ЯЁÇĞİÖŞÜ]+\s+){0,2}"
        r"(?:ADET|TABLET\w*|KAPS[UÜ]L\w*|CAPSULES?|SA[SŞ]E|SACHETS?|ШТ\w*|ТАБЛЕТ\w*|КАПСУЛ\w*|САШЕ|ПАКЕТИК\w*)\b",
        text.upper(),
    )
    # У источника фасовка — последняя: в «OMEGA 3 KAPSUL 30 kapsül» «3» — часть состава
    # (153 названия каталога 25.10.2026); числа состава проверяет supplement_content.title_problems.
    for number in packs[-1:] if source else packs:
        facts.add(f"PACK:{number}")
    word_re = r"[A-Za-zÇĞİÖŞÜçğıöşü][A-Za-z0-9ÇĞİÖŞÜçğıöşü-]{2,}"
    words = re.findall(word_re, text)
    brands = words[:1] if source else words
    # Бренд источника — первое слово; короткое или с точкой («HP BIOTIN», «NN KARADUT»,
    # «DR.US OMEGA 3») так не выделить — второе слово уже состав, его переводят.
    if source and not re.fullmatch(word_re, (text.split() or [""])[0]):
        brands = []
    return facts | {f"BRAND:{word.upper()}" for word in brands}


class CategorySemanticIndex:
    """In-memory category policy index for bulk semantic validation.

    Request-time validation can keep using the lazy database path. Management
    commands that validate many products should build this index once and
    reuse it to avoid loading the complete category tree for every product.
    """

    def __init__(self, categories: Iterable[Any]):
        rows = list(categories)
        self._categories = {
            category.pk: category for category in rows if getattr(category, "pk", None) is not None
        }
        self._active_ids = {
            category.pk
            for category in rows
            if getattr(category, "pk", None) is not None and getattr(category, "is_active", False)
        }
        # Link parents to the already loaded objects. This makes lineage walks
        # in build_category_policy query-free regardless of tree depth.
        for category in rows:
            parent_id = getattr(category, "parent_id", None)
            if parent_id in self._categories:
                category._state.fields_cache["parent"] = self._categories[parent_id]
            elif parent_id is None:
                category._state.fields_cache["parent"] = None

        self._ancestor_cache: dict[int, frozenset[int]] = {}
        self._compatible_alias_cache: dict[tuple[int, str], frozenset[str]] = {}
        self._policy_cache: dict[tuple[int, str], Any] = {}
        self._alias_cache: dict[str, tuple[tuple[int, str, str], ...]] = {}

    @classmethod
    def from_database(cls) -> "CategorySemanticIndex":
        from apps.catalog.models import Category

        categories = Category.objects.all().prefetch_related(
            "translations",
            "global_attribute_keys",
        )
        return cls(categories)

    def policy_for(self, category: Any, product_type: str | None = None):
        category_id = getattr(category, "pk", None)
        indexed_category = self._categories.get(category_id)
        if indexed_category is None:
            return build_category_policy(category, product_type)
        cache_key = (category_id, str(product_type or ""))
        if cache_key not in self._policy_cache:
            self._policy_cache[cache_key] = build_category_policy(
                indexed_category,
                product_type,
            )
        return self._policy_cache[cache_key]

    def longest_conflicting_match(
        self,
        current_category: Any,
        title_text: str,
        locale: str,
        own_match_words: int,
    ) -> str:
        current_id = getattr(current_category, "pk", None)
        if current_id is None:
            return self._configured_override_match(
                current_category,
                title_text,
                locale,
                own_match_words,
            )

        current_lineage_ids = self._ancestor_ids(current_id)
        rows = self._aliases(locale)
        # Название совместимой категории (своя линия или подраздел) не конфликт,
        # даже если так же называется раздел другого дерева: «кроссовки» в «Обуви»
        # — это «Обувь → Кроссовки», а не «Спорт → Кроссовки».
        compatible_aliases = self._compatible_aliases(current_id, locale)
        # Алиасы из CATEGORY_POLICY_OVERRIDES тоже: «гардероб» в корне «Мебель» —
        # это «Мебель → Шкафы-купе и гардеробы» (очередь модерации 27.10.2026).
        best = self._configured_override_match(
            current_category,
            title_text,
            locale,
            own_match_words,
            compatible_aliases,
        )
        current_root = self._root_slug(current_id)
        for candidate_id, alias, normalized_alias in rows:
            if candidate_id in current_lineage_ids or normalized_alias in compatible_aliases:
                continue
            if current_root in _INGREDIENT_ROOT_SLUGS and self._root_slug(candidate_id) == current_root:
                continue
            # A more specific descendant is compatible with the current kind.
            if current_id in self._ancestor_ids(candidate_id):
                continue
            candidate_words, _candidate_length = _alias_specificity(normalized_alias)
            if own_match_words and candidate_words <= own_match_words:
                continue
            if _alias_specificity(normalized_alias) <= _alias_specificity(best):
                continue
            if _contains_phrase(title_text, alias):
                best = normalized_alias
        return best

    def _compatible_aliases(self, category_id: int, locale: str) -> frozenset[str]:
        key = (category_id, locale)
        if key not in self._compatible_alias_cache:
            lineage_ids = self._ancestor_ids(category_id)
            self._compatible_alias_cache[key] = frozenset(
                normalized_alias
                for candidate_id, _alias, normalized_alias in self._aliases(locale)
                if candidate_id in lineage_ids or category_id in self._ancestor_ids(candidate_id)
            )
        return self._compatible_alias_cache[key]

    def own_line_aliases(self, category: Any, locale: str) -> tuple[str, ...]:
        """Алиасы самой категории и её подразделов: «Трусы-боксеры» — свои для «Мужского белья»."""
        category_id = getattr(category, "pk", None)
        if category_id not in self._categories:
            return ()
        return tuple(
            normalized_alias
            for candidate_id, _alias, normalized_alias in self._aliases(locale)
            if category_id in self._ancestor_ids(candidate_id)
        )

    def _ancestor_ids(self, category_id: int) -> frozenset[int]:
        if category_id in self._ancestor_cache:
            return self._ancestor_cache[category_id]
        result: set[int] = set()
        current_id: int | None = category_id
        guard = 0
        while current_id is not None and current_id not in result and guard < 20:
            result.add(current_id)
            current = self._categories.get(current_id)
            current_id = getattr(current, "parent_id", None) if current is not None else None
            guard += 1
        frozen = frozenset(result)
        self._ancestor_cache[category_id] = frozen
        return frozen

    def _root_slug(self, category_id: int) -> str:
        current = self._categories.get(category_id)
        guard = 0
        while current is not None and getattr(current, "parent_id", None) in self._categories and guard < 20:
            current = self._categories[current.parent_id]
            guard += 1
        return getattr(current, "slug", "") if current is not None else ""

    def _is_service_category(self, category_id: int) -> bool:
        return any(
            getattr(self._categories.get(ancestor_id), "slug", "") in _SERVICE_ROOT_SLUGS
            for ancestor_id in self._ancestor_ids(category_id)
        )

    def _aliases(self, locale: str) -> tuple[tuple[int, str, str], ...]:
        if locale not in self._alias_cache:
            rows: list[tuple[int, str, str]] = []
            for category_id in self._active_ids:
                category = self._categories[category_id]
                if self._is_service_category(category_id):
                    continue
                policy = self.policy_for(category)
                if policy is None:
                    continue
                for alias in policy.aliases.get(locale, ()):
                    normalized_alias = _normalized(alias)
                    if normalized_alias in _NON_KIND_CATEGORY_ALIASES.get(locale, ()):
                        continue
                    if normalized_alias:
                        rows.append((category_id, alias, normalized_alias))
            self._alias_cache[locale] = tuple(rows)
        return self._alias_cache[locale]

    @staticmethod
    def _configured_override_match(
        current_category: Any,
        title_text: str,
        locale: str,
        own_match_words: int,
        compatible_aliases: frozenset[str] = frozenset(),
    ) -> str:
        best = ""
        current_slug = getattr(current_category, "slug", "")
        for canonical_kind, config in CATEGORY_POLICY_OVERRIDES.items():
            if canonical_kind == current_slug:
                continue
            for alias in (config.get("aliases") or {}).get(locale, ()):
                normalized_alias = _normalized(alias)
                if normalized_alias in compatible_aliases:
                    continue
                candidate_words, _candidate_length = _alias_specificity(normalized_alias)
                if own_match_words and candidate_words <= own_match_words:
                    continue
                if _alias_specificity(normalized_alias) <= _alias_specificity(best):
                    continue
                if _contains_phrase(title_text, alias):
                    best = normalized_alias
        return best


class SemanticValidator:
    def __init__(self, category_index: CategorySemanticIndex | None = None):
        self.category_index = category_index

    @classmethod
    def with_preloaded_categories(cls) -> "SemanticValidator":
        return cls(category_index=CategorySemanticIndex.from_database())

    def validate_log(self, log) -> SemanticValidationReport:
        product = getattr(log, "product", None)
        if product is None:
            return SemanticValidationReport()
        product_type = getattr(product, "product_type", None)
        attrs = merge_confirmed_sizes(
            getattr(log, "extracted_attributes", None) or {},
            getattr(log, "input_data", None) or {},
            product_type,
            allow_moderator_override=True,
        )
        translations = (
            attrs.get("seo_translations") if isinstance(attrs.get("seo_translations"), dict) else {}
        )
        # Название, подтверждённое модератором, проверки не проходят: решение
        # принял человек. Любое новое название проверяется снова.
        title_reviewed = moderator_reviewed_title(log, attrs)
        report = self.validate(
            product,
            generated_titles={}
            if title_reviewed
            else {
                "ru": getattr(log, "generated_title", ""),
                "en": (translations.get("en") or {}).get("generated_title", ""),
            },
            dynamic_attributes=attrs.get("dynamic_attributes") or [],
            sizes=attrs.get("sizes") or [],
            extracted_attributes=attrs,
        )
        if title_reviewed:
            report.moderator_reviewed_fields.add("title")
        # Заданную категорию AI не меняет (она определяет наценку): другое
        # предложение — повод для модератора, а не для авто-применения.
        # Предложение родительской (более общей) категории — не повод для
        # модератора: текущая категория точнее.
        suggested_category_id = getattr(log, "suggested_category_id", None)
        current_category = getattr(product, "category", None)
        if (
            suggested_category_id
            and current_category is not None
            and suggested_category_id != current_category.pk
            and suggested_category_id not in _ancestor_ids(current_category)
        ):
            report.reasons.append("category_change_suggested")
        # БАД: число из названия источника пропало в названии, в описании — число
        # не из источника или обещание лечения. Такое поле не применяется.
        if product_type == "supplements":
            for field_name, reasons in supplement_content.log_problems(log).items():
                if field_name == "title" and title_reviewed:
                    continue
                report.rejected_fields.add(field_name)
                report.reasons.extend(reasons)
            report.reasons = list(dict.fromkeys(report.reasons))
        # Сдвинутые переводы абзацев (у 92 логов 20.10.2026) проверки полноты не
        # видят: раздел «полный», но абзацы — от соседних. Такой раздел не применяется.
        if product_type == "medicines":
            report.moderator_reviewed_fields.update(
                f"medicine_translation:{field_name}"
                for field_name in moderator_reviewed_medicine_fields(attrs)
            )
            report.paragraph_findings = medicine_paragraph_findings(log, attrs)
            for field_name in report.paragraph_findings:
                report.rejected_fields.add(f"medicine_translation:{field_name}")
                report.reasons.append("medicine_paragraph_mismatch")
            report.reasons = list(dict.fromkeys(report.reasons))
        return report

    def validate(
        self,
        product,
        *,
        generated_titles: dict[str, Any],
        dynamic_attributes: list[dict[str, Any]],
        sizes: list[dict[str, Any]] | None = None,
        extracted_attributes: dict[str, Any] | None = None,
    ) -> SemanticValidationReport:
        attrs = extracted_attributes or {}
        category = getattr(product, "category", None)
        product_type = getattr(product, "product_type", None)
        # The detached-object path below is useful for lightweight unit tests.
        # Real catalog categories use one preloaded index, avoiding an N+1 walk
        # through the entire category tree for every title locale.
        if self.category_index is None and getattr(category, "pk", None):
            self.category_index = CategorySemanticIndex.from_database()
        policy = (
            self.category_index.policy_for(category, product_type)
            if self.category_index is not None
            else build_category_policy(category, product_type)
        )
        report = SemanticValidationReport(
            canonical_product_kind=policy.canonical_product_kind if policy else ""
        )
        size_reason = size_inventory_block_reason(
            getattr(product, "domain_item", product),
            product_type,
            sizes or [],
        )
        if size_reason:
            report.rejected_fields.add("sizes")
            report.reasons.append(size_reason)
        # Лекарство без категории (на проде 20.10.2026 — 140) проверяется так же:
        # название и медицинские разделы от категории не зависят.
        if policy is None and product_type != "medicines":
            report.reasons = list(dict.fromkeys(report.reasons))
            return report

        identity_tokens = (
            _medicine_identity_tokens if product_type == "medicines" else _identity_tokens
        )
        # Лекарство сверяется с турецким оригиналом, из которого строится шаблон:
        # name после применения AI переведён, у старых товаров ещё и обрезан.
        source_name = (
            medicine_source_name(getattr(product, "name", ""), getattr(product, "external_data", None))[0]
            if product_type == "medicines"
            else getattr(product, "name", "")
        )
        original_tokens = identity_tokens(source_name)
        if product_type == "supplements":
            # После применения AI name — RU-название: сверяем с турецким оригиналом.
            identity_tokens = _supplement_identity_tokens
            source_name = supplement_content.supplement_source_name(product)
            original_tokens = _supplement_identity_tokens(source_name, source=True)
        elif product_type != "medicines":
            # Турецкие названия часто целиком в ВЕРХНЕМ регистре: общие слова
            # («TEE», «SNEAKER», «BEYAZ») — не идентичность, а бренд/модель
            # («LC WAIKIKI» → «LC Waikiki») сверяем без учёта регистра.
            generic = generic_title_words()
            # Артикулы поставщика правила в название не пишут (rules/facts.py).
            codes = supplier_code_tokens(source_name)
            # Слово с чисто турецкими буквами («GÜNEŞ», «DİKDÖRTGEN») — не модель:
            # класс символов _identity_tokens их режет на обрывки («GÜNE»).
            latin_name = " ".join(word for word in str(source_name or "").split() if not _TURKISH_ONLY_LETTERS_RE.search(word))
            # Цвета через «/» («Beyaz/lacivert») — общие слова, а не модель «PLATSA/SMÅSTAD».
            original_tokens = {
                _without_marks(token)
                for token in _identity_tokens(latin_name)
                if fold(token) not in generic
                and token not in codes
                and not _VOLUME_TOKEN_RE.fullmatch(token)
                and not ("/" in token and all(fold(part) in generic for part in token.split("/") if part))
            }
            # «UTSADD» в источнике и «UTSÅDD» в названии (и наоборот) — одна модель.
            identity_tokens = lambda value: {  # noqa: E731
                _without_marks(token) for token in _identity_tokens(str(value or "").upper())
            }
        for locale, title in generated_titles.items():
            if not str(title or "").strip():
                continue
            medicine_problem = (
                _medicine_title_problem(title, source_name)
                or (_medicine_flavour_lost(title, source_name) if locale == "ru" else "")
                if product_type == "medicines"
                else ""
            )
            if medicine_problem:
                report.rejected_fields.add("title")
                report.reasons.append(medicine_problem)
                break
            if _title_has_turkish_words(title) or (
                locale == "ru"
                and product_type == "supplements"
                and _SUPPLEMENT_RU_TITLE_LATIN_UNITS.search(str(title))
            ) or (
                locale == "ru"
                and product_type == "medicines"
                and _medicine_ru_title_untranslated(title, source_name)
            ):
                report.rejected_fields.add("title")
                report.reasons.append("title_untranslated")
                break
            title_text = _normalized(title)
            own_aliases = policy.aliases.get(locale, ()) if policy is not None else ()
            if product_type not in _DOSAGE_FORM_PRODUCT_TYPES:
                # Тип товара — в начале названия: «органайзер для полки», «диван с
                # пружинным блоком», «Storage Combination with Glass Doors».
                title_text = _kind_text(title_text)
                if self.category_index is not None and policy is not None:
                    own_aliases = (*own_aliases, *self.category_index.own_line_aliases(category, locale))
            matching_own_aliases = [
                _normalized(alias)
                for alias in own_aliases
                if _contains_phrase(title_text, alias)
            ]
            own_match_words = max(
                (_alias_specificity(alias)[0] for alias in matching_own_aliases),
                default=0,
            )
            conflicting_match = (
                self._longest_conflicting_category_match(
                    category,
                    _medicine_category_text(title, locale)
                    if product_type == "medicines"
                    else title_text,
                    locale,
                    own_match_words,
                )
                if policy is not None
                else ""
            )
            if (
                product_type in _DOSAGE_FORM_PRODUCT_TYPES
                and conflicting_match
                and (
                    conflicting_match in _MEDICINE_DOSAGE_FORM_CATEGORY_ALIASES.get(locale, frozenset())
                    or _alias_in_source(conflicting_match, source_name, locale)
                )
            ):
                conflicting_match = ""
            # Латинское слово из названия источника (аромат «OUD VIBRANT LEATHER» — не
            # категория «Уд») модель не придумала. Только латиница: у применённого товара
            # name — уже RU-название AI, и «Кровать TONSTAD» не может оправдать само себя.
            # Лекарства и БАДы сверяются выше, со своими словарями.
            if (
                product_type not in _DOSAGE_FORM_PRODUCT_TYPES
                and conflicting_match
                and not CYRILLIC_RE.search(conflicting_match)
                and _contains_phrase(_normalized(fold_tr(source_name)), conflicting_match)
            ):
                conflicting_match = ""
            if conflicting_match:
                report.rejected_fields.add("title")
                report.reasons.append("title_category_mismatch")
                break
            if (
                locale == "ru"
                and original_tokens
                and not original_tokens.issubset(identity_tokens(title))
            ):
                report.rejected_fields.add("title")
                report.reasons.append("title_identity_lost")
                break

        for row in dynamic_attributes:
            if not isinstance(row, dict):
                continue
            slug = str(row.get("slug") or "").strip().lower()
            if (
                not slug
                or (product_type and get_dynamic_attribute_spec(product_type, slug) is None)
                or (
                    policy is not None
                    and policy.allowed_dynamic_attributes
                    and slug not in policy.allowed_dynamic_attributes
                )
            ):
                # Запрещённый для домена атрибут просто не применяется (applier
                # его тоже отбрасывает); в rejected_fields — для прозрачности
                # отчёта, но поводом для модерации он не является.
                report.rejected_fields.add(f"dynamic_attributes:{slug or 'unknown'}")
            if looks_untranslated_turkish(row.get("value_ru")) or looks_untranslated_turkish(
                row.get("value_en")
            ):
                report.rejected_fields.add(f"dynamic_attributes:{slug or 'unknown'}")
                report.reasons.append("untranslated_attribute")

        if product_type == "medicines":
            moderator_decisions = attrs.get("medicine_moderator_decisions")
            # Разделы «Не менять» и «Проверено — как есть» решил модератор.
            moderator_decided_fields = {
                field_name
                for field_name, decision in (
                    moderator_decisions.items()
                    if isinstance(moderator_decisions, dict)
                    else ()
                )
                if decision == "keep_current"
            } | moderator_reviewed_medicine_fields(attrs)
            quality = attrs.get("medicine_translation_quality")
            if isinstance(quality, dict):
                for field_name, details in quality.items():
                    if field_name in moderator_decided_fields:
                        continue
                    if isinstance(details, dict) and not details.get("complete", False):
                        report.rejected_fields.add(f"medicine_translation:{field_name}")
                        report.reasons.append(
                            "medicine_fact_mismatch"
                            if details.get("fact_mismatch")
                            else "incomplete_medicine_translation"
                        )
            translations_data = attrs.get("translations_data")
            ru_data = (
                translations_data.get("ru")
                if isinstance(translations_data, dict)
                and isinstance(translations_data.get("ru"), dict)
                else {}
            )
            for field_name, value in ru_data.items():
                if field_name in moderator_decided_fields:
                    continue
                if looks_untranslated_turkish(strip_proper_name_lines(value)):
                    report.rejected_fields.add(f"medicine_translation:{field_name}")
                    report.reasons.append("untranslated_medicine_field")

        report.reasons = list(dict.fromkeys(report.reasons))
        return report

    def _longest_conflicting_category_match(
        self,
        current_category,
        title_text: str,
        locale: str,
        own_match_words: int,
    ) -> str:
        if self.category_index is not None:
            return self.category_index.longest_conflicting_match(
                current_category,
                title_text,
                locale,
                own_match_words,
            )

        from apps.catalog.models import Category

        current_lineage_ids = set()
        current_lineage_slugs = set()
        current_root = ""
        node = current_category
        while node is not None:
            node_pk = getattr(node, "pk", None)
            if node_pk is not None:
                current_lineage_ids.add(node_pk)
            current_root = getattr(node, "slug", "")
            current_lineage_slugs.add(current_root)
            node = getattr(node, "parent", None)

        best = ""
        # Configured semantic kinds also participate when the corresponding
        # catalog category has not been created in this particular database.
        for canonical_kind, config in CATEGORY_POLICY_OVERRIDES.items():
            if canonical_kind in current_lineage_slugs:
                continue
            for alias in (config.get("aliases") or {}).get(locale, ()):
                normalized_alias = _normalized(alias)
                candidate_words, _candidate_length = _alias_specificity(normalized_alias)
                if own_match_words and candidate_words <= own_match_words:
                    continue
                if _alias_specificity(normalized_alias) <= _alias_specificity(best):
                    continue
                if _contains_phrase(title_text, alias):
                    best = normalized_alias

        # Lightweight test/detached objects still receive configured policy
        # validation without requiring a database identity.
        if not getattr(current_category, "pk", None):
            return best

        queryset = (
            Category.objects.filter(is_active=True)
            .select_related("parent")
            .prefetch_related("translations", "global_attribute_keys")
        )
        for candidate in queryset:
            if candidate.pk in current_lineage_ids:
                continue
            # A more specific descendant is compatible with the current kind.
            ancestor = candidate.parent
            is_descendant = False
            while ancestor is not None:
                if ancestor.pk == current_category.pk:
                    is_descendant = True
                    break
                ancestor = ancestor.parent
            if is_descendant:
                continue
            node, is_service, candidate_root = candidate, False, ""
            while node is not None:
                is_service = is_service or node.slug in _SERVICE_ROOT_SLUGS
                candidate_root = node.slug
                node = node.parent
            if is_service or (current_root in _INGREDIENT_ROOT_SLUGS and candidate_root == current_root):
                continue
            candidate_policy = build_category_policy(candidate)
            if candidate_policy is None:
                continue
            for alias in candidate_policy.aliases.get(locale, ()):
                normalized_alias = _normalized(alias)
                candidate_words, _candidate_length = _alias_specificity(normalized_alias)
                if own_match_words and candidate_words <= own_match_words:
                    continue
                if _alias_specificity(normalized_alias) <= _alias_specificity(best):
                    continue
                if _contains_phrase(title_text, alias):
                    best = normalized_alias
        return best
