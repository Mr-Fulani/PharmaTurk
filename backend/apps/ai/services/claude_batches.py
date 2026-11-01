"""Запросы проверки переводов через Message Batches API Claude (вдвое дешевле обычных; TD-025, TD-031).

Вид запроса (``KINDS``) задаёт системный промпт и схему ответа. Вход — JSON lines: строка
``{"k": номер части, "items": [...]}``, у скептиков ещё ``issues`` или ``decisions`` первого прохода.
В БД ничего не пишет.

Проверка памяти — два прохода review (high и xhigh), их замечания объединяются. На разметке пилота 4
после скептика исправлено 96 % критичных, 60 % серьёзных и 31 % мелких ошибок (один проход high —
89 / 45 / 19 %); max не укладывается в 32 000 токенов ответа.
"""

from __future__ import annotations

import json

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from django.conf import settings

from apps.ai.services.memory_review import PRICE_INPUT

MODEL = "claude-haiku-5-5"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
CHARS_PER_TOKEN = 3  # грубо, для оценки в режиме показа

_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "checked": {"type": "integer"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer", "description": "the item id exactly as given"},
                    "lang": {"type": "string", "enum": ["ru", "en", "both"]},
                    "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                    "category": {"type": "string", "enum": ["wrong_paragraph", "meaning_changed", "omission", "addition",
                                                            "number", "term", "untranslated", "grammar_unclear"]},
                    "problem": {"type": "string", "description": "at most 25 words"},
                    "ru_fix": {"type": "string", "description": "full corrected Russian paragraph, or empty if RU is fine"},
                    "en_fix": {"type": "string", "description": "full corrected English paragraph, or empty if EN is fine"},
                },
                "required": ["i", "lang", "severity", "category", "problem", "ru_fix", "en_fix"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["checked", "issues"],
    "additionalProperties": False,
}

_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "real": {"type": "boolean", "description": "the CURRENT ru/en really has a meaning error"},
                    "severity": {"type": "string", "enum": ["critical", "major", "minor", "none"]},
                    "fix_was_wrong": {"type": "boolean", "description": "the proposed fix itself is unfaithful or incomplete"},
                    "ru_final": {"type": "string", "description": "final full RU paragraph if RU must change, else empty"},
                    "en_final": {"type": "string", "description": "final full EN paragraph if EN must change, else empty"},
                    "reason": {"type": "string", "description": "at most 25 words"},
                },
                "required": ["i", "real", "severity", "fix_was_wrong", "ru_final", "en_final", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}

_FRAGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "choice": {"type": "string", "enum": ["old", "new", "merged"]},
                    "ru_final": {"type": "string", "description": "for merged: full RU paragraph, else empty"},
                    "en_final": {"type": "string", "description": "for merged: full EN paragraph, else empty"},
                    "reason": {"type": "string", "description": "at most 25 words"},
                },
                "required": ["i", "choice", "ru_final", "en_final", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}

_INN_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "tr": {"type": "string"},
                    "ru": {"type": "string"},
                    "en": {"type": "string"},
                    "status": {"type": "string", "enum": ["ok", "fixed", "garbage", "unsure"]},
                    "reason": {"type": "string", "description": "кратко, для fixed, garbage и unsure"},
                },
                "required": ["id", "tr", "ru", "en", "status", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}

_BRAND_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "brand": {"type": "string"},
                    "ru": {"type": "string"},
                    "kind": {"type": "string", "enum": ["established", "transliteration", "abbreviation"]},
                    "note": {"type": "string", "description": "кратко, если есть сомнения"},
                },
                "required": ["i", "brand", "ru", "kind", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}

