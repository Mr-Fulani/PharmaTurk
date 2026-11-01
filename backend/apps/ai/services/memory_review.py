"""Проверка памяти абзацев лекарств моделью: всё, кроме запросов к API (TD-025, TD-031).

Порядок шагов — AI_GUIDE.md, цифры и ловушки — docs/MEDICINE_TRANSLATION_KNOWLEDGE_BASE.md.

1. Словарь терминов из самой памяти: для пары «турецкая основа — русская или английская основа»
   считается, в скольких записях они встречаются вместе.
2. Запись тем подозрительнее, чем больше турецких терминов с устойчивым переводом этого перевода не
   имеют. Варианты одного абзаца из PDF (``canon``) проверяются одним представителем.
3. Ответы проверяющего, скептика и арбитра обрывков собираются в правки. Правка отсекается
   автопроверками (``rejection_reasons``); запись — только если текст не менялся с выгрузки.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict

from django.db import transaction

from apps.ai.models import AITranslationMemory
from apps.ai.services.medicine_memory import (
    BRAND_TOKEN,
    INN_NAMESPACE,
    PARAGRAPH_NAMESPACE,
    paragraph_problems,
)
from apps.ai.services.translation_files import open_text, read_jsonl

CHUNK_SIZE = 40
FRAGMENT_CHUNK_SIZE = 20
APPLY_BATCH_SIZE = 1000
# Цена Claude Haiku 5.5 в Message Batches API (половина обычной), $ за токен.
PRICE_INPUT, PRICE_OUTPUT = 0.10 / 2 / 1e6, 0.50 / 2 / 1e6
DICTIONARY_MARGIN = 0.5  # насколько правка может быть хуже старого перевода по словарю
ALIGNMENT_MIN_DF, ALIGNMENT_MAX_SHARE = 3, 0.05
ALIGNMENT_TOP, ALIGNMENT_MIN_DICE = 5, 0.1

WORD = re.compile(r"[^\W\d_]{3,}")
ELLIPSIS = re.compile(r"\.\.\.|…")
FRAGMENT_END = re.compile(r"[^\W\d_]$")
_TAIL = re.compile(r"[\s.,;:]*$")
_TAIL_MARKS = re.compile(r"[.,;:]*\s*$")


def _turkish_lower(text: str) -> str:
    return text.replace(BRAND_TOKEN, " ").replace("I", "ı").replace("İ", "i").lower()


def _translation_lower(text: str) -> str:
    return text.replace(BRAND_TOKEN, " ").lower().replace("ё", "е")


def canon(text: str) -> str:
    """Один ключ для вариантов абзаца из PDF: апострофы, цифры OCR, пробелы, хвостовая пунктуация."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s*['’`´ʼ]\s*", "'", text)
    text = re.sub(r"(?<=\d)[oO](?=\d)|(?<=\d)[oO]\b|\b[oO](?=\d)", "0", text)
    text = re.sub(r"(?<=\d)[lI](?=\d)|\b[lI](?=\d)", "1", text)
    return re.sub(r"\s+", " ", text).strip(" .;,")


def export_memory(path) -> int:
    """Выгрузка абзацев и МНН в JSON lines (только чтение)."""
    rows = (
        AITranslationMemory.objects.filter(namespace__in=[PARAGRAPH_NAMESPACE, INN_NAMESPACE])
        .order_by("pk")
        .values_list("pk", "namespace", "source_text", "ru_text", "en_text", "hits", "source_log_id")
    )
    written = 0
    with open_text(path, "wt") as handle:
        for pk, namespace, source, ru, en, hits, log_id in rows.iterator(chunk_size=2000):
            handle.write(json.dumps(
                {"id": pk, "ns": namespace, "tr": source, "ru": ru, "en": en, "hits": hits, "log": log_id},
                ensure_ascii=False,
            ) + "\n")
            written += 1
    return written


def _vocabulary(docs, limit: float) -> dict[str, int]:
    frequency = Counter(stem for doc in docs for stem in doc)
    return {stem: count for stem, count in frequency.items() if ALIGNMENT_MIN_DF <= count <= limit}


