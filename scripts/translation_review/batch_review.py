"""Проверка памяти абзацев Claude Haiku через Message Batches API (TD-025). В БД ничего не пишет.

Запуск в контейнере backend (ключ — ANTHROPIC_API_KEY из окружения, не печатается); данные — через
stdin/stdout, состояние в контейнере не хранится:
  ... python batch_review.py submit review EFFORT [MAX_TOKENS] < chunks.jsonl  → {"batch_id", "requests"}
  ... python batch_review.py submit verify EFFORT < flagged.jsonl    → {"batch_id", "requests"}
  ... python batch_review.py submit fragment EFFORT < fragments.jsonl  → {"batch_id", "requests"}
  ... python batch_review.py status BATCH_ID [BATCH_ID ...]
  ... python batch_review.py results BATCH_ID > results.jsonl
chunks.jsonl — строки {"k", "items": [{i, tr, ru, en, hint}]} (prepare_chunks.py);
flagged.jsonl — строки {"k", "items": [...], "issues": [...]} (collect_fixes.py flagged).
Проверка — два прохода (high и xhigh), их замечания объединяются. На разметке пилота 4 после
скептика исправлено 96 % критичных, 60 % серьёзных и 31 % мелких ошибок (один проход high —
89 / 45 / 19 %); max не укладывается в 32 000 токенов ответа.
Промпты — как в workflow run1-memory-review 23.10 (проверяющий, затем скептик), но часть передаётся
в сообщении, а ответ — строгий JSON по схеме (output_config.format).
"""
import json, sys

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

MODEL = "claude-haiku-5-5"