_PARAGRAPH_RULES = """Context: a translation memory of paragraphs from Turkish drug leaflets (patient information), translated into Russian (ru) and English (en) for a pharmacy website. Each item: i = record id (copy it exactly), tr = Turkish source, ru, en, hint = an automatic dictionary check (it is often a false alarm: a synonym or paraphrase is fine). Items come from different drugs and are unrelated to each other. {BRAND} is a placeholder for the drug's brand name: keep it exactly as {BRAND} in any fix. Units may be localized (mg→мг, IU→МЕ, 24 saat→сутки); thousands in Russian as "1000"/"10 000". Fragments (list items, half sentences, text cut mid-word) must stay fragments: translate only what is in tr, never add the rest of the sentence.

Typical errors to look for:
- the ru or en is the translation of a DIFFERENT paragraph (same topic is not enough: compare the actual content);
- negation lost or flipped ("olmayan", "-mez/-maz", "değil", "kullanmayınız"), "unless" ("-medikçe/-madıkça"), "en az" (at least) / "en fazla" (at most) lost;
- wrong number, dose, frequency, age, duration;
- a wrong medical term, condition or drug class (e.g. "Dijital" = digitalis, not "digital"); a clinically relevant part (warning, condition, who must do what) omitted or added;
- Turkish left untranslated.

Severity: critical = meaning reversed or wrong (translation of a different paragraph, wrong dose/number/frequency/age, negation flipped, wrong drug class or condition, contraindication turned into indication); major = clinically relevant part omitted/added/distorted or a wrong medical term; minor = small loss that could still mislead a patient. Do NOT report style, word order or acceptable paraphrases."""

_REVIEW_SYSTEM = _PARAGRAPH_RULES + """

The user message is a JSON array of about 40 items. Check EVERY item: do ru and en faithfully render tr? Use the hint only as a pointer. Return only items with real problems, each with a full corrected paragraph for the language(s) that need it (minimal edit: keep everything else as is). Set checked to the number of items you checked."""

_VERIFY_SYSTEM = _PARAGRAPH_RULES + """

You are a skeptical second reviewer. The user message has the items and the issues another reviewer flagged, with proposed fixes.
For EACH flagged i:
1. Decide yourself whether the current ru/en really has a meaning error (real). Style or acceptable paraphrase = not real.
2. If real, check the proposed fix clause by clause against tr: every condition (if / unless / until / when), negation, number and unit, who does what to whom (Turkish genitive and case endings), each list element and medical term must match tr, and nothing may be added. Reviewers often detect the error correctly but write a fix that keeps the wrong logic or garbles the sentence. If the proposed fix is wrong or incomplete, set fix_was_wrong=true and write the correct full paragraph yourself.
3. Check both languages: if the other language has the same error, fix it too.
Return one entry per flagged i with the final full paragraphs (empty for a language that needs no change)."""

# Арбитр обрывков (пилот 25.10): у абзаца, разрезанного при разборе PDF, старый перевод часто верно
# договаривает фразу, а правка «переводит только то, что есть» и оставляет на сайте ломаный хвост
# («Также побочные эффекты, с которыми вы столкнулись»), а иногда и переворачивает смысл
# («ürünü al[mayınız]» → «принимайте»). Но бывает, что старое окончание выдумано: запрет, доза, чужой абзац.
_FRAGMENT_SYSTEM = """Context: a translation memory of paragraphs from Turkish drug leaflets, translated into Russian (ru) and English (en) for a pharmacy website. {BRAND} is a placeholder for the brand name. The Turkish source (tr) of each item ends without final punctuation: it is either a heading / list item, or a sentence cut by PDF extraction (the rest of the sentence is in the next paragraph, which is translated separately). A reviewer replaced the OLD translation with a NEW one. Decide for each item which version a patient should read on the website:
- "new" if the OLD translation contradicts tr, is the translation of a different paragraph, or adds clinical content that tr does not support: a prohibition or negation, a dose, number, age or frequency, a condition, a claim (e.g. tr "{BRAND}'in yiyecek ve içecek ile kullanılması" is a heading "Use of {BRAND} with food and drink", not "do not take with food"); also choose "new" for a heading or list item that OLD turned into a sentence.
- "old" if OLD faithfully renders everything in tr and only completes the cut sentence in the obvious way that the visible words imply (e.g. tr "... bu tıbbi ürünü al" = "do not take this medicine" when the context is a warning; "Ayrıca karşılaştığınız yan etkileri" = "Also report the side effects you experience"), while NEW leaves a dangling broken phrase, reverses the evident meaning or is ungrammatical.
- "merged" if OLD has a real error in the part covered by tr (wrong term, number, missing clause) but its natural ending is fine: write the full corrected ru and en keeping the natural ending; never invent a dose, number, prohibition or negation.
Return one entry per item."""