def build_alignment(records) -> dict:
    """Словарь по выгрузке: {"N", "tr_df", "ru"/"en": {основа: [[перевод, dice, P(перевод|основа)], ...]}}."""
    tr_docs, translated = [], {"ru": [], "en": []}
    for record in records:
        if record["ns"] != PARAGRAPH_NAMESPACE:
            continue
        tr_docs.append(tuple({word[:5] for word in WORD.findall(_turkish_lower(record["tr"]))}))
        for lang in translated:
            translated[lang].append(tuple({word[:6] for word in WORD.findall(_translation_lower(record[lang]))}))
    limit = ALIGNMENT_MAX_SHARE * len(tr_docs)
    tr_df = _vocabulary(tr_docs, limit)
    postings = defaultdict(list)
    for index, doc in enumerate(tr_docs):
        for stem in doc:
            if stem in tr_df:
                postings[stem].append(index)
    result = {"N": len(tr_docs), "tr_df": tr_df, "ru": {}, "en": {}}
    for lang, docs in translated.items():
        lang_df = _vocabulary(docs, limit)
        docs = [tuple(stem for stem in doc if stem in lang_df) for doc in docs]
        for stem, indexes in postings.items():
            together = Counter()
            for index in indexes:
                together.update(docs[index])
            if not together:
                continue
            scored = sorted(
                ((2 * count / (tr_df[stem] + lang_df[other]), other, count) for other, count in together.items()),
                key=lambda row: (-row[0], row[1]),
            )
            result[lang][stem] = [
                [other, round(dice, 3), round(count / tr_df[stem], 3)]
                for dice, other, count in scored[:ALIGNMENT_TOP]
                if dice >= ALIGNMENT_MIN_DICE
            ]
    return result


class Alignment:
    """Подозрения словаря: термин исходника без своего обычного перевода."""

    MIN_PROBABILITY, MIN_DF = 0.5, 5

    def __init__(self, data: dict):
        self.data = data

    def best_probability(self, lang: str, stem: str) -> float:
        return max([p for _, _, p in self.data[lang].get(stem) or []] or [0])

    def _usable(self, lang: str, stem: str) -> bool:
        return (
            bool(self.data[lang].get(stem))
            and self.data["tr_df"].get(stem, 0) >= self.MIN_DF
            and self.best_probability(lang, stem) >= self.MIN_PROBABILITY
        )

    @staticmethod
    def _terms(source: str) -> dict[str, str]:
        terms: dict[str, str] = {}
        for word in WORD.findall(_turkish_lower(source)):
            terms.setdefault(word[:5], word)
        return terms

    def gaps(self, source: str, lang: str, text: str) -> list[tuple[str, str, list[str]]]:
        """[(основа, слово исходника, обычные переводы)] терминов, которых нет в text."""
        stems = {word[:6] for word in WORD.findall(_translation_lower(text))}
        found = []
        for stem, word in self._terms(source).items():
            if not self._usable(lang, stem):
                continue
            usual = [r for r, dice, p in self.data[lang][stem] if dice >= 0.2 or p >= 0.3]
            has_usual = any(
                any(s[:(4 if len(r) <= 5 else 5)] == r[:(4 if len(r) <= 5 else 5)] for s in stems) for r in usual
            )
            if not has_usual:
                found.append((stem, word, usual))
        return found

    def score(self, source: str, ru: str, en: str) -> float:
        return sum(
            self.best_probability(lang, stem)
            for lang, text in (("ru", ru), ("en", en))
            for stem, _, _ in self.gaps(source, lang, text)
        )

    def suspicion(self, record: dict) -> float:
        """Оценка записи: длинный абзац с множеством терминов не должен всплывать только из-за длины."""
        eligible = sum(
            1 for stem in self._terms(record["tr"])
            if self.data["tr_df"].get(stem, 0) >= self.MIN_DF and self.best_probability("ru", stem) >= self.MIN_PROBABILITY
        )
        return self.score(record["tr"], record["ru"], record["en"]) / (1 + 0.15 * eligible)


