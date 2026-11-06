"""Правка описания после ответа модели: «вода», висящие хвосты, опечатки, турецкие вставки.

Описание модели и описание из памяти переводов проходят одну и ту же правку, поэтому
исправления здесь действуют и на уже сохранённые переводы. Проверено на карточках
SuperStep 06.11.2026 (115 карточек с ошибками из 1 488).
"""

from __future__ import annotations

import re

from apps.ai.services.rules import vocab

# Обороты-«вода», которые модель пишет вопреки промпту: «… подходит для повседневной носки»,
# «Цвет нейтрален и легко сочетается с джинсами». Вырезается оборот вместе с союзом перед ним;
# предложение целиком — только если без оборота в нём ничего не осталось.
# Глагол после «и»: «… для повседневной носки и добавляет образу …» — не продолжение «для».
_VERB = r"[а-яё]+(?:ет|ит|ют|ят|ут|ат|ется|ится|ются|ятся|ются)\b"
_EVERYDAY_RE = {
    "ru": re.compile(
        r"(?P<lead>,\s*|\s+и\s+)?"
        r"(?P<verb>(?:(?:идеально|отлично|хорошо)\s+)?(?:подход\w+|подойд\w+|предназначен\w*|создан\w*|рассчитан\w*)\s+"
        r"|дела\w+\s+(?:[а-яё]+\s+)?подходящ\w*\s+)?"
        r"(?:как\s+)?для\s+повседневн\w*\s+(?:(?:и\s+)?[а-яё]+\s+)?(?:носки|образ\w*|использовани\w*|стил\w*)"
        r"(?:\s+в\s+городе|\s+по\s+городу|,\s*в\s+том\s+числе\s+[^.,;!?]*)?"
        rf"(?:(?P<both>,\s*так\s+и\s+(?=для|в|на|при))|(?P<tail>\s+и\s+(?!{_VERB})(?=[а-яё]))|\s+и(?=\s+{_VERB}))?",
        re.IGNORECASE,
    ),
    "en": re.compile(
        r"(?P<lead>,\s*|\s+and\s+)?(?P<verb>(?:ideal|perfect|great|suitable|designed|made)\s+)?for\s+(?:everyday|daily|casual)\s+"
        r"(?:wear|looks?|outfits?|style)(?P<both>(?!))?(?P<tail>\s+and\s+(?=[a-z]))?",
        re.IGNORECASE,
    ),
}
# «сочетается с …», но не «в сочетании с другими каркасами PAX» (факт у IKEA).
_PAIRING_RE = {
    "ru": re.compile(
        r"(?:,\s*|\s+и\s+)?(?:(?:легко|отлично|хорошо|гармонично|удачно|органично|стильно|удобно|позволя\w+|можно)\s+)?"
        r"сочета(?:ется|ются|ет|ют|ть)\b(?:\s+[а-яё]+){0,2}\s+с\s+"
        # «с разными/другими …» — только вещи и стиль: «с другими модулями» у IKEA — факт.
        r"(?:джинс|брюк|чинос|шорт|юбк|плать|повседневн\w+"
        r"|(?:разн\w+|любы\w+|больш\w+|други\w+)\s+(?:вещ|одежд|образ|стил|предмет\w*\s+гардероб|элемент\w*\s+гардероб|аксессуар|цвет))"
        rf"[^.,;!?]*?(?:,(?!\s*(?:а|но|при|что|котор\w*)\s)[^.,;!?]*?)*(?:\s+и(?=\s+{_VERB})|(?=[.,;!?]|$))",
        re.IGNORECASE,
    ),
    "en": re.compile(
        r"(?:,\s*|\s+and\s+)?(?:it\s+|they\s+)?(?:pairs?|goes|go|combines?|matches?)\s+(?:well\s+|easily\s+|perfectly\s+)?with\s+[^.,;!?]*"
        r"(?:,(?!\s*(?:and|but|while|which)\s)[^.,;!?]*)*",
        re.IGNORECASE,
    ),
}
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+(?=[«\"A-ZА-ЯЁ])")

# После вырезки предложение не может кончаться союзом или предлогом: «Кремовый цвет нейтрален и.»,
# «… бежевым оттенком, который.» — хвост срезается; «Дизайн подходит для.» без хвоста ничего не
# говорит — предложение убирается.
_DANGLING_RE = {
    "ru": re.compile(
        r"(?:,\s*|\s+)(?:и|а|но|или|для|с|со|в|во|на|из|по|от|к|ко|при|без|под|над|о|об|что|чтобы|как|так|"
        r"который|которая|которое|которые|котором|которой|которых|которую|которого|которым|которыми)$",
        re.IGNORECASE,
    ),
    "en": re.compile(r"(?:,\s*|\s+)(?:and|or|but|for|with|to|of|in|on|as|that|which|while|so)$", re.IGNORECASE),
}
# Нетронутое предложение: только то, чем русское/английское предложение не кончается никогда.
# Так правятся переводы, сохранённые в память уже обрезанными (06.11.2026), но не «Pull them on.»
# и не «Стирка при 30 С.».
_DANGLING_ALWAYS_RE = {
    "ru": re.compile(
        r"(?:,\s*|\s+)(?:и|а|но|или|для|который|которая|которое|которые|которую|которого|которым|которыми)$",
        re.IGNORECASE,
    ),
    "en": re.compile(r"(?:,\s*|\s+)(?:and|or|but)$", re.IGNORECASE),
}
# «подходит как для спорта, так и.» / «… так и для повседневной носки» → «подходит для спорта».
_BOTH_RE = re.compile(
    r"\bкак\s+((?:для|в|на|при)\s+[^,]+),\s*так(?:\s+и(?:\s+для\s+повседневн\w*\s+(?:(?:и\s+)?[а-яё]+\s+)?"
    r"(?:носки|образ\w*|использовани\w*|стил\w*))?)?(?=\s*[.!?…]?$|\s*[.!?…])",
    re.IGNORECASE,
)
# Начало предложения вырезано: «…, а подошва из EVA гасит удары.» → «Подошва из EVA гасит удары.»
_LEAD_JOINER_RE = re.compile(r"^(?:[,;:—–-]\s*|(?:а|но|и|при\s+этом)\s+)+", re.IGNORECASE)
_FRAGMENT_START_RE = re.compile(r"^(?:особенно|в\s+том\s+числе|например)\b", re.IGNORECASE)
_HOLLOW_RE = {
    "ru": re.compile(
        r"(?:подход\w*|подойд\w*|предназначен\w*|создан\w*|рассчитан\w*|подходящ\w*|универсальн\w*|органично|удобно|легко)$",
        re.IGNORECASE,
    ),
    "en": re.compile(r"(?:suitable|ideal|perfect|designed|made|great)$", re.IGNORECASE),
}

# Ошибки модели, которые правятся однозначно (карточки SuperStep 06.11.2026).
_RU_FIXES = (
    (re.compile(r"\b([Ее])рго"), lambda m: ("Э" if m.group(1) == "Е" else "э") + "рго"),  # «Ергономичная»
    (re.compile(r"(^|[.!?…]\s+|>)Кроя\b"), r"\1Крой"),  # «Кроя regular fit», «Кроя без рукавов»
    (re.compile(r"\bиз\s+([а-яё]+(?:ого|его))\s+цвета\b", re.IGNORECASE), r"\1 цвета"),  # «из белого цвета»
    (re.compile(r"\b([Нн]изк|[Вв]ысок)ий\s+голенищ"), r"\1ое голенищ"),  # «Низкий голенище»
    # «Лёгкая лёгкая подошва»; только русские слова — «Bye Bye Bye» у моделей не трогаем.
    (re.compile(r"\b([а-яё]{3,})(\s+)\1\b", re.IGNORECASE), r"\1"),
)
# «File» у обуви и сумок — сетка: «Сделаны из файла, TPU» (не «Папка для файла А4»).
_MESH_TYPES = frozenset({"shoes", "accessories"})
_FILE_FIXES = (
    (re.compile(r"\bфайлом\b", re.IGNORECASE), "сеткой"),
    (re.compile(r"\bфайла\b", re.IGNORECASE), "сетки"),
    (re.compile(r"\bфайле\b", re.IGNORECASE), "сетке"),
    (re.compile(r"\bфайл\b", re.IGNORECASE), "сетка"),
)

# Английские слова ключей словаря («Slim Fit», «Crew Neck»): в описании — не турецкая вставка.
_ENGLISH_WORDS = frozenset({
    "boy", "classic", "crew", "eau", "full", "high", "long", "loose", "mat", "nec", "neck", "regular", "roll",
    "shirt", "short", "sleeve", "slim", "toilette", "zip",
})
# Слова словаря, которые бывают латиницей в названиях моделей и брендов («Marin», «Doktor»).
_NAME_LIKE_WORDS = frozenset({"marin", "doktor", "kombin", "model", "normal", "basic"})
# Турецкие слова словарей (без совпадающих с английскими): по ним видно непереведённую вставку.
TURKISH_WORDS = frozenset(
    word
    for mapping in (vocab.COLORS, vocab.DESCRIPTORS, vocab.AUDIENCE, vocab.KINDS)
    for key in mapping
    for word in key.split()
    if word.isalpha() and len(word) > 2 and word not in vocab._ENGLISH_VOCAB_WORDS and word not in _ENGLISH_WORDS
) | frozenset({"yaka", "dik", "kapsul", "koleksiyon", "sisme", "kopuk", "canli", "ergonomik", "tasarim", "hirka"})
_TURKISH_LETTERS_RE = re.compile(r"[çğışÇĞİŞ]")
# Оригинал в скобках или кавычках после перевода: «(bisiklet yaka)», «горловина-«bisiklet yaka»», «(Dik Yaka)».
_ASIDE_RE = re.compile(r"\s*-?(?:\(([^()]*)\)|«([^«»]*)»)")


def _drop_turkish_asides(text: str) -> str:
    def aside(match: re.Match) -> str:
        inner = match.group(1) if match.group(1) is not None else match.group(2)
        words = re.findall(r"[^\W\d_]+", inner)
        # Только слова словаря: «(bisiklet yaka)», «(lacivert)»; бренд «Hotiç», «Altınyıldız Classics» — остаётся.
        if not words or re.search(r"[а-яё]", inner, re.IGNORECASE) or not all(vocab.fold(w) in TURKISH_WORDS for w in words):
            return match.group(0)
        return ""

    return _ASIDE_RE.sub(aside, text)


def turkish_leftovers(text: str, identity: str = "") -> list[str]:
    """Турецкие слова в RU-описании, кроме бренда и модели товара."""
    own = {vocab.fold(word) for word in re.findall(r"[^\W\d_]+", identity)}
    plain = re.sub(r"<[^>]+>", " ", text or "")
    words = re.findall(r"[^\W\d_]+", plain)
    return [
        word
        for word in words
        if vocab.fold(word) not in own
        and not re.search(r"[а-яё]", word, re.IGNORECASE)
        # Короткие слова словаря совпадают с латиницей моделей и брендов («Bot», «Spor», «Krem», «Mont»).
        and (
            _TURKISH_LETTERS_RE.search(word)
            or (len(word) >= 5 and vocab.fold(word) in TURKISH_WORDS and vocab.fold(word) not in _NAME_LIKE_WORDS)
        )
    ]


def _trim_dangling(sentence: str, locale: str, *, cut: bool) -> str:
    end = sentence[-1] if sentence and sentence[-1] in ".!?…" else "."
    body = sentence.rstrip(" .!?…")
    body = _BOTH_RE.sub(r"\1", body) if locale == "ru" else body
    dangling = _DANGLING_RE[locale] if cut else _DANGLING_ALWAYS_RE[locale]
    trimmed = body != sentence.rstrip(" .!?…")
    for _ in range(3):
        match = dangling.search(body)
        if not match:
            break
        body, trimmed = body[: match.start()].rstrip(" ,;:—-"), True
    if not trimmed:
        return sentence
    if _HOLLOW_RE[locale].search(body):
        if "," not in body:
            return ""
        body = body.rsplit(",", 1)[0].rstrip()  # «Мягкая ткань, модель подходит для.» → «Мягкая ткань.»
    return body + end if not _is_empty(body) else ""


def _is_empty(text: str) -> bool:
    """«Модель», «Чёрный цвет» — без вырезанного оборота смысла нет; «Подошва EVA» — факт."""
    words = re.findall(r"[^\W\d_]+", text)
    return len(words) <= 2 and not re.search(r"[A-Za-z0-9]", text)


def _without_filler(sentence: str, locale: str) -> str:
    def everyday(match: re.Match) -> str:
        lead = " " if (match.group("lead") or "").strip() in ("", ",") else match.group("lead")
        if match.group("both"):  # «подходит как для повседневной носки, так и для особых случаев» → «подходит для …»
            return f"{lead}{match.group('verb') or ''}"
        if match.group("tail"):  # «для повседневной носки и бега» → «для бега»
            return f"{lead}{match.group('verb') or ''}{'для' if locale == 'ru' else 'for'} "
        return ""

    cleaned = _BOTH_RE.sub(r"\1", sentence) if locale == "ru" else sentence
    cleaned = _EVERYDAY_RE[locale].sub(everyday, _PAIRING_RE[locale].sub("", cleaned))
    cut = cleaned != sentence
    if cut:
        cleaned = re.sub(r"\s+([,.!?…;:])", r"\1", re.sub(r"\s{2,}", " ", cleaned)).strip()
        cleaned = re.sub(r"[,;:]+(?=[.!?…]?$)", "", cleaned)
        lead_cut = _LEAD_JOINER_RE.match(cleaned)
        if lead_cut or (sentence[:1].isupper() and cleaned[:1].islower()):
            # Начало вырезано: «…, а подошва из EVA гасит удары.» → «Подошва из EVA гасит удары.»
            cleaned = _LEAD_JOINER_RE.sub("", cleaned)
            if _FRAGMENT_START_RE.match(cleaned):
                return ""  # «особенно в жаркую погоду.» — без начала не предложение
            cleaned = cleaned[:1].upper() + cleaned[1:]
        if _is_empty(cleaned.rstrip(".!?…")):
            return ""
        if cleaned[-1] not in ".!?…":
            cleaned += "."
    return _trim_dangling(cleaned, locale, cut=cut) if cleaned else ""


def polish_description(text: str, locale: str, product_type: str = "") -> str:
    """Описание без «воды», висящих хвостов, однозначных ошибок и турецких оригиналов в скобках."""
    if not text or locale not in _EVERYDAY_RE:
        return text
    if locale == "ru":
        for pattern, replacement in _RU_FIXES + (_FILE_FIXES if product_type in _MESH_TYPES else ()):
            text = pattern.sub(replacement, text)
        text = _drop_turkish_asides(text)
    parts = re.split(r"(<[^>]+>)", text)
    for index, part in enumerate(parts):
        if part.startswith("<") or not part.strip():
            continue
        lead = part[: len(part) - len(part.lstrip())]
        kept = [s for s in (_without_filler(s.strip(), locale) for s in _SENTENCE_SPLIT_RE.split(part)) if s]
        parts[index] = (lead + " ".join(kept)) if kept else ""
    cleaned = "".join(parts)
    for _ in range(2):  # вложенные пустые теги: <ul><li></li></ul>
        cleaned = re.sub(r"<(p|li|ul|ol)>\s*</\1>", "", cleaned)
    return cleaned.strip() if re.sub(r"<[^>]+>|\s", "", cleaned) else ""
