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
        "sports",
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
_HYPHEN_CODE_RE = re.compile(r"^(?=[A-Z-]*\d)[A-Z0-9]{2,}(?:-[A-Z0-9]+)+$", re.IGNORECASE)
# Строка материала LCW: «Kumaş: Suni Deri», «Kumaş Karışımı: 100% Deri».
_MATERIAL_LINE_RE = re.compile(r"\b(?:Kumaş(?:\s+Karışımı)?|Materyal|Malzeme)\s*:\s*(?:%?\s*\d+\s*%?\s*)?([^\W\d_]+(?:\s+[^\W\d_]+)?)", re.IGNORECASE)
_DIMENSIONS_RE = re.compile(r"\d+(?:[.,]\d+)?(?:[x×]\d+(?:[.,]\d+)?)+", re.IGNORECASE)
# Подзаголовок IKEA в начале описания: «<h3>PAX gardırop, beyaz</h3>».
_IKEA_SUBTITLE_RE = re.compile(r"^\s*<h3>([^<,]+)", re.IGNORECASE)
# Турецкие строчные буквы бренда («Altınyıldız») → латиница: иначе название
# считается непереведённым; бренд ВЕРХНИМ регистром («İMZA») оставляем.
_LATIN_BRAND = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U"})


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
    # Различитель названий моделей без имени (Seniorah): «каблук 10 см» и ещё одно описание.
    heel: tuple[str, str] | None = None
    # Спорттовары: вес, длина или размер мяча из названия — «2 кг», «65 см», «размер 7».
    measure: tuple[str, str] | None = None
    extra_descriptor: bool = False

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


_HEEL_KIND_SUFFIX = "на каблуке"


def _refine_heel_kind(facts: ProductFacts) -> None:
    """«Туфли на каблуке» + «на низком каблуке» → «туфли на низком каблуке»: уточнение
    каблука переходит в тип, а не повторяет его в конце названия."""
    kind = facts.kind
    if kind is None or not kind.ru.endswith(_HEEL_KIND_SUFFIX):
        return
    heel = next(
        (
            pair for pair in facts.descriptors
            if pair[0] != _HEEL_KIND_SUFFIX and (pair[0].endswith(" каблуке") or pair[0] == "на танкетке")
        ),
        None,
    )
    if heel is None:
        return
    base_ru = kind.ru[: -len(_HEEL_KIND_SUFFIX)]
    if kind.en == "Heels":
        en = "Wedges" if heel[1] == "Wedge" else f"{heel[1]}s"
    else:
        en = kind.en.replace("Heeled", heel[1])
    facts.kind = Kind(f"{base_ru}{heel[0]}", kind.gender, en, kind.generic)
    facts.descriptors.remove(heel)


_HEEL_HEIGHT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*cm", re.IGNORECASE)


def _heel_phrase(raw: Any, kind: Kind | None) -> tuple[str, str] | None:
    """«10 cm» у обуви на каблуке → («каблук 10 см», «10 cm heel»); ниже 3 см — не каблук."""
    match = _HEEL_HEIGHT_RE.search(str(raw or "").replace("\xa0", " "))
    if not match or kind is None or ("каблук" not in kind.ru and "шпильк" not in kind.ru and "ботильон" not in kind.ru):
        return None
    value = match.group(1).replace(".", ",")
    if float(value.replace(",", ".")) < 3:
        return None
    return f"каблук {value} см", f"{value.replace(',', '.')} cm heel"


def _attrs(input_data: dict[str, Any]) -> dict[str, Any]:
    attrs = input_data.get("attributes")
    return attrs if isinstance(attrs, dict) else {}