def _hint(alignment: Alignment, record: dict, forms: dict) -> str:
    parts = []
    for lang in ("ru", "en"):
        for _, word, usual in alignment.gaps(record["tr"], lang, record[lang]):
            expected = [forms[lang][stem].most_common(1)[0][0] for stem in usual[:2] if forms[lang][stem]]
            parts.append(f"{lang.upper()} lacks the usual translation of '{word}' (usually: {' / '.join(expected) or '?'})")
    return "; ".join(parts[:4])


def build_chunks(records, alignment: Alignment, *, seen=(), skip_sources=(), chunk_size=CHUNK_SIZE, limit=0):
    """Непроверенные записи → (части, группы вариантов, id для следующего запуска, статистика).

    seen — id уже проверенных записей: их варианты тоже пропускаются. skip_sources — исходники, переведённые
    со скептиком. Части идут по убыванию подозрительности; limit — первые N представителей (пилот).
    """
    paragraphs, empty = [], 0
    forms = {"ru": defaultdict(Counter), "en": defaultdict(Counter)}
    for record in records:
        if record["ns"] != PARAGRAPH_NAMESPACE:
            continue
        if not record["ru"] or not record["en"]:
            empty += 1
            continue
        paragraphs.append(record)
        for lang in forms:
            for word in WORD.findall(_translation_lower(record[lang])):
                forms[lang][word[:6]][word] += 1
    seen = set(seen)
    skip_sources = set(skip_sources)
    seen |= {record["id"] for record in paragraphs if record["tr"] in skip_sources}
    seen_canon = {canon(record["tr"]) for record in paragraphs if record["id"] in seen}

    groups = defaultdict(list)
    for record in paragraphs:
        key = canon(record["tr"])
        if record["id"] not in seen and key not in seen_canon:
            groups[key].append(record)
    representatives = []
    for members in groups.values():
        representative = min(members, key=lambda record: (-record["hits"], record["id"]))
        representatives.append((alignment.suspicion(representative), representative, [m["id"] for m in members]))
    representatives.sort(key=lambda row: (-row[0], row[1]["id"]))
    if limit:
        representatives = representatives[:limit]

    chunks = []
    for start in range(0, len(representatives), chunk_size):
        items = [
            {"i": record["id"], "tr": record["tr"], "ru": record["ru"], "en": record["en"],
             "hint": _hint(alignment, record, forms)}
            for _, record, _ in representatives[start:start + chunk_size]
        ]
        chunks.append({"k": len(chunks), "items": items})
    variants = {str(record["id"]): ids for _, record, ids in representatives if len(ids) > 1}
    reviewed = sorted(seen | {i for _, _, ids in representatives for i in ids})
    stats = {
        "записей абзацев": len(paragraphs), "без перевода": empty, "уже проверено": len(seen),
        "к проверке записей": sum(len(ids) for _, _, ids in representatives),
        "представителей": len(representatives), "частей": len(chunks),
    }
    return chunks, variants, reviewed, stats


def read_chunks(path) -> dict[int, list[dict]]:
    return {row["k"]: row["items"] for row in read_jsonl(path)}


def read_results(paths, stats: Counter, usage: Counter) -> list[dict]:
    """Ответы по файлам: [{номер части: объект ответа}], у каждого прохода проверки свой файл."""
    passes = []
    for path in paths:
        answers = {}
        passes.append(answers)
        for row in read_jsonl(path):
            label = row["id"][0]
            k = int(row["id"].split("-", 1)[1])
            if row["type"] != "succeeded":
                stats[f"{label}_{row['type']}"] += 1
                continue
            usage.update(row["usage"])
            if row["stop"] != "end_turn":
                stats[f"{label}_stop_{row['stop']}"] += 1
                continue
            try:
                answers[k] = json.loads(row["text"])
            except ValueError:
                stats[f"{label}_bad_json"] += 1
    return passes


