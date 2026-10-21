"""Перевод МНН и инструкций лекарств через память переводов.

Память (AITranslationMemory) хранит проверенные переводы фрагментов:
namespace ``medicine_inn`` — действующие вещества, ``medicine_paragraph`` —
абзацы клинических разделов. Модель переводит только то, чего в памяти ещё
нет, короткими запросами (до 10 абзацев); в память попадает только перевод,
прошедший проверки (дозировки, язык, МНН, сдвиг ответа). Правка менеджера в админке берётся из памяти
при следующей обработке, а правка МНН сразу разносится по товарам
(apps.ai.signals).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from functools import lru_cache
from typing import Any, Callable, Optional

from apps.ai.services.medicine_fact_check import doses_match, inn_matches, is_proper_name_line
from apps.ai.services.medicine_paragraph_check import item_problems, request_shift
from apps.catalog.product_semantics import looks_untranslated_turkish
from apps.ai.services.medicine_reference import fold_tr
from apps.ai.services.translation_memory import lookup, normalize_source_text, remember, source_hash

logger = logging.getLogger(__name__)

INN_NAMESPACE = "medicine_inn"
PARAGRAPH_NAMESPACE = "medicine_paragraph"
# Бренд товара в абзаце → метка: абзацы разных препаратов совпадают в памяти.
BRAND_TOKEN = "{BRAND}"

# Запрос — до 10 абзацев и до 5000 символов. В длинном JSON модель пропускает
# абзац, и дальше каждому ключу достаётся перевод соседнего: в пакете 20.10.2026
# (20 000 символов, ≈ 154 абзаца) сдвиг был в 59 % запросов, среди первых 10
# абзацев — у 1,6 %, к концу запроса — до 54 %. При сдвиге отклоняется весь
# запрос, поэтому сдвиг портит и отправляет на повтор не больше 10 абзацев
# (docs/MEDICINE_PARAGRAPH_SHIFT_2026-10-20.md, «Маленькие запросы»).
PARAGRAPH_BATCH_ITEMS = 10
PARAGRAPH_BATCH_CHARS = 5000
PARAGRAPH_MAX_TOKENS = 16000
# Ключи source_tabs ilacfiyati с клиническими разделами, которые переводятся полностью.
CLINICAL_SOURCE_TABS = ("indications", "before_use_warnings", "usage_instructions", "side_effects", "storage_conditions")

INN_SYSTEM_PROMPT = (
    "Ты фармацевт-переводчик. Переводи турецкие названия действующих веществ (МНН) "
    "на русский и английский. RU — русское МНН полностью кириллицей, включая соль и "
    "гидрат (maleat → малеат, hidroklorür → гидрохлорид, sodyum → натрия, potasyum → калия, "
    "kalsiyum → кальция, trihidrat → тригидрат, asit → кислота); латиница в RU допустима "
    "только в обозначениях с цифрами (B12, D3). EN — международное непатентованное название. "
    "Ничего не добавляй. Ответ — строго JSON."
)

PARAGRAPH_SYSTEM_PROMPT = (
    "Ты профессиональный медицинский переводчик. Переводи абзацы официальной инструкции "
    "препарата с турецкого на русский и английский. Каждый абзац переводи полностью и "
    "отдельно: не сокращай, не пересказывай, не объединяй и не добавляй факты. Сохраняй "
    "каждую дозировку, число, единицу, предупреждение и название препарата. Метку {BRAND} "
    "(название препарата) переноси в оба перевода ровно как есть: не переводи, не склоняй, "
    "не убирай. Русский — "
    "естественный перевод, а не кириллическая транслитерация турецкого. Терминология: "
    "oblong = продолговатые, yaygın olmayan = нечастые, uzatılmış salımlı tablet = таблетки "
    "пролонгированного высвобождения, kısıtlanmış beyaz reçete = ограниченный белый рецепт, "
    "ek izlemeye tabi ilaç = препарат под дополнительным наблюдением. Ответ — строго JSON."
)


def peek(namespace: str, texts) -> dict[str, dict[str, str]]:
    """Как lookup, но без счётчика использований — для отчётов и разноса правок."""
    from apps.ai.models import AITranslationMemory

    by_hash = {source_hash(t): normalize_source_text(t) for t in texts if normalize_source_text(t)}
    found = {}
    hashes = list(by_hash)
    for start in range(0, len(hashes), 5000):
        rows = AITranslationMemory.objects.filter(
            namespace=namespace, source_hash__in=hashes[start:start + 5000]
        ).exclude(ru_text="").exclude(en_text="").values_list("source_hash", "ru_text", "en_text")
        for key, ru, en in rows:
            found[by_hash[key]] = {"ru": ru, "en": en}
    return found


_EMPTY_USAGE = {"tokens": {"prompt": 0, "completion": 0, "total": 0}, "cost_usd": 0.0, "processing_time_ms": 0}


def _add_usage(total: dict, result: Optional[dict]) -> None:
    if not result:
        return
    for key, value in (result.get("tokens") or {}).items():
        total["tokens"][key] = total["tokens"].get(key, 0) + (value or 0)
    total["cost_usd"] = round(total["cost_usd"] + (result.get("cost_usd") or 0), 6)
    total["processing_time_ms"] += result.get("processing_time_ms") or 0


def _new_usage() -> dict:
    return {"tokens": dict(_EMPTY_USAGE["tokens"]), "cost_usd": 0.0, "processing_time_ms": 0}


def translation_user_prompt(items: dict[str, str]) -> str:
    return (
        'Переведи значения. Ключи не меняй, не пропускай ни одного. '
        'Верни JSON вида {"ru": {"1": "…"}, "en": {"1": "…"}}.\n\n'
        f"{json.dumps(items, ensure_ascii=False)}"
    )


def paragraph_user_prompt(items: dict[str, str]) -> str:
    """Абзацы: RU и EN каждого — в одном объекте под его номером, а не двумя
    отдельными списками, где перевод легче съезжает к соседнему ключу."""
    return (
        'Переведи каждый абзац. Ключи не меняй, абзацы не пропускай и не объединяй. '
        'Верни JSON вида {"1": {"ru": "…", "en": "…"}, "2": {"ru": "…", "en": "…"}}.\n\n'
        f"{json.dumps(items, ensure_ascii=False)}"
    )


def items_from_user_prompt(user_prompt: str) -> dict[str, str]:
    return json.loads(user_prompt.split("\n\n", 1)[1])


def _call_translator(
    llm, system_prompt: str, items: dict[str, str], *, max_tokens: int, prompt=translation_user_prompt
) -> tuple[dict, dict]:
    """Один запрос: {"id": текст} → (JSON ответа модели, usage)."""
    user_prompt = prompt(items)
    try:
        result = llm.generate_content(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=0.0,
            max_retries=3,
        )
    except Exception as exc:
        logger.exception("Medicine memory translation failed: %s", exc)
        return {}, {}
    payload = result.get("content")
    if result.get("truncated") or result.get("json_error") or not isinstance(payload, dict):
        return {}, result
    return payload, result


# Оценка по пилоту 18.10.2026 (gpt-4o-mini): турецкий ≈ 3.2 символа на токен
# промпта; ответ RU+EN ≈ 0.54 токена на символ источника; ~300 токенов
# инструкций и ~6 токенов JSON на элемент.
def estimate_translation_cost(
    values: Optional[list[str]] = None,
    *,
    chars: Optional[int] = None,
    items_per_request: Optional[int] = None,
    request_chars: Optional[int] = None,
) -> dict:
    from django.conf import settings

    values = values or []
    chars = chars if chars is not None else sum(len(v) for v in values)
    items = len(values) or (chars // 400)
    if items_per_request:
        requests = -(-len(values) // items_per_request)
    else:
        requests = max(-(-chars // (request_chars or PARAGRAPH_BATCH_CHARS)), -(-items // PARAGRAPH_BATCH_ITEMS))
    prompt_tokens = chars / 3.2 + requests * 300 + items * 6
    completion_tokens = chars * 0.54 + items * 12
    model = settings.AI_CONFIG.get("MODEL", "gpt-4o-mini")
    price = (settings.AI_CONFIG.get("PRICING") or {}).get(model) or {}
    cost = (prompt_tokens * price.get("input", 0) + completion_tokens * price.get("output", 0)) / 1_000_000
    return {
        "requests": requests,
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "cost_usd": round(cost, 4),
    }


# ── МНН ───────────────────────────────────────────────────────────────────


def split_inn(value: Any) -> list[str]:
    """Комбинация «A + B» → ключи памяти по каждому веществу."""
    return [fold_tr(part) for part in re.split(r"\s*\+\s*", str(value or "")) if fold_tr(part)]


def _cyrillic_inn_ok(source: str, ru: str) -> bool:
    if not re.search(r"[А-Яа-яЁё]", ru):
        return False
    # Латиница — только в обозначениях с цифрами (B12, D3): «Клорфенирамин Maleat» — брак.
    if any(not re.search(r"\d", word) for word in re.findall(r"[A-Za-z][A-Za-z0-9-]*", ru)):
        return False
    return inn_matches(source, ru, "ru")


def _english_inn_ok(source: str, en: str) -> bool:
    return bool(en) and not re.search(r"[А-Яа-яЁё]", en) and inn_matches(source, en, "en")


def translate_inn_values(values: list[str], llm, *, batch_size: int = 100) -> tuple[dict, dict]:
    """Перевод ключей МНН моделью (без памяти). Возвращает только прошедшие проверку."""
    accepted: dict[str, dict[str, str]] = {}
    usage = _new_usage()
    for start in range(0, len(values), batch_size):
        chunk = values[start:start + batch_size]
        items = {str(index): value for index, value in enumerate(chunk, 1)}
        payload, result = _call_translator(llm, INN_SYSTEM_PROMPT, items, max_tokens=4000)
        _add_usage(usage, result)
        ru_payload = payload.get("ru") if isinstance(payload.get("ru"), dict) else {}
        en_payload = payload.get("en") if isinstance(payload.get("en"), dict) else {}
        for key, source in items.items():
            ru = str(ru_payload.get(key) or "").strip()
            en = str(en_payload.get(key) or "").strip()
            if _cyrillic_inn_ok(source, ru) and _english_inn_ok(source, en):
                accepted[source] = {"ru": ru[:1].upper() + ru[1:], "en": en[:1].upper() + en[1:]}
            else:
                logger.warning("Rejected INN translation %r → %r / %r", source, ru, en)
    return accepted, usage


def translate_active_ingredient(
    value: Any,
    *,
    llm=None,
    product_id: Optional[int] = None,
) -> tuple[Optional[tuple[str, str]], Optional[dict]]:
    """(RU, EN) МНН из памяти; новые вещества — коротким запросом, если есть llm."""
    keys = split_inn(value)
    if not keys:
        return None, None
    found = lookup(INN_NAMESPACE, keys)
    missing = [key for key in dict.fromkeys(keys) if key not in found]
    usage = None
    if missing and llm is not None:
        translated, usage = translate_inn_values(missing, llm)
        if translated:
            remember(INN_NAMESPACE, translated)
            found.update(translated)
    if any(key not in found for key in keys):
        logger.info("Medicine %s: INN %r is not fully translated", product_id, value)
        return None, usage
    return (
        " + ".join(found[key]["ru"] for key in keys),
        " + ".join(found[key]["en"] for key in keys),
    ), usage


def propagate_inn_translations(keys: set[str]) -> int:
    """Перевод МНН из памяти → active_ingredient в переводах товаров с этим веществом.

    Обновляются существующие переводы (товары после AI-обработки) с хотя бы
    одним веществом из keys, если переведены все вещества комбинации.
    Возвращает число обновлённых строк перевода.
    """
    from apps.catalog.models import MedicineProduct, MedicineProductTranslation

    by_value: dict[tuple[str, str], list[int]] = {}
    rows = MedicineProduct.objects.exclude(active_ingredient="").values_list("pk", "active_ingredient")
    products = [(pk, split_inn(value)) for pk, value in rows.iterator(chunk_size=5000)]
    products = [(pk, parts) for pk, parts in products if keys.intersection(parts)]
    found = peek(INN_NAMESPACE, {p for _, parts in products for p in parts})
    for pk, parts in products:
        if all(part in found for part in parts):
            value = (
                " + ".join(found[p]["ru"] for p in parts)[:300],
                " + ".join(found[p]["en"] for p in parts)[:300],
            )
            by_value.setdefault(value, []).append(pk)
    updated = 0
    for (ru, en), product_ids in by_value.items():
        for locale, text in (("ru", ru), ("en", en)):
            updated += (
                MedicineProductTranslation.objects.filter(product_id__in=product_ids, locale=locale)
                .exclude(active_ingredient=text)
                .update(active_ingredient=text)
            )
    return updated


# ── Абзацы инструкций ─────────────────────────────────────────────────────


# Буква бренда после fold_tr → все её написания в турецком тексте.
_TR_LETTERS = {"c": "cCçÇ", "g": "gGğĞ", "i": "iIıİ", "o": "oOöÖ", "s": "sSşŞ", "u": "uUüÜ"}


@lru_cache(maxsize=512)
def _brand_re(brand: str) -> re.Pattern:
    parts = []
    for char in fold_tr(brand):
        if char == " ":
            parts.append(r"\s+")
        elif char in _TR_LETTERS:
            parts.append(f"[{_TR_LETTERS[char]}]")
        elif char.isalpha():
            parts.append(f"[{char}{char.upper()}]")
        else:
            parts.append(re.escape(char))
    # «MAJEZIK'in», «MAJEZİK’i», «EPORON®'u» — знак ® и суффикс после апострофа.
    return re.compile(rf"(?<!\w)({''.join(parts)})[®™]*(?:['’`](\w+))?(?!\w)")


def _canonical_suffix(suffix: str) -> str:
    """Суффикс по гармонии гласных → одна форма: 'ı/'ü/'yu → 'i, 'nın → 'in, 'ya → 'e, 'te → 'de."""
    folded = re.sub(r"^[yns](?=[aeiou])", "", fold_tr(suffix))
    return re.sub(r"^t", "d", folded).translate(str.maketrans("au", "ei"))


def normalize_paragraph(text: str, brand: str = "") -> str:
    """Ключ абзаца в памяти: нормализация translation_memory, бренд товара → BRAND_TOKEN.

    Метка ставится на бренд с заглавной буквы («MAJEZIK», «Majezik»); слово
    со строчной («grip») — обычный текст. Знак ® после бренда в ключ не
    попадает: «EPORON®'u» и «MAJEZIK'i» — один абзац.
    """
    text = normalize_source_text(text)
    if not brand:
        return text

    def mask(match: re.Match) -> str:
        if not match.group(1)[0].isupper():
            return match.group(0)
        return BRAND_TOKEN + (f"'{_canonical_suffix(match.group(2))}" if match.group(2) else "")

    return _brand_re(brand).sub(mask, text)


def source_tab_texts(external_data: Any) -> list[str]:
    tabs = ((external_data or {}).get("attributes") or {}).get("source_tabs") or {}
    texts = []
    for key in CLINICAL_SOURCE_TABS:
        payload = tabs.get(key)
        text = payload.get("text") if isinstance(payload, dict) else payload
        if text and str(text).strip():
            texts.append(str(text))
    return texts


# Парсер ilacfiyati собирает раздел через get_text("\n"), и строчный тег внутри
# предложения (<b>, <sup>, <sub>, <a>) становится отдельной строкой: «EPORON» /
# «®» / «'u kullanmayınız.», «B» / «12» / «vitamini». По разметке 349 страниц
# так разорвана каждая 9-я граница строк (docs/MEDICINE_PARAGRAPH_SHIFT_2026-10-20.md,
# «Обрывки абзацев»).
_MARK_LINE = re.compile(r"[®™©]+")
_INDEX_LINE = re.compile(r"\d{1,3}")  # B12, D3, m2, (177Lu — <sup>/<sub>
# Индекс клеится к одиночной букве или скобке: «B» / «12», «mL/m» / «2»; число
# после слова — ячейка таблицы доз («AUGMENTİN ES miktarı» / «8» / «Günde iki kez 3 ml»).
_INDEX_BASE_END = re.compile(r"(?:(?<![^\W\d_])[^\W\d_]|\()$")
_DEGREE_LINE = re.compile(r"[o°]")  # 25 <sup>o</sup>C
_URL_LINE = re.compile(r"(?:https?://|www\.)\S+")
_SUFFIX_START = re.compile(r"['’`][a-zçğıöşü]")  # «'un», «'in» после бренда
_CLOSING_START = re.compile(r"[,.;:)\]]")
_LOWER_START = re.compile(r"[a-zçğıöşü]")
_SENTENCE_END = re.compile(r"[.:;!?]$")


def _line_kind(line: str) -> str:
    if _MARK_LINE.fullmatch(line):
        return "mark"
    if _INDEX_LINE.fullmatch(line) or _DEGREE_LINE.fullmatch(line):
        return "index"
    return "url" if _URL_LINE.fullmatch(line) else ""


def _is_caps_word(text: str) -> bool:
    """«DERHAL», «MON.LUTEC», буквица «A» — до трёх слов заглавными."""
    letters = re.sub(r"[\W\d_]", "", text)
    return bool(letters) and letters.isupper() and len(text.split()) <= 3


def _continuation_glue(paragraph: str, line: str, previous_kind: str) -> Optional[str]:
    """Чем приклеить строку к абзацу, если она продолжает его предложение; None — новый абзац.

    Строка со строчной буквы сама по себе ничего не значит: так же начинаются
    пункты списка побочных эффектов («baş ağrısı» / «bulantı»). Она клеится
    только после строки, которая не может кончать фразу: ®, индекс, ссылка,
    слово заглавными.
    """
    if _MARK_LINE.fullmatch(line) or _SUFFIX_START.match(line) or _CLOSING_START.match(line):
        return ""
    if previous_kind in ("mark", "index") or (previous_kind == "url" and _LOWER_START.match(line)):
        return " "
    if _DEGREE_LINE.fullmatch(line) and paragraph[-1:].isdigit():
        return ""
    if _SENTENCE_END.search(paragraph):
        return None
    if _INDEX_LINE.fullmatch(line) and _INDEX_BASE_END.search(paragraph):
        return ""
    if _URL_LINE.fullmatch(line):
        return " "
    if _LOWER_START.match(line) and _is_caps_word(paragraph):
        return "" if len(paragraph) == 1 else " "
    return None


def split_paragraphs(text: str) -> list[str]:
    """Текст раздела → абзацы и разделители по очереди: [абзац, "\\n", абзац, …].

    Строка, которую от предложения отрезал строчный тег, приклеивается к
    абзацу (``_continuation_glue``): иначе модель получает обрывки
    «Somatropine veya {BRAND}» и «'un içerisindeki…», склеивает их сама, и ответ
    съезжает на ключ. Через пустую строку не клеится.
    """
    parts = re.split(r"(\n+)", str(text or "").strip())
    merged = [parts[0].strip()]
    kind = ""
    for separator, line in zip(parts[1::2], parts[2::2]):
        line = line.strip()
        glue = _continuation_glue(merged[-1], line, kind) if separator == "\n" else None
        if glue is None:
            merged += [separator, line]
        else:
            merged[-1] += glue + line
        kind = _line_kind(line)
        if kind == "index" and glue is None:  # «8» — ячейка таблицы, а не индекс
            kind = ""
    return merged


def needs_translation(paragraph: str) -> bool:
    """Абзацы без слов («1.», «-», «500 mg») переносим как есть."""
    return len(re.findall(r"[^\W\d_]", paragraph)) >= 2


def _looks_russian(source: str, ru: str) -> bool:
    if len(re.findall(r"[^\W\d_]", source)) < 20:
        return True
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", ru))
    if not cyrillic or looks_untranslated_turkish(ru):
        return False
    # Бренд (слово заглавными) переносится латиницей и переводить его не нужно:
    # «5. DERMOVATE'IN SAKLANMASI» → «5. Хранение DERMOVATE» — 8 кириллических букв.
    kept = {fold_tr(word) for word in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", ru)}
    translatable = sum(
        len(word)
        for word in re.findall(r"[^\W\d_]+", source)
        if not (word.isupper() and fold_tr(word) in kept)
    )
    return cyrillic >= min(10, translatable // 2)


# Подписи реквизитов в конце инструкции; имена фирм и адреса не переводятся.
_REQUISITE_LABELS = (
    (r"ruhsat\s+sahibi", "Владелец регистрационного удостоверения", "Marketing authorisation holder"),
    (r"[üu]retim\s+yeri", "Место производства", "Manufacturing site"),
    (r"[üu]retici", "Производитель", "Manufacturer"),
    (r"[iİı]mal\s+eden", "Производитель", "Manufacturer"),
    (r"[iİı]thalat[çc][ıi]", "Импортёр", "Importer"),
    (r"faks", "Факс", "Fax"),
    (r"e-?posta", "Эл. почта", "E-mail"),
    (r"tel", "Тел.", "Tel."),
)


def translate_requisites(line: str) -> tuple[str, str]:
    """Строка реквизитов кодом: подписи — словарём, фирма и адрес — как в источнике."""
    ru = en = normalize_source_text(line)
    for pattern, ru_label, en_label in _REQUISITE_LABELS:
        label = re.compile(rf"(?<![\w]){pattern}(?=\s*:)", re.IGNORECASE)
        ru, en = label.sub(ru_label, ru), label.sub(en_label, en)
    return ru, en


def paragraph_problems(source: str, ru: str, en: str) -> list[str]:
    """Пустой список — перевод абзаца годится в память и в карточку."""
    problems = []
    if not ru or not en:
        return ["missing"]
    if not doses_match(source, ru) or not doses_match(source, en):
        problems.append("fact_mismatch")
    # Фирма/адрес («Ruhsat sahibi: … A.Ş.») остаётся латиницей — это не брак.
    if not is_proper_name_line(source) and not _looks_russian(source, ru):
        problems.append("ru_not_russian")
    if re.search(r"[А-Яа-яЁё]", en):
        problems.append("en_has_cyrillic")
    if len(source) >= 200 and min(len(ru), len(en)) / len(source) < 0.5:
        problems.append("too_short")
    if BRAND_TOKEN in source and (BRAND_TOKEN not in ru or BRAND_TOKEN not in en):
        problems.append("brand_token_missing")
    # Чужой перевод: номер заголовка, числа, длина, RU≠EN, понятия, частота.
    problems.extend(item_problems(source, ru, en))
    return problems


def paragraph_items(batch: list[str]) -> dict[str, str]:
    return {str(index): text for index, text in enumerate(batch, 1)}


def _paragraph_answers(payload: Any, keys: list[str]) -> tuple[list[str], list[str]]:
    """RU и EN по ключам из ответа {"1": {"ru", "en"}} или прежнего
    {"ru": {"1"}, "en": {"1"}} (пакеты Batch API, отправленные до смены формата)."""
    payload = payload if isinstance(payload, dict) else {}
    if isinstance(payload.get("ru"), dict) or isinstance(payload.get("en"), dict):
        ru, en = (payload.get(locale) if isinstance(payload.get(locale), dict) else {} for locale in ("ru", "en"))
        rows = [{"ru": ru.get(key), "en": en.get(key)} for key in keys]
    else:
        rows = [payload.get(key) if isinstance(payload.get(key), dict) else {} for key in keys]
    return [str(row.get("ru") or "").strip() for row in rows], [str(row.get("en") or "").strip() for row in rows]


def check_paragraph_payload(items: dict[str, str], payload: Any) -> tuple[dict, dict]:
    """Ответ модели по абзацам → (принятые {текст: {ru, en}}, отклонённые {текст: причины}).

    Кроме проверок каждого абзаца ищется сдвиг ответа: модель пропустила
    элемент, и ключам достались переводы соседних абзацев. Тогда отклоняется
    весь запрос (``shifted``): он короткий, и повтор дешевле риска принять
    чужой перевод на границе сдвига. Сдвигом считается и ответ, где у части
    абзацев нет перевода: в пакете 20.10.2026 так выглядели 86 % запросов со
    сдвигом (модель пропускала абзац и заканчивала ответ на ключ раньше).
    """
    keys = list(items)
    ru_texts, en_texts = _paragraph_answers(payload, keys)
    answered = [bool(ru and en) for ru, en in zip(ru_texts, en_texts)]
    shifted = (any(answered) and not all(answered)) or bool(
        request_shift([items[key] for key in keys], ru_texts, en_texts)
    )
    accepted, rejected = {}, {}
    for key, ru, en in zip(keys, ru_texts, en_texts):
        source = items[key]
        problems = paragraph_problems(source, ru, en)
        if shifted:
            problems.append("shifted")
        if problems:
            rejected[source] = problems
        else:
            accepted[source] = {"ru": ru, "en": en}
    return accepted, rejected


def paragraph_batches(paragraphs: list[str]) -> list[list[str]]:
    """Абзацы → запросы: не больше PARAGRAPH_BATCH_ITEMS абзацев и PARAGRAPH_BATCH_CHARS символов."""
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for paragraph in paragraphs:
        if current and (len(current) >= PARAGRAPH_BATCH_ITEMS or size + len(paragraph) > PARAGRAPH_BATCH_CHARS):
            batches.append(current)
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph)
    if current:
        batches.append(current)
    return batches


def translate_paragraphs(
    paragraphs: list[str],
    llm,
    *,
    on_batch: Optional[Callable[[dict], None]] = None,
) -> tuple[dict, dict, dict]:
    """Перевод новых абзацев моделью: (принятые, причины отказа, usage).

    Абзацы с отказом повторяются один раз отдельным коротким запросом.
    """
    accepted: dict[str, dict[str, str]] = {}
    rejected: dict[str, list[str]] = {}
    usage = _new_usage()

    def run(batch: list[str]) -> None:
        items = paragraph_items(batch)
        payload, result = _call_translator(
            llm, PARAGRAPH_SYSTEM_PROMPT, items, max_tokens=PARAGRAPH_MAX_TOKENS, prompt=paragraph_user_prompt
        )
        _add_usage(usage, result)
        batch_accepted, batch_rejected = check_paragraph_payload(items, payload)
        accepted.update(batch_accepted)
        rejected.update(batch_rejected)
        for source in batch_accepted:
            rejected.pop(source, None)

    for batch in paragraph_batches(paragraphs):
        run(batch)
    retry = [paragraph for paragraph in paragraphs if paragraph in rejected]
    for batch in paragraph_batches(retry):
        run(batch)
    usage["retried_paragraphs"] = len(retry)
    return accepted, rejected, usage


def translate_sections_by_paragraph(
    sections: dict[str, str],
    llm,
    *,
    product_id: Optional[int] = None,
    brand: str = "",
) -> dict[str, Any]:
    """Разделы инструкции: абзацы из памяти, новые — моделью короткими запросами.

    ``brand`` (``paragraph_brand``) в ключах памяти заменяется меткой и
    подставляется обратно в перевод.

    Возвращает {"ru": {поле: текст}, "en": {...}, "quality": {...}, "usage": {...}}.
    Раздел попадает в ru/en, только если переведены все его абзацы.
    """
    structure = {field: split_paragraphs(text) for field, text in sections.items()}
    unique = list(dict.fromkeys(
        normalize_paragraph(part, brand)
        for parts in structure.values()
        for part in parts[::2]
        if needs_translation(part) and not is_proper_name_line(part)
    ))
    found = lookup(PARAGRAPH_NAMESPACE, unique) if unique else {}
    cached = len(found)
    missing = [paragraph for paragraph in unique if paragraph not in found]
    usage = _new_usage()
    rejected: dict[str, list[str]] = {}
    if missing and llm is not None:
        accepted, rejected, usage = translate_paragraphs(missing, llm)
        if accepted:
            remember(PARAGRAPH_NAMESPACE, accepted)
            found.update(accepted)
    elif missing:
        rejected = {paragraph: ["missing"] for paragraph in missing}

    result: dict[str, Any] = {"ru": {}, "en": {}, "quality": {}, "usage": usage}
    for field, parts in structure.items():
        texts = {"ru": [], "en": []}
        problems: set[str] = set()
        for index, part in enumerate(parts):
            if index % 2:  # разделитель «\n…»
                texts["ru"].append(part)
                texts["en"].append(part)
                continue
            key = normalize_paragraph(part, brand)
            if not needs_translation(part):
                texts["ru"].append(key)
                texts["en"].append(key)
            elif is_proper_name_line(part):
                ru, en = translate_requisites(part)
                texts["ru"].append(ru)
                texts["en"].append(en)
            elif key in found:
                texts["ru"].append(found[key]["ru"].replace(BRAND_TOKEN, brand))
                texts["en"].append(found[key]["en"].replace(BRAND_TOKEN, brand))
            else:
                problems.update(rejected.get(key) or ["missing"])
        source_text = sections[field]
        complete = not problems
        quality = {
            "source_length": len(source_text),
            "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            "paragraphs": len(parts[::2]),
            "ru_complete": complete,
            "en_complete": complete,
            "complete": complete,
        }
        if complete:
            for locale in ("ru", "en"):
                result[locale][field] = "".join(texts[locale]).strip()
        else:
            quality["problems"] = sorted(problems)
            if "fact_mismatch" in problems:
                quality["fact_mismatch"] = ["ru", "en"]
            logger.warning("Medicine %s section %s incomplete: %s", product_id, field, sorted(problems))
        quality["ru_length"] = len(result["ru"].get(field, ""))
        quality["en_length"] = len(result["en"].get(field, ""))
        result["quality"][field] = quality
    usage.update({
        "paragraphs_total": len(unique),
        "paragraphs_cached": cached,
        "paragraphs_translated": len(missing) - len(rejected),
        "paragraphs_rejected": len(rejected),
    })
    return result