REVIEW = {
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

VERIFY = {
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

FRAGMENT = {
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

RULES = """Context: a translation memory of paragraphs from Turkish drug leaflets (patient information), translated into Russian (ru) and English (en) for a pharmacy website. Each item: i = record id (copy it exactly), tr = Turkish source, ru, en, hint = an automatic dictionary check (it is often a false alarm: a synonym or paraphrase is fine). Items come from different drugs and are unrelated to each other. {BRAND} is a placeholder for the drug's brand name: keep it exactly as {BRAND} in any fix. Units may be localized (mg→мг, IU→МЕ, 24 saat→сутки); thousands in Russian as "1000"/"10 000". Fragments (list items, half sentences, text cut mid-word) must stay fragments: translate only what is in tr, never add the rest of the sentence.

Typical errors to look for:
- the ru or en is the translation of a DIFFERENT paragraph (same topic is not enough: compare the actual content);
- negation lost or flipped ("olmayan", "-mez/-maz", "değil", "kullanmayınız"), "unless" ("-medikçe/-madıkça"), "en az" (at least) / "en fazla" (at most) lost;
- wrong number, dose, frequency, age, duration;
- a wrong medical term, condition or drug class (e.g. "Dijital" = digitalis, not "digital"); a clinically relevant part (warning, condition, who must do what) omitted or added;
- Turkish left untranslated.

Severity: critical = meaning reversed or wrong (translation of a different paragraph, wrong dose/number/frequency/age, negation flipped, wrong drug class or condition, contraindication turned into indication); major = clinically relevant part omitted/added/distorted or a wrong medical term; minor = small loss that could still mislead a patient. Do NOT report style, word order or acceptable paraphrases."""

REVIEW_SYSTEM = RULES + """

The user message is a JSON array of about 40 items. Check EVERY item: do ru and en faithfully render tr? Use the hint only as a pointer. Return only items with real problems, each with a full corrected paragraph for the language(s) that need it (minimal edit: keep everything else as is). Set checked to the number of items you checked."""

VERIFY_SYSTEM = RULES + """

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
FRAGMENT_SYSTEM = """Context: a translation memory of paragraphs from Turkish drug leaflets, translated into Russian (ru) and English (en) for a pharmacy website. {BRAND} is a placeholder for the brand name. The Turkish source (tr) of each item ends without final punctuation: it is either a heading / list item, or a sentence cut by PDF extraction (the rest of the sentence is in the next paragraph, which is translated separately). A reviewer replaced the OLD translation with a NEW one. Decide for each item which version a patient should read on the website:
- "new" if the OLD translation contradicts tr, is the translation of a different paragraph, or adds clinical content that tr does not support: a prohibition or negation, a dose, number, age or frequency, a condition, a claim (e.g. tr "{BRAND}'in yiyecek ve içecek ile kullanılması" is a heading "Use of {BRAND} with food and drink", not "do not take with food"); also choose "new" for a heading or list item that OLD turned into a sentence.
- "old" if OLD faithfully renders everything in tr and only completes the cut sentence in the obvious way that the visible words imply (e.g. tr "... bu tıbbi ürünü al" = "do not take this medicine" when the context is a warning; "Ayrıca karşılaştığınız yan etkileri" = "Also report the side effects you experience"), while NEW leaves a dangling broken phrase, reverses the evident meaning or is ungrammatical.
- "merged" if OLD has a real error in the part covered by tr (wrong term, number, missing clause) but its natural ending is fine: write the full corrected ru and en keeping the natural ending; never invent a dose, number, prohibition or negation.
Return one entry per item."""


def params(kind, effort, row, max_tokens=None):
    if kind == "fragment":
        system, schema = FRAGMENT_SYSTEM, FRAGMENT
        content = json.dumps(row["items"], ensure_ascii=False)
    elif kind == "review":
        system, schema = REVIEW_SYSTEM, REVIEW
        content = json.dumps(row["items"], ensure_ascii=False)
    else:
        system, schema = VERIFY_SYSTEM, VERIFY
        content = ("Items (JSON):\n" + json.dumps(row["items"], ensure_ascii=False)
                   + "\n\nFlagged issues with proposed fixes (JSON):\n" + json.dumps(row["issues"], ensure_ascii=False))
    return MessageCreateParamsNonStreaming(
        model=MODEL,
        # На xhigh/max размышления длиннее: 16 000 обрывали ответ (замер 25.10).
        # Части с множеством ошибок (верх ранжирования) дошлются с большим лимитом.
        max_tokens=max_tokens or (16000 if effort in ("low", "medium", "high") else 32000),
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": content}],
    )


def main():
    client = anthropic.Anthropic(max_retries=6)
    cmd = sys.argv[1]
    if cmd == "submit":
        kind, effort = sys.argv[2], sys.argv[3]
        max_tokens = int(sys.argv[4]) if len(sys.argv) > 4 else None
        rows = [json.loads(line) for line in sys.stdin if line.strip()]
        reqs = [Request(custom_id=f"{kind[0]}-{r['k']}", params=params(kind, effort, r, max_tokens)) for r in rows]
        batch = client.messages.batches.create(requests=reqs)
        print(json.dumps({"batch_id": batch.id, "requests": len(reqs)}))
    elif cmd == "status":
        for bid in sys.argv[2:]:
            b = client.messages.batches.retrieve(bid)
            print(json.dumps({"batch_id": bid, "status": b.processing_status, **b.request_counts.to_dict()}))
    elif cmd == "results":
        for r in client.messages.batches.results(sys.argv[2]):
            out = {"id": r.custom_id, "type": r.result.type}
            if r.result.type == "succeeded":
                m = r.result.message
                out["stop"] = m.stop_reason
                out["text"] = "".join(b.text for b in m.content if b.type == "text")
                out["usage"] = {"input": m.usage.input_tokens, "output": m.usage.output_tokens,
                                "cache_read": m.usage.cache_read_input_tokens or 0,
                                "cache_write": m.usage.cache_creation_input_tokens or 0}
            elif r.result.type == "errored":
                out["error"] = str(r.result.error)
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    else:
        sys.exit("usage: submit review|verify EFFORT | status ID... | results ID")


if __name__ == "__main__":
    main()