_INN_RULES = """Задача — словарь действующих веществ лекарств: турецкое название вещества (tr) → официальное русское МНН (ru) и международное непатентованное название на английском (en). По этим названиям люди ищут лекарства в Google, поэтому нужны именно общепринятые официальные названия, а не транслитерация турецкого.

Доказательства у каждой записи: atc — коды АТХ лекарств с этим веществом (substances_in_product = 1 значит вещество в лекарстве одно, и код АТХ относится именно к нему), wikidata — названия по этому коду АТХ (ru, en, la, синонимы, who_inn). Wikidata бывает с шумом (торговое название, химическое имя, соседнее вещество) — используй как подсказку, а не как истину. Для комбинированных лекарств (substances_in_product > 1) код АТХ описывает комбинацию.

Правила для ru:
- Русское МНН как в ГРЛС/ВОЗ, кириллицей. Латиница только в обозначениях с цифрами (B12, D3, Q10) и устоявшихся сокращениях.
- Типичные ошибки транслитерации турецкого, которые надо исправить: «s» на месте латинского «c» перед e/i/y (sefotaksim → Цефотаксим, sitalopram → Циталопрам, asiklovir → Ацикловир), пропуски и замены букв (Ризперидон → Рисперидон, Будезонид → Будесонид, Адалумаб → Адалимумаб, Клофидин → Клонидин, Дапафлифлозин → Дапаглифлозин, Даруновир → Дарунавир, Дезмопресин → Десмопрессин, Идрогестерон → Дидрогестерон, Амидарон → Амиодарон).
- Русские МНН строятся из латинских по правилам: c перед e/i/y → ц, иначе к; ph → ф; th → т; y → и; x → кс; qu → кв; -ine → -ин; -one → -он; -ate → -ат; -ide → -ид; -mab → -маб; -cillin → -циллин; -cef-/-ceph- → цеф-.
- Соль и гидрат пишутся, ТОЛЬКО если они есть в tr. Анион или гидрат: вещество в родительном падеже + анион («Амиодарона гидрохлорид», «Отилония бромид», «Амлодипина безилат», «Амоксициллина тригидрат», «Бетаметазона дипропионат»). Катион: вещество в именительном + катион в родительном («Диклофенак натрия», «Аторвастатин кальция», «Эзомепразол магния»).
- Первая буква заглавная, остальное строчными (кроме B12, D3 и т.п.).
- Не МНН (витамины, минералы, растительные экстракты, вспомогательные вещества): общепринятое русское название («Цинк», «Экстракт листьев плюща»).

Правила для en:
- Рекомендованное МНН ВОЗ (rINN): «Aciclovir», «Paracetamol», «Epinephrine», «Ceftriaxone»; с солью, если она есть в tr («Amiodarone hydrochloride», «Diclofenac sodium»). Первая буква заглавная.

status: "ok" — текущие ru и en верны (не меняй их ради стиля и регистра, если смысл и написание верны); "fixed" — исправлено ru и/или en; "garbage" — tr вообще не вещество (обрывок названия, единица, форма выпуска, «Otag (Ml)») — тогда ru/en оставь текущими; "unsure" — не уверен, тогда тоже оставь текущие и объясни в reason."""

_INN_SYSTEM = "Ты фармацевт-терминолог.\n\n" + _INN_RULES + """

В сообщении — JSON-массив записей словаря (id, tr, текущие ru и en, products, atc). Для КАЖДОЙ записи реши, верны ли ru и en, и дай правильные значения: по одному объекту на запись, в том же порядке, id и tr копируй без изменений."""

