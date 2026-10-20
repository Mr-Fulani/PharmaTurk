"""Сверка перевода абзаца инструкции с турецким исходником без LLM.

Пакетный перевод (десятки абзацев в одном JSON) иногда сдвигает ответы:
ключу «5» достаётся перевод абзаца «6» и так до конца запроса. Проверки
дозировок такое не видят, если в абзацах нет чисел с единицами. В памяти
``medicine_paragraph`` 20.10.2026 так испорчено около 21 % записей
(«Papiller nekroz» → «Храните при температуре ниже 25°C»).

Сравниваются признаки, которые переживают перевод: все числа, медицинские
понятия по словарю TR/RU/EN, длина (модель Гейла–Чёрча), номер заголовка,
частота побочного эффекта, метка {BRAND} и знак в конце абзаца.

- ``item_problems`` — правила для одного абзаца (входят в ``paragraph_problems``);
- ``request_shift`` — сдвиг внутри одного ответа модели: перевод ближе к
  соседнему исходнику, чем к своему; отбрасывается цепочка таких абзацев;
- ``audit_sequence`` — то же для записей памяти в порядке pk (команда
  ``medicine_paragraph_audit``).

Пороги подобраны по выгрузке памяти 20.10.2026 (270 945 записей) и ручной
разметке 120 случайных записей; цифры — в docs/MEDICINE_PARAGRAPH_SHIFT_2026-10-20.md.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Optional, Sequence

from apps.ai.services.medicine_fact_check import _normalize_number

_BRAND = "{BRAND}"  # medicine_memory.BRAND_TOKEN

# ── Числа ─────────────────────────────────────────────────────────────────

_NUMBER_WORDS = {
    "tr": {
        "iki": 2, "ikinci": 2, "üç": 3, "üçüncü": 3, "dört": 4, "dördüncü": 4, "beş": 5, "yedi": 7,
        "sekiz": 8, "dokuz": 9, "on": 10, "yirmi": 20, "otuz": 30, "yüz": 100, "bin": 1000,
    },
    "ru": {
        "два": 2, "две": 2, "двух": 2, "двум": 2, "двумя": 2, "дважды": 2,
        "три": 3, "трех": 3, "трёх": 3, "трем": 3, "трём": 3, "тремя": 3, "трижды": 3,
        "четыре": 4, "четырех": 4, "четырёх": 4, "пять": 5, "пяти": 5, "шесть": 6, "шести": 6,
        "семь": 7, "семи": 7, "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9,
        "десять": 10, "десяти": 10, "двенадцать": 12, "двенадцати": 12,
        "двадцать": 20, "двадцати": 20, "тридцать": 30, "тридцати": 30,
        "второй": 2, "второго": 2, "второму": 2, "вторым": 2, "второе": 2, "вторая": 2, "вторую": 2,
        "третий": 3, "третьего": 3, "третьей": 3, "третье": 3, "третья": 3, "третью": 3,
        "четвертый": 4, "четвёртый": 4, "четвертого": 4, "четвёртого": 4, "четвертой": 4, "четвёртой": 4,
        "четвертая": 4, "четвёртая": 4, "четвертую": 4, "четвёртую": 4,
        "сто": 100, "тысяча": 1000, "тысячи": 1000, "тысяч": 1000,
    },
    "en": {
        "two": 2, "twice": 2, "three": 3, "thrice": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "twenty": 20, "thirty": 30,
        "second": 2, "third": 3, "fourth": 4, "hundred": 100, "thousand": 1000,
    },
}
# «on bin» = 10 000: составные числа частот («10 000 hastanın birinde»).
_NUMBER_PHRASES = {
    "tr": ((r"\bon bin\b", "10000"),),
    "ru": ((r"\bдесят[ьи] тысяч\b", "10000"),),
    "en": ((r"\bten thousand\b", "10000"),),
}
# «IV» не переводим: так пишут «внутривенно» (İ.V. → IV).
_ROMAN = {"II": "2", "III": "3", "VI": "6", "VII": "7", "VIII": "8", "IX": "9", "XII": "12"}
_ROMAN_RE = re.compile(r"\b(?:II|III|VI|VII|VIII|IX|XII)\b")
_FRACTIONS = str.maketrans({"½": " 1/2 ", "¼": " 1/4 ", "¾": " 3/4 ", "⅓": " 1/3 ", "⅔": " 2/3 "})
# «1 000», «10 000 000» — пробел как разделитель тысяч (так пишет RU).
_SPACED_THOUSANDS = re.compile(r"(?<![\d.,])\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?![\d.,]?\d)")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _lower(text: str, lang: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower() if lang == "tr" else text.lower()


def plain_numbers(text: str) -> frozenset[str]:
    """Все числа абзаца цифрами в одной записи: «1.000» = «1 000» = «1,000», «2,50» = «2.5».

    Римские («tip II») и дроби («½») приводятся к цифрам. Единица и ноль не
    сравниваются: «bir»/«1 из», «once»/«1 раз» модель пишет то словом, то цифрой.
    """
    text = _ROMAN_RE.sub(lambda m: _ROMAN[m.group(0)], str(text or "").replace(_BRAND, " ").translate(_FRACTIONS))
    text = _SPACED_THOUSANDS.sub(lambda m: re.sub(r"\s", "", m.group(0)), text)
    return frozenset({_normalize_number(token) for token in _NUMBER.findall(text)} - {"1", "0"})


def number_words(text: str, lang: str) -> frozenset[str]:
    """Числа словами («üç», «три», «three», «twice») — только оправдывают цифру
    в другом тексте: «her iki» — это «оба», а не «2»; аббревиатура «TEN» — не 10."""
    words = _NUMBER_WORDS[lang]
    text = str(text or "")
    found = {value for pattern, value in _NUMBER_PHRASES[lang] if re.search(pattern, _lower(text, lang))}
    for word in re.findall(r"[^\W\d_]+", text):
        key = _lower(word, lang)
        if key in words and not (word.isupper() and len(word) > 1):
            found.add(str(words[key]))
    return frozenset(found)


# ── Понятия ───────────────────────────────────────────────────────────────

# Понятие: (TR, RU, EN). TR сравнивается после свёртки букв (ı→i, ç→c, ğ→g,
# ö→o, ü→u; ş остаётся: «kaş» — бровь, «kas» — мышца). None — в этом языке
# перевод понятия слишком разнообразен (совпадение < 90 % на верных записях).
_CONCEPTS = {
    "doctor": (r"doktor|hekim", r"врач|доктор", r"doctor|physician"),
    "pharmacist": (r"eczaci", r"фармацевт|провизор|аптек", r"pharmac"),
    "kidney": (r"bobrek", r"почк|почек|почеч|нефр", r"kidney|renal|nephr"),
    "liver": (r"karacig|hepat", r"печен|печён|гепат", r"liver|hepat"),
    "heart": (r"\bkalp|\bkalb|kardi", r"сердц|сердеч|кардио|инфаркт", r"heart|cardi"),
    "child": (r"cocuk|pediatri", r"\bдет|ребен|ребён|педиатр", r"child|pediatr|paediatr|kids"),
    "pregnancy": (r"hamile|\bgebe", r"беремен", r"pregnan"),
    "breastfeeding": (r"emzir|anne sut", r"кормл|кормящ|кормить|молок|лактац|грудью|вскармлив", r"breast|lactat|nursing"),
    "allergy": (r"all?er[jg]i", r"аллерг", r"allerg"),
    "infection": (r"enfeks", r"инфекц|инфицир", r"infect"),
    "blood": (r"\bkan(?:in|i|da|daki|dan|a|am\w*)?\b(?! basinc)|kan pulcu", None, r"blood|bleed|haem|hemo|platelet"),
    "skin": (r"\bderi|\bcilt", r"кож|дерм", r"skin|derm|cutaneous"),
    "intestine": (r"bagirsa|barsak", r"кишеч|кишк|кишок", None),
    "nausea": (r"bulanti", r"тошнот", r"nause"),
    "vomiting": (r"kusma|kusar", r"рвот", r"vomit"),
    "diarrhea": (r"ishal", r"диаре|понос", r"diarr"),
    "constipation": (r"kabiz", r"запор", r"constipat"),
    "itching": (r"ka[sş]int", r"зуд", r"itch|prurit"),
    "rash": (r"dokuntu|kizari|kizarik", r"сып|покраснен|высыпан|эритем", r"rash|redness|erythem"),
    "swelling": (r"[sş]i[sş]me|[sş]i[sş]lik|odem", r"отек|отёк|опух|припух|отёч|отеч", r"swell|o?edema"),
    "dizziness": (r"ba[sş] donme|sersem|vertigo", r"головокруж", r"dizz|vertigo|lightheaded"),
    "headache": (r"ba[sş] agri", r"головн\w* бол", r"headache"),
    "fatigue": (r"yorgun|halsiz|bitkin", r"усталост|утомл|слабост|вялост", r"tired|fatigue|weak|letharg"),
    "sleep": (r"uyku|uyu[sş]uk", None, r"sleep|insomn|drows|somnol"),
    "depression": (r"depres", r"депрес", r"depress"),
    "cancer": (r"kanser|tumor|malign|onkolo", r"\bрак|опухол|онко|злокачеств", r"cancer|tumou?r|malignan|oncol"),
    "diabetes": (r"diyabet|[sş]eker hastal", r"диабет", r"diabet"),
    "sugar": (r"[sş]eker|glukoz", r"сахар|глюкоз", None),
    "alcohol": (r"alkol", r"алкогол|спирт", r"alcohol"),
    "driving": (r"\barac\b|arac kullan|makine", r"транспорт|машин|механизм|автомоб|вожден", r"driv|machin|vehicle"),
    "storage": (r"sakla", r"хран", r"\bstor|\bkeep"),
    "refrigerator": (r"buzdolab", r"холодильн", r"refrigerat|fridge"),
    "freeze": (r"dondur|donmu[sş]", r"замора|морозил|заморож", r"freez|frozen"),
    "light": (
        r"\bi[sş]i[kg]|gune[sş]",
        r"свет(?!л)|солн",
        r"(?<!-)\blight\b(?![- ](?:pink|yellow|blue|green|brown|orange|red|gr[ae]y|purple|colou?red|beige|cream))"
        r"|\bsun(?:light|screen|burn)?\b",
    ),
    "tablet": (r"tablet", r"таблет", r"tablet"),
    "capsule": (r"kapsul", r"капсул", r"capsul"),
    "injection": (r"enjeks|enjekt", None, r"inject|syringe"),
    "solution": (r"cozelti|solusyon", r"раствор", r"solution"),
    "syrup": (r"[sş]urup", r"сироп", r"syrup"),
    "cream": (r"\bkrem", r"крем", r"cream|sunscreen"),
    "week": (r"hafta", r"недел", r"week"),
    "age": (r"\bya[sş](?:in|ind|indan|indaki|tan|taki|a\b|\b)", r"\bлет\b|возраст|\bгод(?:а|у|ом)?\b", r"\byears?\b|\baged?\b"),
    "elderly": (r"ya[sş]li", r"пожил", r"elderl"),
    "women": (r"kadin", r"женщин", r"\bwom[ae]n|female"),
    "baby": (r"bebek|bebeg|yenidog", r"\bдет|ребен|ребён|младен|новорожд|недонош|груднич", r"bab(?:y|ies)|infant|newborn|neonat"),
    "adult": (r"yeti[sş]kin|eri[sş]kin", r"взросл", r"adult"),
    "muscle": (r"\bkas(?:\b|lar|ta\b|lara|larda|larin)|kramp", r"мышц|мышеч|судорог|спазм", r"muscl|muscul|cramp|spasm"),
    "bone": (r"\bkemik", None, r"\bbones?\b|osteo|skelet"),
    "joint": (r"\beklem", r"сустав", r"joint|arthr"),
    "seizure": (r"nobet|havale|konvulz|epilep", None, r"seizure|convuls|epilep"),
    "hair": (r"\bsac(?:\b|lar|in|i\b)", r"волос", r"\bhair"),
    "throat": (r"bogaz", r"горл", r"throat"),
    "nose": (r"burun|burn[iu]", r"\bнос|назал|ноздр|насморк|ринит", r"\bnos[ei]|nasal|nostril|rhin"),
    "surgery": (r"ameliyat|cerrah", r"операц|хирург", r"surg|operation"),
    "vitamin": (r"vitamin", r"витамин", r"vitamin"),
    "hormone": (r"hormon", r"гормон", r"hormon"),
    "antibiotic": (r"antibiyo", r"антибиот", r"antibiot"),
    "bacteria": (r"bakteri", r"бактер", r"bacter"),
    "fungal": (r"mantar", r"грибк|грибов|микоз", r"fung"),
    "virus": (r"virus|viral", r"вирус", r"virus|viral"),
    "asthma": (r"astim", r"астм", r"asthm"),
    "cough": (r"oksur", r"кашл|кашел|кашель", r"cough"),
    "contraception": (r"dogum kontrol|kontrasep", r"контрацеп|противозачат|рождаемост|предохран", r"contracep|birth control"),
    "weight": (r"\bkilo(?!gram)|agirlik|agirli", None, r"weigh"),
    "stroke": (r"\binme\b", r"инсульт", r"stroke"),
    "side_effect": (r"yan etki", r"побочн|нежелательн", r"side effect|adverse"),
    "package": (r"ambalaj|\bkutu|blister", r"упаков|коробк|блистер", r"pack|\bbox|blister|carton"),
    "expiry": (r"son kullanma|miad", None, r"expir"),
    "white": (r"beyaz", r"\bбел", r"white"),
    "red": (r"kirmizi", r"красн", r"\bred\b"),
    "yellow": (r"\bsari\b|\bsarims", r"желт|жёлт", r"yellow"),
    "pink": (r"pembe", r"розов", r"pink"),
    "orange": (r"turuncu", r"оранж", r"orange"),
    "green": (r"ye[sş]il", r"зелен|зелён", r"green"),
    "brown": (r"kahverengi", r"коричн", r"brown"),
    "round": (r"yuvarlak", r"кругл", r"round|circular"),
    "oval": (r"\boval", None, r"oval"),
    "lactose": (r"laktoz", r"лактоз", r"lactose"),
    "sodium": (r"sodyum", r"натри", r"sodium"),
    "potassium": (r"potasyum", r"\bкали[йяюе]", r"potassium"),
    "calcium": (r"kalsiyum", r"кальци", r"calcium"),
    "magnesium": (r"magnezyum", r"магни", r"magnesium"),
    "iron": (r"\bdemir", None, r"\biron\b|ferr"),
    "thyroid": (r"tiroid", None, r"thyroid"),
    "immune": (r"bagi[sş]iklik|immun", r"иммун", r"immun"),
}
_LANGS = ("tr", "ru", "en")
_CONCEPT_RES = {
    lang: [(name, re.compile(row[index])) for name, row in _CONCEPTS.items() if row[index]]
    for index, lang in enumerate(_LANGS)
}
_CHECKED = {lang: frozenset(name for name, _ in _CONCEPT_RES[lang]) for lang in ("ru", "en")}
_TR_FOLD = str.maketrans("ıçğöüâîû", "icgouaiu")


def concepts(text: str, lang: str) -> frozenset[str]:
    """Медицинские понятия абзаца по словарю (врач, почки, хранение, таблетка…)."""
    text = _lower(str(text or "").replace(_BRAND, " "), lang)
    if lang == "tr":
        text = text.translate(_TR_FOLD)
    return frozenset(name for name, pattern in _CONCEPT_RES[lang] if pattern.search(text))


# ── Заголовок, частота, длина ─────────────────────────────────────────────

# «2. X'İ KULLANMADAN ÖNCE…», «3. Kapağı açınız»; не «1. günde», «2. haftada».
_SOURCE_HEADING = re.compile(
    r"^\s*(\d{1,2})\.\s+(?!(?:g[üu]n|hafta|ay\b|y[ıi]l|doz|kez|saat|basamak|tedavi|k[üu]r|seans)\w*)(?=[^\W\d_])",
    re.IGNORECASE,
)
_TRANSLATION_HEADING = re.compile(r"^\s*(\d{1,2})\s*[.)](?!\d)")

# Частота побочного эффекта в начале абзаца («Yaygın olmayan: 100 hastanın…»).
_FREQUENCY_LABEL = re.compile(
    r"^\W*(çok yaygın|yaygın olmayan|yaygın|çok seyrek|seyrek|bilinmiyor)\s*(?:yan etkiler\w*)?\s*[:(]",
    re.IGNORECASE,
)
_FREQUENCY_SOURCE = {
    "çok yaygın": "very_common", "yaygın olmayan": "uncommon", "yaygın": "common",
    "çok seyrek": "very_rare", "seyrek": "rare", "bilinmiyor": "unknown",
}
_FREQUENCY_TRANSLATION = {
    "ru": (
        ("unknown", r"неизвестн|не известн"),
        ("very_common", r"очень (?:част|распростран)"),
        ("uncommon", r"нечаст|не част|необычн|нераспростран"),
        ("common", r"част|распростран"),
        ("very_rare", r"очень редк"),
        ("rare", r"редк"),
    ),
    "en": (
        ("unknown", r"not known|unknown"),
        ("very_common", r"very (?:common|frequent)"),
        ("uncommon", r"uncommon|infrequent|not common"),
        ("common", r"common|frequent"),
        ("very_rare", r"very rare"),
        ("rare", r"rare"),
    ),
}

# Длина перевода ≈ c × длина исходника, дисперсия ∝ длине (Гейл–Чёрч).
_LENGTH_MODEL = {"ru": (1.015, 3.737), "en": (0.983, 3.027)}


def _frequency(text: str, lang: str) -> Optional[str]:
    if lang == "tr":
        label = _FREQUENCY_LABEL.match(_lower(text, lang))
        return _FREQUENCY_SOURCE[label.group(1)] if label else None
    head = text.lower()[:60]
    for name, pattern in _FREQUENCY_TRANSLATION[lang]:
        if re.search(pattern, head):
            return name
    return None


class Features:
    """Признаки одного текста для сравнения исходника и перевода."""

    __slots__ = ("lang", "numbers", "words", "concepts", "length", "heading", "frequency", "brand", "end", "empty")

    def __init__(self, text: str, lang: str):
        text = str(text or "").strip()
        self.lang = lang
        self.empty = not text
        self.numbers = plain_numbers(text)
        self.words = number_words(text, lang)
        self.concepts = concepts(text, lang)
        self.length = len(text)
        match = (_SOURCE_HEADING if lang == "tr" else _TRANSLATION_HEADING).match(text)
        self.heading = match.group(1) if match else None
        self.frequency = _frequency(text, lang)
        self.brand = _BRAND in text
        self.end = text[-1] if text and text[-1] in ":?,;" else "."


def pair_score(source: Features, translation: Features) -> float:
    """Насколько translation похож на перевод source: больше — лучше, ≈0 — без признаков."""
    score = 0.0
    if source.numbers or translation.numbers:
        matched = source.numbers & (translation.numbers | translation.words)
        matched |= translation.numbers & (source.numbers | source.words)
        score += 3 * (2 * len(matched) / len(source.numbers | translation.numbers) - 1)
    expected = source.concepts & _CHECKED[translation.lang]
    if expected and translation.concepts:
        score += 3 * len(expected & translation.concepts) / math.sqrt(len(expected) * len(translation.concepts)) - 1
    ratio, variance = _LENGTH_MODEL[translation.lang]
    delta = (translation.length - ratio * source.length) / math.sqrt(variance * source.length + 25)
    score -= min(delta * delta / 2, 12) / 2
    if source.heading:
        score += 2 if translation.heading == source.heading else -2
    elif translation.heading:
        score -= 1
    if source.brand != translation.brand:
        score -= 0.7
    if source.end != translation.end:
        score -= 0.3
    return score


# ── Правила для одного абзаца ─────────────────────────────────────────────

# |ln| отношения длин перевода и исходника: у 98 % верных записей — до 0,34.
# Сглаживание гасит разброс у коротких («Gaz» → «Газообразование»), у пары
# RU/EN оно больше: «Gastritis» против «Воспаление желудка (гастрит)» — норма.
LENGTH_LOG_RATIO = 0.7
RU_EN_LENGTH_LOG_RATIO = 0.6


def _log_ratio(a: Features, b: Features, smoothing: int) -> float:
    return abs(math.log((a.length + smoothing) / (b.length + smoothing)))


def _numbers_differ(a: Features, b: Features) -> bool:
    """Цифра одного текста не встречается в другом ни цифрой, ни словом."""
    return bool(a.numbers - b.numbers - b.words or b.numbers - a.numbers - a.words)


def _problems(src: Features, ru: Features, en: Features) -> list[str]:
    problems = []
    if src.heading and (ru.heading != src.heading or en.heading != src.heading):
        problems.append("heading_mismatch")
    if _numbers_differ(src, ru) or _numbers_differ(src, en):
        problems.append("number_mismatch")
    if max(_log_ratio(ru, src, 10), _log_ratio(en, src, 10)) > LENGTH_LOG_RATIO:
        problems.append("length_mismatch")
    if _numbers_differ(ru, en) or _log_ratio(ru, en, 20) > RU_EN_LENGTH_LOG_RATIO:
        problems.append("ru_en_mismatch")
    for translation in (ru, en):
        expected = src.concepts & _CHECKED[translation.lang]
        if len(expected) >= 2 and not expected & translation.concepts:
            problems.append("concept_mismatch")
            break
    if src.frequency and (ru.frequency != src.frequency or en.frequency != src.frequency):
        problems.append("frequency_mismatch")
    return problems


def item_problems(source: str, ru: str, en: str) -> list[str]:
    """Признаки чужого перевода в одном абзаце (пустой список — расхождений нет)."""
    return _problems(Features(source, "tr"), Features(ru, "ru"), Features(en, "en"))


# ── Сдвиг в последовательности абзацев ────────────────────────────────────

# Перевод ближе к соседнему исходнику, чем к своему, на SHIFT_MARGIN (RU и EN
# вместе) или на LOCALE_SHIFT_MARGIN в одном языке — сдвиг; сдвиг бывает только
# в EN (≈2 % записей 20.10). Абзац на месте — ближе к своему на SHIFT_MARGIN и
# сам по себе похож (> SELF_MIN_SCORE): исходник чужого перевода мог не попасть
# в память, и тогда с соседями перевод не совпадает.
SHIFT_MARGIN = 2.0
LOCALE_SHIFT_MARGIN = 3.0
SELF_MIN_SCORE = -2.0
_NEIGHBOURS = (1, 2, -1)


def _evidence(rows: Sequence[tuple[Features, Features, Features]], index: int) -> int:
    """+1 — перевод записи index от соседнего абзаца, −1 — от своего, 0 — не ясно.

    Сосед годится в «хозяева» перевода, только если его собственный перевод
    подходит ему не лучше: два почти одинаковых абзаца подряд («Aksiyal
    spondiloartrit…» и «-Radyografik olmayan aksiyal spondiloartrit…») — не сдвиг.
    """
    source, ru, en = rows[index]
    if ru.empty or en.empty:
        return 0
    own_ru, own_en = pair_score(source, ru), pair_score(source, en)
    own = own_ru + own_en
    neighbours, candidates = [], []
    for j in (index + step for step in _NEIGHBOURS):
        if not 0 <= j < len(rows) or rows[j][0].empty:
            continue
        other, other_ru, other_en = rows[j]
        scores = (pair_score(other, ru), pair_score(other, en))
        neighbours.append(scores)
        if sum(scores) >= pair_score(other, other_ru) + pair_score(other, other_en):
            candidates.append(scores)
    if candidates and (
        max(ru_score + en_score for ru_score, en_score in candidates) - own > SHIFT_MARGIN
        or max(ru_score for ru_score, _ in candidates) - own_ru > LOCALE_SHIFT_MARGIN
        or max(en_score for _, en_score in candidates) - own_en > LOCALE_SHIFT_MARGIN
    ):
        return 1
    if not neighbours:
        return 0
    best = max(ru_score + en_score for ru_score, en_score in neighbours)
    return -1 if own - best > SHIFT_MARGIN and own > SELF_MIN_SCORE else 0


def spread_shift(evidence: Sequence[int], *, back: int = 3, forward: int = 40) -> list[bool]:
    """Сдвиг по цепочке: от каждой записи со сдвигом вперёд до записи «на месте»
    (не дальше ``forward``) и назад на ``back`` записей без признаков."""
    shifted = [value == 1 for value in evidence]
    for index, value in enumerate(evidence):
        if value != 1:
            continue
        j = index + 1
        while j < len(evidence) and j <= index + forward and evidence[j] != -1:
            shifted[j] = True
            j += 1
        j = index - 1
        while j >= 0 and j >= index - back and evidence[j] == 0:
            shifted[j] = True
            j -= 1
    return shifted


def request_shift(sources: Sequence[str], ru: Sequence[str], en: Sequence[str]) -> set[int]:
    """Индексы абзацев одного ответа модели, переводы которых, вероятно, сдвинуты.

    Сдвиг тянется по ответу, пока не встретится абзац, точно стоящий на месте,
    поэтому от каждого признака сдвига отбрасываются соседи в обе стороны до
    такого абзаца.
    """
    rows = [(Features(s, "tr"), Features(r, "ru"), Features(e, "en")) for s, r, e in zip(sources, ru, en)]
    evidence = [_evidence(rows, index) for index in range(len(rows))]
    spread = spread_shift(evidence, back=len(rows), forward=len(rows))
    return {index for index, shifted in enumerate(spread) if shifted}


def audit_sequence(rows: Iterable[tuple[str, str, str]]) -> list[list[str]]:
    """Причины для каждой записи потока (исходник, RU, EN) в порядке вставки в память.

    Записи одного запроса стоят в памяти подряд (pk по порядку абзацев), поэтому
    соседи по pk — соседи по ответу модели. К правилам абзаца добавляется
    «shifted»; в памяти держится только окно из четырёх записей.
    """
    problems: list[list[str]] = []
    evidence: list[int] = []
    window: list[tuple[Features, Features, Features]] = []  # записи i-1, i, i+1, i+2
    current = 0  # позиция записи i в окне (0 — у первой записи нет предыдущей)

    def evaluate() -> None:
        nonlocal current
        evidence.append(_evidence(window, current))
        if current == 0:
            current = 1
        else:
            window.pop(0)

    for source, ru, en in rows:
        features = (Features(source, "tr"), Features(ru, "ru"), Features(en, "en"))
        problems.append(_problems(*features))
        window.append(features)
        if len(window) - current == 3:
            evaluate()
    while current < len(window):
        evaluate()
    for index, shifted in enumerate(spread_shift(evidence)):
        if shifted:
            problems[index].append("shifted")
    return problems