def merged_issues(passes, k: int, items: dict) -> tuple[dict, int]:
    """Замечания всех проходов по части k: {id: [замечание, ...]}; чужие номера отбрасываются."""
    issues, foreign = {}, 0
    for answers in passes:
        for issue in (answers.get(k) or {}).get("issues", []):
            if issue["i"] in items:
                issues.setdefault(issue["i"], []).append(issue)
            else:
                foreign += 1
    return issues, foreign


def batch_cost(usage: Counter) -> float:
    tokens = usage["input"] + usage["cache_write"] * 1.25 + usage["cache_read"] * 0.1
    return round(tokens * PRICE_INPUT + usage["output"] * PRICE_OUTPUT, 4)


def is_fragment(source: str) -> bool:
    """Абзац кончается буквой: заголовок или фраза, разрезанная при разборе PDF."""
    return bool(FRAGMENT_END.search(source.strip()))


def flagged_rows(chunks: dict, review_paths) -> tuple[list[dict], dict]:
    """Части для скептика: только записи с замечаниями и сами замечания."""
    stats, usage = Counter(), Counter()
    passes = read_results(review_paths, stats, usage)
    rows = []
    for k in sorted(set().union(*passes)):
        items = {item["i"]: item for item in chunks[k]}
        issues, foreign = merged_issues(passes, k, items)
        stats["review_bad_id"] += foreign
        stats["chunks"] += 1
        stats["passes_missing"] += sum(1 for answers in passes if k not in answers)
        stats["flagged"] += len(issues)
        if issues:
            rows.append({"k": k, "items": [items[i] for i in issues],
                         "issues": [issue for found in issues.values() for issue in found]})
    return rows, {**stats, "usage": dict(usage), "cost_usd": batch_cost(usage)}


def fragment_rows(fixes) -> list[dict]:
    """Правки абзацев-обрывков → части для арбитра."""
    rows = [row for row in fixes if is_fragment(row["tr"])]
    return [
        {"k": start // FRAGMENT_CHUNK_SIZE, "items": [
            {"i": row["id"], "tr": row["tr"], "problem": row["problem"], "ru_old": row["ru_old"], "en_old": row["en_old"],
             "ru_new": row["ru_new"], "en_new": row["en_new"]}
            for row in rows[start:start + FRAGMENT_CHUNK_SIZE]
        ]}
        for start in range(0, len(rows), FRAGMENT_CHUNK_SIZE)
    ]


def memory_vocabulary(records) -> dict[str, set]:
    vocabulary = {"ru": set(), "en": set()}
    for record in records:
        for lang in vocabulary:
            vocabulary[lang].update(word.lower() for word in WORD.findall(record[lang] or ""))
    return vocabulary


def _cut_word(words: set, new: str, old: str) -> bool:
    """Правка кончается оборванным словом: «Зверобой (депресси» из обрывка PDF."""
    last = WORD.findall(new[-40:])
    if not last or not FRAGMENT_END.search(new.strip()):
        return False
    word = last[-1].lower()
    return word not in words and word not in {other.lower() for other in WORD.findall(old)}


def rejection_reasons(item: dict, ru_new: str, en_new: str, alignment: Alignment, vocabulary: dict) -> list[str]:
    """Почему правку нельзя записать: {BRAND}, многоточие, обрыв слова, новые замечания, словарь."""
    source, ru_old, en_old = item["tr"], item["ru"], item["en"]
    reasons = []
    if ru_new == ru_old and en_new == en_old:
        reasons.append("no_change")
    if BRAND_TOKEN in source and (BRAND_TOKEN not in ru_new or BRAND_TOKEN not in en_new):
        reasons.append("brand_token_missing")
    pairs = (("ru", ru_new, ru_old), ("en", en_new, en_old))
    if not ELLIPSIS.search(source) and any(ELLIPSIS.search(new) and not ELLIPSIS.search(old) for _, new, old in pairs):
        reasons.append("ellipsis_added")
    if any(_cut_word(vocabulary[lang], new, old) for lang, new, old in pairs if new != old):
        reasons.append("cut_word")
    fresh = set(paragraph_problems(source, ru_new, en_new)) - set(paragraph_problems(source, ru_old, en_old))
    if fresh:
        reasons.append("paragraph_problems:" + ",".join(sorted(fresh)))
    if alignment.score(source, ru_new, en_new) > alignment.score(source, ru_old, en_old) + DICTIONARY_MARGIN:
        reasons.append("dictionary_worse")
    return reasons


