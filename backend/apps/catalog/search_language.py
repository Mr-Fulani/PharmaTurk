"""Язык поиска товаров: как пишут бренды и товары по-русски, раскладка, окончания, опечатки.

Устройство — docs/PRODUCT_SEARCH.md («Вторая очередь»). Всё кодом и словарями, без LLM.
Бренды кириллицей берутся из ``vocab.BRAND_RU`` и памяти ``medicine_brand``, типы
товаров и пол — из ``vocab.KINDS`` и ``vocab.AUDIENCE`` (те же словари, что пишут
карточки). Здесь — только то, чего в них нет: разговорные синонимы запроса,
раскладка клавиатуры и чтение латиницы. Строки — уже нормализованные
(``product_search.normalize_search_text``).
"""
from __future__ import annotations

import re

# --- раскладка клавиатуры ЙЦУКЕН ↔ QWERTY ------------------------------------------
_EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`"
_RU = "йцукенгшщзхъфывапролджэячсмитьбюё"
_EN_TO_RU = str.maketrans(_EN, _RU)
_RU_TO_EN = str.maketrans(_RU, _EN)


def switch_layout(text: str) -> str:
    """«gfhfwtnfvjk» → «парацетамол», «ыфтщаш» → «sanofi». Пусто, если в запросе буквы обеих раскладок."""
    text = text.lower()
    letters = [ch for ch in text if ch.isalpha()]
    if letters and all(ch in _RU for ch in letters):
        return text.translate(_RU_TO_EN)
    if letters and all("a" <= ch <= "z" for ch in letters):
        return text.translate(_EN_TO_RU)
    return ""


# --- латиница ↔ кириллица ---------------------------------------------------------
_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s",
    "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

# Как читают латиницу на упаковке. Порядок важен: сначала сочетания букв.
_LAT_TO_CYR = (
    ("sch", "ш"), ("sh", "ш"), ("ch", "ч"), ("ph", "ф"), ("th", "т"), ("kh", "х"), ("zh", "ж"),
    ("ts", "ц"), ("ck", "к"), ("qu", "кв"), ("oo", "у"), ("ee", "и"), ("ou", "у"),
    ("ai", "ай"), ("ay", "ай"), ("ei", "ей"), ("ey", "ей"), ("oi", "ой"), ("oy", "ой"),
    ("yu", "ю"), ("ya", "я"), ("yo", "е"), ("ce", "це"), ("ci", "ци"), ("cy", "ци"),
    ("a", "а"), ("b", "б"), ("c", "к"), ("d", "д"), ("e", "е"), ("f", "ф"), ("g", "г"),
    ("h", "х"), ("i", "и"), ("j", "дж"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"),
    ("o", "о"), ("p", "п"), ("q", "к"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"),
    ("v", "в"), ("w", "в"), ("x", "кс"), ("y", "и"), ("z", "з"),
)
_LAT_PATTERN = re.compile("|".join(re.escape(src) for src, _ in _LAT_TO_CYR))
_LAT_MAP = dict(_LAT_TO_CYR)


def cyrillic_to_latin(text: str) -> str:
    """«нурофен» → «nurofen». Остальные символы — как есть."""
    return "".join(_CYR_TO_LAT.get(ch, ch) for ch in text)


def latin_to_cyrillic(word: str) -> str:
    """«nurofen» → «нурофен», «euthyrox» → «эутирокс», «sanofi» → «санофи».

    Только слово из латинских букв не короче 3; иначе пусто.
    """
    if not re.fullmatch(r"[a-z]{3,}", word or ""):
        return ""
    result = _LAT_PATTERN.sub(lambda match: _LAT_MAP[match.group(0)], word)
    return "э" + result[1:] if word.startswith("e") else result


def latin_reading(text: str) -> str:
    """Каждое латинское слово текста кириллицей; слова без латиницы пропускаются."""
    return " ".join(filter(None, (latin_to_cyrillic(word) for word in text.split())))


# --- окончания ----------------------------------------------------------------------
_ENDINGS = sorted(
    {
        "иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими", "ией", "ая", "яя", "ое", "ее",
        "ые", "ие", "ой", "ей", "ий", "ый", "ую", "юю", "ов", "ев", "ах", "ях", "ам", "ям", "ом", "ем",
        "а", "я", "ы", "и", "у", "ю", "е", "о", "ь", "й",
    },
    key=len,
    reverse=True,
)
_MIN_STEM = 4


def stem(word: str) -> str:
    """Русское слово без окончания: «магния» → «магни», «кроссовки» → «кроссовк».

    Короче 5 букв, с латиницей или цифрами — без изменений; основа не короче 4 букв.
    """
    if len(word) <= _MIN_STEM or not re.fullmatch(r"[а-я]+", word):
        return word
    for ending in _ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= _MIN_STEM:
            return word[: -len(ending)]
    return word


# --- синонимы запроса ----------------------------------------------------------------
# Разговорные слова, которых нет в названиях и словарях карточек. Ключ — основа слова
# запроса (``stem``), значения — основы, которые тоже ищутся (как часть слова, не короче 4 букв).
# Турецкие и английские названия типов в текст товара уже добавлены по ``vocab.KINDS``.
QUERY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "кросс": ("кроссовк",),
    "кроссовк": ("кед",),
    "кеды": ("кроссовк",),
    "толстовк": ("худи", "свитшот"),
    "худи": ("толстовк",),
    "свитшот": ("толстовк",),
    "кофт": ("свитер", "худи", "свитшот", "кардиган"),
    "пуховик": ("puffer", "sisme"),
    "штан": ("брюк",),
    "брюк": ("штан",),
    "шлепк": ("шлепанц",),
    "шлепанц": ("шлепк",),
    "тапк": ("шлепанц", "тапоч"),
    "тапоч": ("шлепанц",),
    "бейсболк": ("кепк",),
    "кепк": ("бейсболк",),
    "духи": ("парфюм",),
    "парфюм": ("духи",),
    "женщин": ("женск",),
    "мужчин": ("мужск",),
    "девочк": ("детск",),
    "мальчик": ("детск",),
    "ребенк": ("детск",),
    "детей": ("детск",),
    "витамин": ("vitamin",),
    "vitamin": ("витамин",),
}

# Буква витамина: русская в запросе = латинская на упаковке («витамин д3» = «Vitamin D3»).
LETTER_TWINS = {"а": "a", "б": "b", "в": "b", "с": "c", "д": "d", "е": "e", "к": "k"}


def letter_twin(word: str) -> str:
    """«д3» → «d3», «с» → «c», «b12» → «б12»; пусто, если слово не «буква + цифры»."""
    match = re.fullmatch(r"([a-zа-я])(\d*)", word)
    if not match:
        return ""
    letter, digits = match.groups()
    twin = LETTER_TWINS.get(letter) or next((ru for ru, lat in LETTER_TWINS.items() if lat == letter), "")
    return twin + digits if twin else ""


# --- опечатки ---------------------------------------------------------------------------
# Кандидаты ищутся в индексе по похожести слова (pg_trgm ``word_similarity``) с этим порогом:
# «нурафен» ~ «нурофен» 0,45, «ибупрафен» ~ «ибупрофен» 0,54.
TYPO_CANDIDATE_THRESHOLD = 0.4
# Слово короче — без исправления: в коротких словах одна буква меняет слово целиком.
TYPO_MIN_LENGTH = 5


def typo_limit(word: str) -> int:
    """Сколько букв можно исправить: одну в словах до 7 букв, две — в длинных."""
    return 1 if len(word) <= 7 else 2


def edit_distance(first: str, second: str) -> int:
    """Вставки, удаления, замены и перестановка соседних букв («ибупорфен»)."""
    rows = [list(range(len(second) + 1))]
    for i, a in enumerate(first, 1):
        row = [i]
        for j, b in enumerate(second, 1):
            cost = min(rows[-1][j] + 1, row[j - 1] + 1, rows[-1][j - 1] + (a != b))
            if i > 1 and j > 1 and a == second[j - 2] and first[i - 2] == b:
                cost = min(cost, rows[-2][j - 2] + 1)
            row.append(cost)
        rows.append(row)
    return rows[-1][-1]


def closest_word(word: str, texts) -> str:
    """Слово из текстов, отличное от ``word`` не больше чем на ``typo_limit`` букв.

    Из нескольких — с меньшим числом правок, затем встречающееся в большем числе товаров.
    """
    limit = typo_limit(word)
    counts: dict[str, int] = {}
    for text in texts:
        for token in set(text.split()):
            if token != word and abs(len(token) - len(word)) <= limit and not token.isdigit():
                counts[token] = counts.get(token, 0) + 1
    best, best_key = "", None
    for token, count in counts.items():
        distance = edit_distance(word, token)
        key = (distance, -count, token)
        if distance <= limit and (best_key is None or key < best_key):
            best, best_key = token, key
    return best