# SuperStep: шаблонный текст магазина (только этот источник). «Kombin Önerileri» — с чем носить
# (модель пересказывала «сочетается с джинсами»), оговорки «проверенных сведений нет» и коды Option —
# не факты (пилот 06.11.2026). Режется строка или предложение (граница — точка, тег, перевод строки).
# Весь текст пустой, только если магазин пишет, что описание ограничено названием и разделом.
_SUPERSTEP_NO_FACTS_RE = re.compile(r"eklenmemiş[^.<\n]*sınırlı\s+tutul", re.IGNORECASE)
_SUPERSTEP_HEADING_RE = re.compile(
    r"Bakım|Ürün Özellikleri|Teknik Özellikler|Ürün Detayları|Sana Sağlayacağı|Kullanım Önerileri"
    r"|Neden\s[^.?!]*Tercih Etmelisin"
)
# После «Kombin Önerileri» режутся подряд идущие советы «с чем носить» — до первого предложения
# без таких слов или до следующего заголовка: заголовков у SuperStep может и не быть.
_SUPERSTEP_OUTFIT_WORDS_RE = re.compile(
    r"kombin|tamamla|eşleştir|birleştir|\bgiy|pantolon|\bjean|şort|tişört|sweatshirt|ceket|gömlek|\betek\b"
    r"|elbise|\bstil|\btarz|\bton\w*|\brenk|görünüm|parça|katman|nötr|aksesuar|\bplan|bedenli|ölçü",
    re.IGNORECASE,
)
_SUPERSTEP_FILLER_RE = re.compile(
    r"[^.?!<>\n]*(?:doğrulanabil\w*|doğrulanama\w*|varyant kodu"
    r"|doğrulanmış\s+(?:[^\s.<]+\s+){0,3}(?:bilgi|veri)\w*)[^.?!<>\n]*[.?!]?",
    re.IGNORECASE,
)


# Поля шаблона с названием, брендом и типом: модель переносила их в описание как есть —
# «Название модели: Lacoste Sport Kadın Relaxed Fit Beyaz Şort» (карточки 06.11.2026). Всё это
# уже есть в названии и характеристиках. Значение — до следующего поля, точки или конца строки.
_SUPERSTEP_FIELD_LABELS = (
    r"Marka|Ürün\s+(?:tipi|adı)|Alt\s+grup|Hedef\s+kullanıcı|Renk|Option|Materyal|Malzeme|Ölçü(?:\s+ve\s+beden)?"
    r"|Teknoloji(?:\s+ve\s+donanım)?|Kalıp|Kesim|Dış\s+(?:taban|yüzey)|Taban|Üst(?:\s+yüzey)?|Astar|Cinsiyet"
    r"|Sezon|Kullanım\s+Alanı|Kumaş|İçerik|Yaka|Kol\s+boyu|Desen|Ürün\s+sayfas\w*(?:\s+[^\s:]+){0,3}"
)
_SUPERSTEP_META_FIELD_RE = re.compile(
    rf"(?:Marka|Ürün\s+(?:tipi|adı)|Alt\s+grup|Hedef\s+kullanıcı)\s*:\s*.*?(?=\s*(?:{_SUPERSTEP_FIELD_LABELS})\s*:|[.;<\n]|$)",
    re.IGNORECASE,
)


# Магазины одного владельца с одним шаблоном текста карточки.
SUPERSTEP_TEXT_SOURCES = frozenset({"superstep", "intersport"})


def product_source(product: Any) -> str:
    """Источник товара по external_id: «superstep-B75806» → «superstep»."""
    return str(getattr(product, "external_id", "") or "").split("-", 1)[0].lower()


def _clean_superstep(text: str) -> str:
    if _SUPERSTEP_NO_FACTS_RE.search(text):
        return ""
    text = _SUPERSTEP_FILLER_RE.sub(" ", text)
    text = re.sub(r"Option\s*/\s*ürün kodu:\s*[^\s<]+", " ", text, flags=re.IGNORECASE)
    return text


def superstep_prompt_text(raw: Any, name: str) -> str:
    """Текст SuperStep для модели: без названия товара и полей шаблона с ним.

    Строится из исходного HTML построчно: поле шаблона в пункте списка без точки
    («<li>Marka: Lacoste</li>») режется до конца строки. Ключ памяти переводов — полный
    текст (``clean_source_text``): названием с цветом отличаются тексты соседних цветов одной
    модели, и старые записи памяти остаются в силе.
    """
    text = clean_source_text(raw, "superstep", keep_lines=True)  # у Intersport правила те же
    if len(name) > 10:
        text = text.replace(name, " ")
    text = _SUPERSTEP_META_FIELD_RE.sub(" ", text)
    text = re.sub(r"[^\S\n]+\.", ".", re.sub(r"(?:[^\S\n]*\.){2,}", ".", text))  # «Ürün Özellikleri . . .»
    lines = (re.sub(r"[^\S\n]+", " ", line).strip(" ,.") for line in text.split("\n"))
    return "\n".join(line for line in lines if re.search(r"[^\W\d_]", line))