def collect_fixes(chunks, groups, alignment, vocabulary, review_paths, verify_paths, fragment_paths=()):
    """Ответы проходов → (правки, отклонённые, сводка). Файлы скептика читаются по порядку: повторная отправка заменяет ответ."""
    stats, review_usage, verify_usage, fragment_usage = Counter(), Counter(), Counter(), Counter()
    verdicts = {}
    for answers in read_results(fragment_paths, stats, fragment_usage):
        for answer in answers.values():
            verdicts.update({row["i"]: row for row in answer["items"]})
    passes = read_results(review_paths, stats, review_usage)
    verifies = {}
    for answers in read_results(verify_paths, stats, verify_usage):
        verifies.update(answers)

    fixes, rejected = [], []
    for k in sorted(set().union(*passes)):
        items = {item["i"]: item for item in chunks[k]}
        stats["chunks"] += 1
        stats["items"] += len(items)
        flagged = {i: found[0] for i, found in merged_issues(passes, k, items)[0].items()}
        stats["flagged"] += len(flagged)
        if flagged and k not in verifies:
            stats["chunks_without_verify"] += 1
            continue
        answered = set()
        for verdict in (verifies.get(k) or {}).get("items", []):
            i = verdict["i"]
            if i not in flagged or i in answered:
                stats["verify_bad_id"] += 1
                continue
            answered.add(i)
            if not verdict["real"]:
                stats["refuted"] += 1
                continue
            item, issue = items[i], flagged[i]
            ru_new = (verdict["ru_final"] or "").strip() or item["ru"]
            en_new = (verdict["en_final"] or "").strip() or item["en"]
            severity = verdict["severity"] if verdict["severity"] != "none" else issue["severity"]
            row = {
                "id": i, "chunk": k, "severity": severity, "category": issue["category"], "problem": issue["problem"],
                "reason": verdict["reason"], "fix_was_wrong": verdict["fix_was_wrong"], "tr": item["tr"],
                "hint": item.get("hint", ""), "ru_old": item["ru"], "ru_new": ru_new, "en_old": item["en"],
                "en_new": en_new, "variants": groups.get(str(i), [i]),
            }
            reasons = []
            if fragment_paths and is_fragment(item["tr"]):
                judged = verdicts.get(i)
                row["fragment"] = judged["choice"] if judged else None
                if not judged:
                    reasons.append("fragment_unjudged")
                elif judged["choice"] == "old":
                    reasons.append("fragment_keep_old")
                elif judged["choice"] == "merged":
                    ru_new = (judged["ru_final"] or "").strip() or ru_new
                    en_new = (judged["en_final"] or "").strip() or en_new
                    row["ru_new"], row["en_new"] = ru_new, en_new
            reasons += rejection_reasons(item, ru_new, en_new, alignment, vocabulary)
            if reasons:
                row["rejected"] = reasons
                rejected.append(row)
                stats["rejected"] += 1
            else:
                fixes.append(row)
                stats["fix_" + severity] += 1
    summary = {
        **stats, "fixes": len(fixes), "variants_covered": sum(len(row["variants"]) for row in fixes),
        "rejected_by": Counter(reason.split(":")[0] for row in rejected for reason in row["rejected"]),
        "categories": Counter(row["category"] for row in fixes),
        "fragment_choice": Counter(str(row.get("fragment")) for row in fixes + rejected if "fragment" in row),
        "cost_usd": {
            "review": batch_cost(review_usage), "verify": batch_cost(verify_usage), "fragment": batch_cost(fragment_usage),
            "total": round(batch_cost(review_usage) + batch_cost(verify_usage) + batch_cost(fragment_usage), 4),
        },
    }
    return fixes, rejected, summary


def _tail(text: str) -> str:
    # Хвост целиком: «..» и «.» — разные, вариант с одной точкой не должен получить «..».
    return _TAIL_MARKS.search(text).group(0).strip()