_INN_VERIFY_SYSTEM = "Ты придирчивый фармацевт-терминолог, второй проверяющий.\n\n" + _INN_RULES + """

В сообщении — записи словаря и решение первого проверяющего. Перепроверь КАЖДУЮ запись:
- для "fixed": правда ли новое написание — официальное русское МНН / WHO INN (а не новая ошибка), то ли это вещество, что в tr, соль только если она есть в tr, падеж соли верный;
- для "ok": нет ли пропущенной ошибки транслитерации (сравни с латинским/английским названием и правилами);
- "garbage" — действительно не вещество.
Исправь неверное и верни итог по КАЖДОЙ записи, в том же порядке."""

# Покупатели читают латиницу на упаковке, а не по-турецки: в запросах Вордстата 29 брендов с C написаны
# «крестор», «канестен», «клеоцин», и ни одного с «дж» (24.10). Промпт 24.10 просил «c → дж», скептик
# портил бренды (ENCEF → «Энджеф»), и код исправил 421 запись. Остаток правит latin_reading.
_BRAND_RULES = """Задача — для каждого бренда турецкого лекарства (поле brand, латиница заглавными, турецкие буквы без диакритики: I может быть İ или I, C — C или Ç, S — S или Ş, G — G или Ğ, O — O или Ö, U — U или Ü) написать его по-русски кириллицей так, как его пишут и ищут в Яндексе и Google русскоязычные покупатели («мажезик», «арвелес», «дексофен», «оземпик», «нексиум», «дермовейт»). Это название пойдёт в SEO-заголовок карточки рядом с латинским: «MAJEZIK (Мажезик)».

Контекст: names — примеры полных названий товаров, inn — действующее вещество, atc — код АТХ.

Правила:
- Международный бренд, давно известный по-русски (зарегистрирован в России/СНГ или широко известен), — его устоявшееся русское написание, даже если оно не похоже на транслитерацию: NEXIUM → Нексиум, AUGMENTIN → Аугментин, VOLTAREN → Вольтарен, AERIUS → Эриус, OZEMPIC → Оземпик, DERMOVATE → Дермовейт, MIRENA → Мирена, CRESTOR → Крестор, EXELON → Экселон, VIRAMUNE → Вирамун. Только если уверен. kind = "established".
- Местный бренд — как покупатель читает латиницу на упаковке, а не по турецкому произношению: C перед E, I, Y → ц, иначе к (ENCEF → Энцеф, никогда не «дж»); J → ж (MAJEZIK → Мажезик); конечную E не читай (TEGELINE → Тегелин), кроме -TTE; X → кс; W → в; Q → к; «-flex/-fleks» → «-флекс». Если бренд явно образован от понятного слова, бери понятное русское звучание: CINKOVIT (çinko = цинк) → Цинковит. kind = "transliteration".
- Слова-описатели в бренде переводи по смыслу только если так говорят по-русски: THERMO → Термо, FORTE → Форте, PLUS → Плюс, JUNIOR → Джуниор, COLD → Колд, HOT → Хот, SPRAY → Спрей. Цифры и дефисы оставь: PEDIA-D → Педиа-Д, MON.IYOT-131 → Мон. Йод-131.
- Аббревиатуры из 2–4 согласных (CAPD, DMSO) оставляй латиницей как есть, kind = "abbreviation".
- Каждое слово с заглавной буквы, остальные строчные («Термо Фузо»), аббревиатуры как есть.
- Не добавляй действующее вещество, форму или дозировку — только бренд."""

_BRAND_SYSTEM = _BRAND_RULES + """

В сообщении — JSON-массив брендов (i, brand, count, names, inn, atc). Верни по одному объекту на КАЖДЫЙ бренд в том же порядке, brand — как в исходнике."""

