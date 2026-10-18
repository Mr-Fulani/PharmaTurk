"""Структурированные факты товара из названия и атрибутов парсера (без LLM)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any

from apps.ai.services.rules import vocab
from apps.ai.services.rules.vocab import Color, Kind

# Типы, для которых тексты собираются правилами (LLM — только перевод описания).
RULE_PRODUCT_TYPES = frozenset(
    {
        "clothing",
        "shoes",
        "underwear",
        "headwear",
        "islamic_clothing",
        "accessories",
        "perfumery",
        "furniture",
    }
)
# Заглушки бренда в каталоге: настоящий бренд ищем в названии/описании.
PLACEHOLDER_BRANDS = frozenset({"", "другое", "other", "unknown", "markalar", "без бренда"})

_CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)
_TURKISH_CHARS_RE = re.compile(r"[çğışöüÇĞİŞÖÜ]")
_PRICE_RE = re.compile(r"\b\d+[.,]\d{2}\s*(?:TL|TRY)?\b|\b\d+\s*(?:TL|TRY)\b", re.IGNORECASE)
_VOLUME_RE = re.compile(
    r"\b(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*ml\b", re.IGNORECASE
)
_TOKEN_RE = re.compile(r"[^\s]+")
_PACK_RE = re.compile(r"\b(\d+)\s*'\s*l[iıuü]\S*(?:\s+paket\S*)?", re.IGNORECASE)
_CYRILLIC_SUFFIX_RE = re.compile(r"\s+-\s+[а-яё\s-]+$", re.IGNORECASE)
# Коды вида «J5SM-TST7325»: санитайзер названий вырезает их, в модель не берём.
_HYPHEN_CODE_RE = re.compile(r"^[A-Z0-9]{2,}-[A-Z0-9]+$", re.IGNORECASE)


@dataclass
class ProductFacts:
    product_type: str
    kind: Kind | None = None
    audience: tuple[str, str] | None = None
    brand: str = ""
    model: str = ""
    descriptors: list[tuple[str, str]] = field(default_factory=list)
    color: Color | None = None
    composition: tuple[str, str] | None = None
    upper: tuple[str, str] | None = None
    lining: tuple[str, str] | None = None
    sole: tuple[str, str] | None = None
    material: tuple[str, str] | None = None
    volume: tuple[str, str] | None = None
    pack: tuple[str, str] | None = None
    finish: tuple[str, str] | None = None
    russian_name: str = ""
    untranslated: list[str] = field(default_factory=list)
    has_variants: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Снимок для input_data лога (для разбора в админке)."""
        return {
            "kind": self.kind.ru if self.kind else "",
            "kind_en": self.kind.en if self.kind else "",
            "audience": self.audience[1] if self.audience else "",
            "brand": self.brand,
            "model": self.model,
            "color": self.color.en if self.color else "",
            "composition": self.composition[1] if self.composition else "",
            "volume": self.volume[1] if self.volume else "",
            "untranslated": self.untranslated,
        }


def _attrs(input_data: dict[str, Any]) -> dict[str, Any]:
    attrs = input_data.get("attributes")
    return attrs if isinstance(attrs, dict) else {}