def _cut_outfit_tips(text: str) -> str:
    match = re.search(r"Kombin Önerileri\s*", text)
    if not match:
        return text
    rest = text[match.end() :]
    heading = _SUPERSTEP_HEADING_RE.search(rest)
    section, tail = (rest[: heading.start()], rest[heading.start() :]) if heading else (rest, "")
    sentences = re.split(r"(?<=[.!?])\s+", section.strip())
    while sentences and _SUPERSTEP_OUTFIT_WORDS_RE.search(sentences[0]):
        sentences.pop(0)
    return " ".join(part for part in (text[: match.start()].strip(), " ".join(sentences), tail) if part)


def clean_source_text(value: Any, source: str = "", *, keep_lines: bool = False) -> str:
    """Текст источника без HTML, кодов LCW и юридического хвоста; ``source`` — product_source().

    ``keep_lines`` — границы абзацев и пунктов списка остаются переводами строк (текст для модели:
    поле шаблона без точки режется до конца строки, а не до первой точки). Ключ памяти — без него.
    """
    text = str(value or "")
    for _ in range(2):  # у части источников HTML экранирован дважды
        text = html.unescape(text)
    if source in SUPERSTEP_TEXT_SOURCES:
        text = _clean_superstep(text)
    if keep_lines:
        text = re.sub(r"<br\s*/?>|</(?:p|li|div|h[1-6]|tr|ul|ol)>", "\n", text, flags=re.IGNORECASE)
    spaces = r"[^\S\n]+" if keep_lines else r"\s+"
    text = re.sub(r"<[^>]+>", " ", text)
    if source in SUPERSTEP_TEXT_SOURCES:
        text = _cut_outfit_tips(re.sub(spaces, " ", text))
    text = re.sub(r"Ürün Kodu:\s*\S+", " ", text)
    text = re.sub(r"\bS\d{6,}\b", " ", text)
    text = re.sub(r"(?:İmalatçı|Imalatçı)\s*/.*$", " ", text, flags=re.DOTALL)
    text = re.sub(r"Ürün İçeriği ve Özellikleri", " ", text)
    # Остаток шапки LCW: « - 26865 - Renksiz - NIVEA MEN…» → «NIVEA MEN…»
    text = re.sub(r"^(?:\s*-\s*[^-]{1,30}?(?=\s+-))+\s*-\s*", " ", text)
    text = re.sub(spaces, " ", text)
    if keep_lines:
        text = re.sub(r" *\n[\s]*", "\n", text)
    return text.strip(" -\n")


# «PC-5112-3892 Taba-Erkek Sandalet», «Vizon-Erkek»: цвет и пол слитно через дефис.
_HYPHEN_AUDIENCE_RE = re.compile(r"(?<=[^\W\d_])-(?=(?:erkek|kad[iı]n|unisex|[cç]ocuk)\b)", re.IGNORECASE)


def _clean_name(name: str) -> str:
    text = vocab.TITLE_NOISE_RE.sub(" ", str(name or ""))
    text = _HYPHEN_AUDIENCE_RE.sub(" ", text)
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


# Спорттовары: «2Kg», «0,5Kg», «65cm», «55-59cm», «6 mm», «14OZ», «27 inç» и размер мяча
# («7 No», «No 5», «7 Numara»). В название идёт первое найденное, по-русски.
_MEASURE_UNITS = {"kg": ("кг", "kg"), "cm": ("см", "cm"), "mm": ("мм", "mm"), "oz": ("унций", "oz"), "inc": ("дюймов", "in")}
_MEASURE_RE = re.compile(
    r"(?<![\w.,])(\d+(?:[.,]\d+)?(?:\s*-\s*\d+(?:[.,]\d+)?)?)\s*(kg|cm|mm|oz|inç|inc)\b", re.IGNORECASE
)
_BALL_SIZE_RE = re.compile(r"(?<![\w.,])(?:(\d)\s*(?:no|numara)\b\.?|no\.?\s*(\d)(?![\w.,]))", re.IGNORECASE)