_BRAND_VERIFY_SYSTEM = "Ты второй проверяющий.\n\n" + _BRAND_RULES + """

В сообщении — бренды и решение первого проверяющего. Проверь КАЖДЫЙ бренд: передано ли чтение латиницы (C → ц или к, не «дж»; J → ж), не выдуман ли «устоявшийся» русский вариант для местного турецкого бренда, не пропущено ли известное русское написание международного бренда, нет ли в ru лишнего (вещество, форма, дозировка), регистр. Исправь неверное и верни итог по КАЖДОМУ бренду в том же порядке."""


def _items(row) -> str:
    return json.dumps(row["items"], ensure_ascii=False)


def _items_with(key: str, title: str):
    def content(row) -> str:
        return f"Items (JSON):\n{_items(row)}\n\n{title} (JSON):\n{json.dumps(row[key], ensure_ascii=False)}"
    return content


KINDS = {
    "review": (_REVIEW_SYSTEM, _REVIEW_SCHEMA, _items),
    "verify": (_VERIFY_SYSTEM, _VERIFY_SCHEMA, _items_with("issues", "Flagged issues with proposed fixes")),
    "fragment": (_FRAGMENT_SYSTEM, _FRAGMENT_SCHEMA, _items),
    "inn": (_INN_SYSTEM, _INN_SCHEMA, _items),
    "inn_verify": (_INN_VERIFY_SYSTEM, _INN_SCHEMA, _items_with("decisions", "Решение первого проверяющего")),
    "brand": (_BRAND_SYSTEM, _BRAND_SCHEMA, _items),
    "brand_verify": (_BRAND_VERIFY_SYSTEM, _BRAND_SCHEMA, _items_with("decisions", "Решение первого проверяющего")),
}


def request_params(kind: str, effort: str, row: dict, model: str = MODEL, max_tokens: int | None = None):
    system, schema, content = KINDS[kind]
    return MessageCreateParamsNonStreaming(
        model=model,
        # На xhigh и max размышления длиннее: 16 000 обрывали ответ (замер 25.10). Части с множеством
        # ошибок (верх ранжирования) досылаются с большим лимитом.
        max_tokens=max_tokens or (16000 if effort in ("low", "medium", "high") else 32000),
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": content(row)}],
    )


def estimate(kind: str, rows: list[dict]) -> dict:
    """Режим показа: сколько запросов и примерная цена входа. Выход зависит от числа замечаний."""
    system, _, content = KINDS[kind]
    chars = sum(len(system) + len(content(row)) for row in rows)
    tokens = chars // CHARS_PER_TOKEN
    return {"requests": len(rows), "chars": chars, "input_tokens": tokens, "input_usd": round(tokens * PRICE_INPUT, 4)}


def _client():
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=6)


def submit(kind: str, effort: str, rows: list[dict], model: str = MODEL, max_tokens: int | None = None) -> dict:
    requests = [
        Request(custom_id=f"{kind[0]}-{row['k']}", params=request_params(kind, effort, row, model, max_tokens))
        for row in rows
    ]
    batch = _client().messages.batches.create(requests=requests)
    return {"batch_id": batch.id, "requests": len(requests)}


def status(batch_id: str) -> dict:
    batch = _client().messages.batches.retrieve(batch_id)
    return {"batch_id": batch_id, "status": batch.processing_status, **batch.request_counts.to_dict()}


def results(batch_id: str):
    """Строки для read_results: порядок ответов любой, часть определяется по id."""
    for entry in _client().messages.batches.results(batch_id):
        row = {"id": entry.custom_id, "type": entry.result.type}
        if entry.result.type == "succeeded":
            message = entry.result.message
            row["stop"] = message.stop_reason
            row["text"] = "".join(block.text for block in message.content if block.type == "text")
            row["usage"] = {
                "input": message.usage.input_tokens,
                "output": message.usage.output_tokens,
                "cache_read": message.usage.cache_read_input_tokens or 0,
                "cache_write": message.usage.cache_creation_input_tokens or 0,
            }
        elif entry.result.type == "errored":
            row["error"] = str(entry.result.error)
        yield row