def clean_source_text(value: Any) -> str:
    """Текст источника без HTML, кодов LCW и юридического хвоста."""
    text = str(value or "")
    for _ in range(2):  # у части источников HTML экранирован дважды
        text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"Ürün Kodu:\s*\S+", " ", text)
    text = re.sub(r"\bS\d{6,}\b", " ", text)
    text = re.sub(r"(?:İmalatçı|Imalatçı)\s*/.*$", " ", text, flags=re.DOTALL)
    text = re.sub(r"Ürün İçeriği ve Özellikleri", " ", text)
    # Остаток шапки LCW: « - 26865 - Renksiz - NIVEA MEN…» → «NIVEA MEN…»
    text = re.sub(r"^(?:\s*-\s*[^-]{1,30}?(?=\s+-))+\s*-\s*", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -")


def _clean_name(name: str) -> str:
    text = vocab.TITLE_NOISE_RE.sub(" ", str(name or ""))
    text = _PRICE_RE.sub(" ", text)
    text = re.sub(r"\s+-\s*$|^\s*-\s+", " ", text)
    text = re.sub(r"\s+-\s+-?\s*", " - ", text)
    return re.sub(r"\s+", " ", text).strip(" -")


def _extract_volume(text: str) -> tuple[str, tuple[str, str] | None]:
    match = _VOLUME_RE.search(text)
    if not match:
        return text, None
    count, amount = match.group(1), match.group(2).replace(".", ",")
    ru = f"{count} × {amount} мл" if count else f"{amount} мл"
    en = f"{count} × {amount.replace(',', '.')} ml" if count else f"{amount.replace(',', '.')} ml"
    return (text[: match.start()] + text[match.end() :]).strip(), (ru, en)


def _is_model_token(token: str) -> bool:
    """Латинский токен бренда/модели/кода: без турецких букв."""
    stripped = token.strip("()[],.;:")
    if not stripped or _TURKISH_CHARS_RE.search(stripped) or _CYRILLIC_RE.search(stripped):
        return False
    return bool(re.search(r"[A-Za-z0-9]", stripped))


def _is_strong_model_token(token: str) -> bool:
    """После описательных слов допустимы только коды и ВЕРХНИЙ регистр."""
    stripped = token.strip("()[],.;:")
    if not _is_model_token(stripped):
        return False
    has_digit = any(char.isdigit() for char in stripped)
    letters = [char for char in stripped if char.isalpha()]
    return has_digit or (len(letters) >= 2 and stripped.upper() == stripped)


def _match_phrase(folded: list[str], start: int, mapping: dict, max_len: int = 5):
    for length in range(min(max_len, len(folded) - start), 0, -1):
        phrase = " ".join(folded[start : start + length]).strip("()[],.;:")
        if phrase in mapping:
            return length, mapping[phrase]
    return 0, None


def _match_color(folded: list[str], start: int):
    for length in range(min(3, len(folded) - start), 0, -1):
        color = vocab.translate_color(" ".join(folded[start : start + length]))
        if color is not None:
            return length, color
    return 0, None


def parse_name(name: str, facts: ProductFacts) -> None:
    """Разбор турецкого названия на тип, пол, описательные слова, цвет и модель."""
    text, volume = _extract_volume(_clean_name(name))
    if volume:
        facts.volume = volume
    pack = _PACK_RE.search(text)
    if pack:
        facts.pack = (f"{pack.group(1)} шт.", f"{pack.group(1)}-Pack")
        text = (text[: pack.start()] + text[pack.end() :]).strip()
    tokens = _TOKEN_RE.findall(text)
    folded = [vocab.fold(token) for token in tokens]
    brand_tokens = {vocab.fold(part) for part in facts.brand.split()} if facts.brand else set()
    seen_vocab = False
    model: list[str] = []
    kinds: list[Kind] = []
    index = 0
    while index < len(tokens):
        token, key = tokens[index], folded[index].strip("()[],.;:")
        if not key or key in ("-", "–"):
            index += 1
            continue
        for mapping, target in (
            (vocab.KINDS, "kind"),
            (vocab.AUDIENCE, "audience"),
            (vocab.DESCRIPTORS, "descriptor"),
        ):
            length, value = _match_phrase(folded, index, mapping)
            if length:
                break
        else:
            target = None
        if target is None:
            length, value = _match_color(folded, index)
            target = "color" if length else None
        if target == "kind":
            kinds.append(value)
        elif target == "audience":
            facts.audience = value
        elif target == "descriptor" and value[0]:
            if value not in facts.descriptors:
                facts.descriptors.append(value)
        elif target == "color":
            facts.color = facts.color or value
        if target:
            seen_vocab = True
            index += length
            continue
        if key in brand_tokens or _HYPHEN_CODE_RE.match(token):
            index += 1
            continue
        if token in ("&", "/", "+") and model:
            model.append(token)
        elif _is_strong_model_token(token) or (not seen_vocab and _is_model_token(token)):
            model.append(token)
        else:
            facts.untranslated.append(token)
        index += 1
    specific = [kind for kind in kinds if not kind.generic]
    if specific:
        facts.kind = specific[0]
    elif kinds:
        facts.kind = kinds[0]
    facts.model = " ".join(model).strip(" &/+")


def _variant_colors(product) -> int:
    domain = getattr(product, "domain_item", None)
    manager = getattr(domain, "variants", None) if domain is not None else None
    if manager is None:
        return 0
    try:
        return manager.filter(is_active=True).count()
    except Exception:
        return 0


def _brand_from_description(name: str, source_text: str) -> str:
    """«U.S. Polo Assn. Erkek Tişört» при названии «Erkek Tişört» → «U.S. Polo Assn.»."""
    clean = _clean_name(name)
    if not clean or not source_text:
        return ""
    position = vocab.fold(source_text).find(vocab.fold(clean))
    # Бренд стоит в самом начале текста, перед повтором названия.
    if position <= 0 or position > 40:
        return ""
    prefix = source_text[:position].split()
    if not prefix or len(prefix) > 4 or not all(_is_model_token(word) for word in prefix):
        return ""
    # Отдельное слово-тип допустимо («U.S. Polo Assn.»), описательное — нет.
    vocabulary = (vocab.AUDIENCE, vocab.DESCRIPTORS, vocab.COLORS, vocab.FIBERS)
    if vocab.fold(" ".join(prefix)) in vocab.KINDS or any(
        vocab.fold(word) in mapping for word in prefix for mapping in vocabulary
    ):
        return ""
    return " ".join(prefix).strip(" -,")


def _furniture_kind(raw_type: Any) -> Kind | None:
    words = str(raw_type or "").split()
    while words and words[0].isupper() and len(words) > 1:
        words.pop(0)  # «PAX gardırop» → «gardırop»
    key = vocab.fold(" ".join(words))
    if key in vocab.FURNITURE_KINDS:
        return vocab.FURNITURE_KINDS[key]
    match = vocab.FURNITURE_DRAWER_CHEST_RE.match(key)
    if match:
        count = match.group(1)
        return Kind(f"комод с {count} ящиками", vocab.M, f"Chest of {count} Drawers")
    return None


def collect_facts(product, input_data: dict[str, Any]) -> ProductFacts:
    product_type = str(getattr(product, "product_type", "") or "")
    attrs = _attrs(input_data)
    facts = ProductFacts(product_type=product_type)
    brand = str(input_data.get("brand") or "").strip()
    if brand.casefold() not in PLACEHOLDER_BRANDS and "markalar" not in vocab.fold(input_data.get("name")):
        facts.brand = brand
    facts.has_variants = _variant_colors(product) > 0  # цвет вариант допишет сам
    # FLO дописывает к турецкому названию русский цвет: «… Sneaker - Серый».
    name = _CYRILLIC_SUFFIX_RE.sub("", str(input_data.get("name") or ""))
    source_text = clean_source_text(input_data.get("raw_description") or input_data.get("description"))

    if _CYRILLIC_RE.search(name):
        facts.russian_name = re.sub(r"\s+", " ", _PRICE_RE.sub(" ", name)).strip(" -")
    elif product_type == "furniture":
        facts.model = name.strip()
    else:
        parse_name(name, facts)
        if not facts.brand and not facts.model:
            facts.brand = _brand_from_description(name, source_text)

    category = getattr(product, "category", None)
    category_kind = vocab.CATEGORY_KINDS.get(getattr(category, "slug", "") or "")
    if product_type == "furniture":
        facts.kind = _furniture_kind(attrs.get("furniture_type"))
        if not facts.has_variants and not attrs.get("furniture_variants"):
            facts.finish = vocab.translate_furniture_finish(attrs.get("color"))
    elif facts.kind is None or (facts.kind.generic and category_kind):
        facts.kind = category_kind or facts.kind
    if product_type == "perfumery" and (facts.kind is None or facts.kind.generic):
        fragrance_type = vocab.fold(attrs.get("fragrance_type"))
        facts.kind = vocab.KINDS.get(fragrance_type, facts.kind)

    if facts.audience is None:
        facts.audience = vocab.AUDIENCE.get(vocab.fold(attrs.get("gender")))
    if facts.has_variants:
        facts.color = None
    elif facts.color is None and product_type != "furniture":
        facts.color = vocab.translate_color(attrs.get("color"))

    facts.composition = vocab.translate_composition(attrs.get("composition") if isinstance(attrs.get("composition"), str) else source_text)
    if product_type == "shoes":
        facts.upper = vocab.translate_shoe_material(attrs.get("material"))
        facts.lining = vocab.translate_shoe_material(attrs.get("lining"))
        facts.sole = vocab.translate_shoe_material(attrs.get("sole_material"))
    if product_type == "accessories" and isinstance(attrs.get("material"), str):
        material = attrs["material"].strip()
        from apps.catalog.attribute_specs import english_for_canonical_ru

        english = english_for_canonical_ru(material)
        if english:
            facts.material = (material.lower(), english.lower())
            phrase = vocab.MATERIAL_PHRASES.get(material.lower())
            if phrase and not any(ru.startswith("из ") for ru, _ in facts.descriptors):
                facts.descriptors.append(phrase)
    if product_type == "perfumery" and facts.volume is None and attrs.get("volume"):
        _, facts.volume = _extract_volume(str(attrs["volume"]).split("/")[0])
    return facts