def _extract_measure(text: str) -> tuple[str, tuple[str, str] | None]:
    match = _MEASURE_RE.search(text)
    if match:
        amount = re.sub(r"\s*-\s*", "–", match.group(1))
        ru_unit, en_unit = _MEASURE_UNITS[vocab.fold(match.group(2))]
        measure = (f"{amount.replace('.', ',')} {ru_unit}", f"{amount.replace(',', '.')} {en_unit}")
    else:
        match = _BALL_SIZE_RE.search(text)
        if not match:
            return text, None
        size = match.group(1) or match.group(2)
        measure = (f"размер {size}", f"Size {size}")
    return re.sub(r"\s+", " ", text[: match.start()] + " " + text[match.end() :]).strip(), measure


def _is_model_token(token: str) -> bool:
    """Латинский токен бренда/модели/кода: без турецких букв."""
    stripped = token.strip("()[],.;:")
    if not stripped or _TURKISH_CHARS_RE.search(stripped) or _CYRILLIC_RE.search(stripped):
        return False
    return bool(re.search(r"[A-Za-z0-9]", stripped))


def is_supplier_code(token: str) -> bool:
    """Артикул поставщика («LV04RF822G», «12295132», «4480», «Tb0a6vdpenx1»): в название не идёт.

    Габариты «13x10x6» — не артикул.
    """
    stripped = token.strip("()[],.;:")
    digits = sum(char.isdigit() for char in stripped)
    long_code = digits >= 3 and len(stripped) >= 12 and stripped.isalnum()
    return (digits >= 4 or long_code) and not _DIMENSIONS_RE.fullmatch(stripped)


def drop_codes(tokens: list[str], *, leading_number: bool = False) -> list[str]:
    """Убирает артикулы, короткие коды цвета за ними («DM0DM22546 BDS») и проценты состава («%100»).

    ``leading_number`` — первый токен стоит сразу за брендом: четыре цифры там —
    модель («New Balance 9060», «New Balance 2002»), а не артикул.
    """
    result: list[str] = []
    after_sku = False
    previous_kept = False
    for position, token in enumerate(tokens):
        stripped = token.strip("()[],.;:")
        # Четыре цифры сразу за словом модели — номер модели («Emr 1830»),
        # отдельно («Tişört 4480», «Sandalet 5003») — артикул. Пустой токен — разрыв.
        model_number = stripped.isdigit() and len(stripped) == 4 and (previous_kept or (leading_number and position == 0))
        # Размер «M» в «PC-7315 M Kahve». Только латиница: русские «с», «в», «и» в LLM-названии — слова.
        single_letter = len(stripped) == 1 and stripped.isascii() and stripped.isalpha()
        if not stripped or single_letter or "%" in stripped or (is_supplier_code(stripped) and not model_number) or (
            after_sku and len(stripped) <= 3 and stripped.upper() == stripped
        ):
            after_sku = bool(stripped)
            previous_kept = False
            continue
        after_sku = False
        previous_kept = True
        result.append(token)
    return result


def supplier_code_tokens(name: str) -> set[str]:
    """Токены названия (ВЕРХНИЙ регистр), которые правила считают артикулом и не пишут.

    Артикул с точкой («408048.M5FX») возвращается и частями: проверка идентичности
    делит токены по точке, и без этого «M5FX» требовался в названии.
    """
    tokens = str(name or "").split()
    kept = {token.strip("()[],.;:").upper() for token in drop_codes(tokens)}
    codes = {token.strip("()[],.;:").upper() for token in tokens} - kept
    return codes | {part for code in codes if "." in code for part in code.split(".") if part}


def _is_hyphen_model(token: str) -> bool:
    """«Sk8-Hi», «XT-6», «RS-X» — модель, а не код вида «J5SM-TST7325» или «PC-7315»."""
    parts = token.strip("()[],.;:").split("-")
    return len(parts) == 2 and all(parts) and sum(char.isdigit() for char in token) <= 2


# «Lacoste AG-LT23 Ultra», «McKinley MG30-1»: буквы, до двух цифр, дефис, короткий хвост — модель,
# если стоит сразу за брендом. «PC-7315», «J5SM-TST7325», «PC-5112-3892» — артикулы.
BRAND_MODEL_CODE_RE = re.compile(r"^[A-Za-z]{2,}\d{0,2}-[A-Za-z]{0,3}\d{1,2}$")


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