def _with_source_tail(text: str, representative_source: str, variant_source: str) -> str:
    if _tail(representative_source) == _tail(variant_source):
        return text
    return _TAIL.sub("", text) + _tail(variant_source)


def build_updates(records, fixes) -> list[dict]:
    """Файл записи: представитель и его варианты; хвост перевода варианта — по его собственному исходнику."""
    needed = {i for fix in fixes for i in fix["variants"]} | {fix["id"] for fix in fixes}
    memory = {record["id"]: record for record in records if record["id"] in needed}
    updates = []
    for fix in fixes:
        representative = memory[fix["id"]]
        for variant_id in sorted(set(fix["variants"]) | {fix["id"]}):
            variant = memory[variant_id]
            if variant_id == fix["id"]:
                ru, en = fix["ru_new"], fix["en_new"]
            else:
                ru = _with_source_tail(fix["ru_new"], representative["tr"], variant["tr"])
                en = _with_source_tail(fix["en_new"], representative["tr"], variant["tr"])
            if ru == variant["ru"] and en == variant["en"]:
                continue
            updates.append({
                "id": variant_id, "rep": fix["id"], "severity": fix["severity"], "src": variant["tr"],
                "ru_old": variant["ru"], "en_old": variant["en"], "ru_new": ru, "en_new": en,
            })
    return updates


def _spaces(text) -> str:
    return " ".join((text or "").split())


def plan_memory_updates(updates) -> tuple[list[tuple], Counter, list[tuple]]:
    """Что можно записать: исходник и перевод не менялись с выгрузки, новых замечаний проверки нет."""
    records = AITranslationMemory.objects.in_bulk([update["id"] for update in updates])
    rows, stats, skipped = [], Counter(), []
    for update in updates:
        record = records.get(update["id"])
        if not record or record.namespace != PARAGRAPH_NAMESPACE or record.source_text != update["src"]:
            stats["нет записи"] += 1
            skipped.append((update["id"], "нет записи"))
            continue
        if _spaces(record.ru_text) != _spaces(update["ru_old"]) or _spaces(record.en_text) != _spaces(update["en_old"]):
            stats["запись изменилась"] += 1
            skipped.append((update["id"], "запись изменилась"))
            continue
        before = set(paragraph_problems(record.source_text, record.ru_text, record.en_text))
        after = set(paragraph_problems(record.source_text, update["ru_new"], update["en_new"]))
        if after - before:
            stats["новые замечания проверки"] += 1
            skipped.append((update["id"], sorted(after - before)))
            continue
        rows.append((record, update["ru_new"], update["en_new"]))
        stats["к записи " + update["severity"]] += 1
    return rows, stats, skipped


def apply_memory_updates(rows) -> int:
    """Запись партиями, каждая в своей транзакции; записи не удаляются."""
    for start in range(0, len(rows), APPLY_BATCH_SIZE):
        with transaction.atomic():
            for record, ru, en in rows[start:start + APPLY_BATCH_SIZE]:
                record.ru_text, record.en_text = ru, en
                record.save(update_fields=["ru_text", "en_text", "updated_at"])
    return len(rows)


def verify_memory_updates(updates) -> Counter:
    records = AITranslationMemory.objects.in_bulk([update["id"] for update in updates])
    stats = Counter()
    for update in updates:
        record = records.get(update["id"])
        same = record and record.ru_text == update["ru_new"] and record.en_text == update["en_new"]
        stats["совпадает" if same else "расходится"] += 1
    return stats


def score_against_labels(fixes, rejected, labels) -> list[dict]:
    """Замер на разметке: сколько размеченных ошибок исправлено по важности, и правки вне разметки."""
    labelled = {row["idx"]: row["severity"] for row in labels}
    fixed = {row["id"] for row in fixes}
    found = fixed | {row["id"] for row in rejected}
    report = []
    for severity in ("critical", "major", "minor"):
        ids = {i for i, value in labelled.items() if value == severity}
        report.append({"severity": severity, "labelled": len(ids), "fixed": len(ids & fixed), "found": len(ids & found)})
    return report