def _strip_brand(text: str, brand: str) -> str:
    """«Us. Polo Assn. Erkek Tişört» при бренде «U.S. Polo Assn.» → «Erkek Tişört».

    Бренд в названии пишут с другими точками и пробелами; его слова иначе разбираются
    как словарные («Polo» — тип «поло», 20802 в партии FLO 27.10.2026).
    """
    letters = re.sub(r"[\W_]+", "", vocab.fold(brand))
    if len(letters) < 3 or not letters.isascii():
        return text
    pattern = r"(?<![^\W_])" + r"[\W_]*".join(map(re.escape, letters)) + r"\.?(?![^\W_])"
    return re.sub(r"\s+", " ", re.sub(pattern, " ", text, flags=re.IGNORECASE)).strip()


def parse_name(name: str, facts: ProductFacts) -> None:
    """Разбор турецкого названия на тип, пол, описательные слова, цвет и модель."""
    text, volume = _extract_volume(_clean_name(name))
    if facts.brand:
        text = _strip_brand(text, facts.brand)
    if volume:
        facts.volume = volume
    if facts.product_type == "sports":
        text, facts.measure = _extract_measure(text)
        text = re.sub(r"\b(\d+)(l[iıuü])\b", r"\1'\2", text)  # «3lü Tenis Topu» — упаковка, как «3'lü»
    pack = _PACK_RE.search(text)
    if pack:
        facts.pack = (f"{pack.group(1)} шт.", f"{pack.group(1)}-Pack")
        text = (text[: pack.start()] + text[pack.end() :]).strip()
    tokens = _TOKEN_RE.findall(text)
    folded = [vocab.fold(token) for token in tokens]
    brand_tokens = {vocab.fold(part) for part in facts.brand.split()} if facts.brand else set()
    descriptive = vocab.fold(facts.brand) in vocab.DESCRIPTIVE_NAME_BRANDS
    seen_vocab = False
    mappings = [(vocab.KINDS, "kind"), (vocab.AUDIENCE, "audience"), (vocab.DESCRIPTORS, "descriptor")]
    if facts.product_type == "shoes":
        mappings += [(vocab.SHOE_KINDS, "kind"), (vocab.SHOE_DESCRIPTORS, "descriptor")]
    if facts.product_type == "sports":
        mappings += [(vocab.SPORTS_KINDS, "kind"), (vocab.SPORTS_DESCRIPTORS, "descriptor")]
    model: list[str] = []
    kinds: list[Kind] = []
    index = 0
    while index < len(tokens):
        token, key = tokens[index], folded[index].strip("()[],.;:")
        # «® | PC-5112-3892 Taba-Erkek Sandalet»: знаки без букв и цифр — не слова названия.
        if not key or key in ("-", "–") or (not re.search(r"\w", key) and token not in ("&", "/", "+")):
            index += 1
            continue
        # Самая длинная фраза из всех словарей: «Polo Yaka» — вырез, а не тип «поло».
        length, value, target = 0, None, None
        for mapping, label in mappings:
            found, found_value = _match_phrase(folded, index, mapping)
            if found > length:
                length, value, target = found, found_value, label
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
            if model and model[-1]:
                model.append("")  # разрыв: «Barcelona Urban … Sandalet 5003»
            continue
        brand_word = key in brand_tokens and " ".join(folded[index : index + 2]) not in vocab.BRAND_WORD_PHRASES
        model_code = bool(facts.brand) and not model and not seen_vocab and BRAND_MODEL_CODE_RE.match(token.strip("()[],.;:"))
        if brand_word or (_HYPHEN_CODE_RE.match(token) and not _is_hyphen_model(token) and not model_code):
            index += 1
            continue
        if token in ("&", "/", "+") and model:
            model.append(token)
        elif _is_strong_model_token(token) or (not seen_vocab and not descriptive and _is_model_token(token)):
            model.append(token)
        else:
            facts.untranslated.append(token)
            if model and model[-1]:
                model.append("")
        index += 1
    specific = [kind for kind in kinds if not kind.generic]
    if specific:
        facts.kind = specific[0]
    elif kinds:
        facts.kind = kinds[0]
    # Номер сразу за брендом («New Balance 9060 Lifestyle») — модель только у брендов с
    # числовыми моделями; у остальных («Pierre Cardin 6205») — артикул.
    leading_number = vocab.fold(facts.brand) in vocab.NUMERIC_MODEL_BRANDS and bool(model) and bool(tokens) and model[0] == tokens[0]
    facts.model = " ".join(drop_codes(model, leading_number=leading_number)).strip(" &/+")


def _starts_vocab(folded: list[str], index: int) -> bool:
    for mapping in (vocab.KINDS, vocab.AUDIENCE, vocab.DESCRIPTORS):
        if _match_phrase(folded, index, mapping)[0]:
            return True
    return bool(_match_color(folded, index)[0]) or bool(_VOLUME_RE.match(" ".join(folded[index : index + 2])))


def _leading_brand(name: str) -> tuple[str, str]:
    """«TUDORS Siyah Erkek Kemer» → («TUDORS», «Siyah Erkek Kemer»).

    У мультибрендового магазина (LC Waikiki продаёт Loris, AVON, NIVEA…)
    бренд товара — слова названия до первого словарного слова.
    """
    tokens = _TOKEN_RE.findall(_clean_name(name))
    folded = [vocab.fold(token) for token in tokens]
    for index in range(len(tokens)):
        if _starts_vocab(folded, index) or tokens[index] in ("-", "–"):
            break
    else:
        return "", name
    leading = tokens[:index]
    words = [token for token in leading if token not in ("/", "&", "+")]
    if not words or len(words) > 4 or not any(_match_phrase(folded, i, vocab.KINDS)[0] for i in range(index, len(tokens))):
        return "", name
    if any(not word[:1].isupper() or vocab.fold(word) in vocab.NOT_BRAND_WORDS for word in words):
        return "", name
    brand = " ".join(leading).replace("(R)", "").strip(" /&+")
    if re.search(r"[çğıöşü]", brand):
        brand = brand.translate(_LATIN_BRAND)
    return brand, " ".join(tokens[index:])


def _strip_own_line(name: str) -> str:
    """«LCW ACCESSORIES Dark Black Edp…» → «Dark Black Edp…»: линейка магазина
    — тот же бренд, а следующие слова (название аромата) остаются."""
    tokens = name.split()
    if tokens and vocab.fold(" ".join(tokens[:2])) == "lc waikiki":
        return " ".join(tokens[2:])
    if tokens and vocab.fold(tokens[0]) == "lcw":
        rest = tokens[1:]
        if rest and rest[0].isalpha() and rest[0].isupper():
            rest = rest[1:]
        return " ".join(rest)
    return name


def _source_material(source_text: str) -> str:
    """«Kumaş: Suni Deri», «Kumaş Karışımı: 100% Deri» → канон материала аксессуара."""
    # Склейка строк LCW: «Suni DeriDesen: Düz» → «Suni Deri Desen: Düz».
    text = re.sub(r"(?<=[a-zçğıöşü])(?=[A-ZÇĞİÖŞÜ])", " ", source_text or "")
    match = _MATERIAL_LINE_RE.search(text)
    if not match:
        return ""
    words = vocab.fold(match.group(1)).split()
    for length in (2, 1):
        material = vocab.ACCESSORY_MATERIALS.get(" ".join(words[:length]))
        if material:
            return material
    return ""


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
    # «Dockers by Gerli’nin …» — турецкий притяжательный суффикс не часть бренда.
    return re.sub(r"[’'](?:n?[iıuü]n|[iıuü]n?)$", "", " ".join(prefix)).strip(" -,")


def _ikea_subtitle(description: Any) -> str:
    match = _IKEA_SUBTITLE_RE.match(str(description or ""))
    return html.unescape(match.group(1)).strip() if match else ""


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
    source_text = clean_source_text(input_data.get("raw_description") or input_data.get("description"), product_source(product))
    if vocab.fold(facts.brand) in vocab.STORE_BRANDS and not _CYRILLIC_RE.search(name):
        leading, rest = _leading_brand(name)
        if vocab.fold(leading).startswith(vocab.STORE_OWN_LINE_PREFIXES):
            name = _strip_own_line(name)
        elif leading:
            name, facts.brand = rest, leading

    if _CYRILLIC_RE.search(name):
        facts.russian_name = re.sub(r"\s+", " ", _PRICE_RE.sub(" ", name)).strip(" -")
        # Латиница русского названия — бренд/модель для EN («Кепка JEEP® с деталями»).
        brand_words = {vocab.fold(word) for word in facts.brand.split()}
        facts.model = " ".join(
            token
            for token in _TOKEN_RE.findall(facts.russian_name)
            if _is_model_token(token)
            and re.search(r"[A-Za-z]{2}", token)  # «(2», «3», «1» из «3 в 1» — не модель
            and vocab.fold(token) not in brand_words
            and not _HYPHEN_CODE_RE.match(token)
        )
        facts.model = " ".join(drop_codes(facts.model.split()))
    elif product_type == "furniture":
        facts.model = name.strip()
    else:
        parse_name(name, facts)
        if not facts.brand and not facts.model:
            facts.brand = _brand_from_description(name, source_text)

    category = getattr(product, "category", None)
    category_kind = vocab.CATEGORY_KINDS.get(getattr(category, "slug", "") or "")
    if product_type == "furniture":
        # Тип IKEA: furniture_type, иначе подзаголовок описания. Тип, которого
        # нет в словаре, не подменяем типом категории («KOMPLEMENT tel sepet» в
        # «Шкафах» — не гардероб): название тогда пишет LLM.
        type_names = [
            value
            for value in (attrs.get("furniture_type"), _ikea_subtitle(input_data.get("raw_description") or input_data.get("description")))
            if str(value or "").strip()
        ]
        kinds = [kind for kind in map(_furniture_kind, type_names) if kind]
        facts.kind = kinds[0] if kinds else (None if type_names else category_kind)
        if not facts.has_variants and not attrs.get("furniture_variants"):
            facts.finish = vocab.translate_furniture_finish(attrs.get("color"))
    elif facts.kind is None or (facts.kind.generic and category_kind):
        facts.kind = category_kind or facts.kind
    if facts.kind is not None:
        facts.kind = vocab.BRAND_KINDS.get((vocab.fold(facts.brand), facts.kind.ru), facts.kind)
    if facts.kind is not None and facts.kind.ru in vocab.JACKET_KINDS:
        words = vocab.fold(facts.model).split()
        facts.kind = next((vocab.MODEL_WORD_KINDS[word] for word in words if word in vocab.MODEL_WORD_KINDS), facts.kind)
    if product_type == "perfumery" and (facts.kind is None or facts.kind.generic):
        fragrance_type = vocab.fold(attrs.get("fragrance_type"))
        facts.kind = vocab.KINDS.get(fragrance_type, facts.kind)

    if product_type == "shoes":
        _refine_heel_kind(facts)
        if product_source(product) == "seniorah" and not facts.model:
            # У магазина модели без имени («Cilt Bilek Bağlı Kadın Topuklu Ayakkabı» — две
            # разные модели): различают деталь, которую срезал лимит, и высота каблука.
            facts.extra_descriptor = True
            facts.heel = _heel_phrase(attrs.get("heel_height"), facts.kind)
    if facts.audience is None:
        facts.audience = vocab.AUDIENCE.get(vocab.fold(attrs.get("gender")))
    if product_type == "sports" and facts.audience == vocab.AUDIENCE["unisex"]:
        facts.audience = None  # «мяч унисекс» не говорят; «детские», «женские» остаются
    if facts.has_variants or product_type == "perfumery":
        facts.color = None  # у парфюма цвет — флакон, в название не идёт
    elif facts.color is None and product_type != "furniture":
        facts.color = vocab.translate_color(attrs.get("color"))

    facts.composition = vocab.translate_composition(attrs.get("composition") if isinstance(attrs.get("composition"), str) else source_text)
    if product_type == "shoes":
        facts.upper = vocab.translate_shoe_material(attrs.get("material"))
        facts.lining = vocab.translate_shoe_material(attrs.get("lining"))
        facts.sole = vocab.translate_shoe_material(attrs.get("sole_material"))
    material = ""
    if product_type == "accessories":
        material = _source_material(source_text) or (attrs.get("material") if isinstance(attrs.get("material"), str) else "")
    if material:
        material = material.strip()
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
