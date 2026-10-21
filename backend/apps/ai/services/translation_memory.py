"""Общая память переводов (``AITranslationMemory``) для всех доменов.

Единица — нормализованный исходный текст в своём namespace
(«product_description:<категория>», «medicine_paragraph», «medicine_inn»…).
Нормализация одна на всех: схлопывание пробелов и strip, регистр сохраняется
(у лекарств он значим). Записи из админки — источник правды: автоматическая
запись существующую строку не перезаписывает.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Iterable

from django.db import transaction
from django.db.models import F

from apps.ai.models import AIProcessingLog, AITranslationMemory

Translations = dict[str, dict[str, str]]
Translator = Callable[[list[str]], tuple[Translations, dict[str, Any]]]


def normalize_source_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def source_hash(text: Any) -> str:
    return hashlib.sha256(normalize_source_text(text).encode("utf-8")).hexdigest()


def _unique_texts(texts: Iterable[Any]) -> dict[str, str]:
    """hash → нормализованный текст, пустые и повторы в батче — один раз."""
    result: dict[str, str] = {}
    for text in texts:
        normalized = normalize_source_text(text)
        if normalized:
            result.setdefault(source_hash(normalized), normalized)
    return result


def lookup(
    namespace: str,
    texts: Iterable[Any],
    *,
    log_statuses: Iterable[str] | None = None,
) -> Translations:
    """Готовые переводы без LLM: {нормализованный текст: {"ru", "en"}}.

    ``log_statuses`` — переиспользовать только записи, чей исходный лог в этих
    статусах. Записи без лога подходят всегда: ручная правка в админке
    отвязывает запись от лога.
    """
    by_hash = _unique_texts(texts)
    if not by_hash:
        return {}
    allowed = set(log_statuses) if log_statuses is not None else None
    found: Translations = {}
    used_ids = []
    rows = AITranslationMemory.objects.filter(namespace=namespace, source_hash__in=by_hash).select_related("source_log")
    for entry in rows:
        if not (entry.ru_text and entry.en_text):
            continue
        if allowed is not None and entry.source_log is not None and entry.source_log.status not in allowed:
            continue
        found[by_hash[entry.source_hash]] = {"ru": entry.ru_text, "en": entry.en_text}
        used_ids.append(entry.pk)
    if used_ids:
        AITranslationMemory.objects.filter(pk__in=used_ids).update(hits=F("hits") + 1)
    return found


# Строк в одной вставке: каждая порция — отдельный INSERT … ON CONFLICT DO NOTHING
# в своей транзакции. Одна вставка на ~300 тыс. абзацев уронила Postgres по OOM
# (лимит контейнера 640 МБ, 20.10.2026).
REMEMBER_BATCH_SIZE = 500


def remember(
    namespace: str,
    translations: Translations,
    *,
    log: AIProcessingLog | None = None,
    batch_size: int = REMEMBER_BATCH_SIZE,
) -> int:
    """Сохранить новые переводы порциями; существующие строки не трогаются. → сколько создано.

    Повторный вызов с теми же текстами ничего не меняет (идемпотентно), поэтому
    прерванную запись можно просто повторить.
    """
    created = 0
    chunk: dict[str, AITranslationMemory] = {}
    for text, values in translations.items():
        normalized = normalize_source_text(text)
        ru, en = str((values or {}).get("ru") or "").strip(), str((values or {}).get("en") or "").strip()
        if not (normalized and ru and en):
            continue
        key = source_hash(normalized)
        chunk[key] = AITranslationMemory(
            namespace=namespace,
            source_hash=key,
            source_text=normalized,
            ru_text=ru,
            en_text=en,
            source_log=log,
        )
        if len(chunk) >= batch_size:
            created += _insert_chunk(namespace, chunk)
            chunk = {}
    if chunk:
        created += _insert_chunk(namespace, chunk)
    return created


def _insert_chunk(namespace: str, chunk: dict[str, AITranslationMemory]) -> int:
    with transaction.atomic():
        existing = set(
            AITranslationMemory.objects.filter(namespace=namespace, source_hash__in=list(chunk))
            .values_list("source_hash", flat=True)
        )
        AITranslationMemory.objects.bulk_create(chunk.values(), ignore_conflicts=True)
    return len(chunk) - len(existing)


def get_or_translate(
    namespace: str,
    texts: Iterable[Any],
    translator: Translator | None,
    *,
    log: AIProcessingLog | None = None,
    log_statuses: Iterable[str] | None = None,
) -> tuple[Translations, dict[str, Any]]:
    """Из памяти — готовые, недостающие — одним вызовом ``translator``.

    ``translator(list[str]) -> ({text: {"ru", "en"}}, usage)``; в память
    попадает только то, что он вернул (непрошедшие проверки — не возвращать).
    """
    by_hash = _unique_texts(texts)
    usage: dict[str, Any] = {"tokens": {}, "cost_usd": 0.0, "processing_time_ms": 0}
    found = lookup(namespace, by_hash.values(), log_statuses=log_statuses)
    missing = [text for text in by_hash.values() if text not in found]
    if missing and translator is not None:
        translated, usage = translator(missing)
        wanted = set(missing)
        fresh = {
            normalize_source_text(text): values
            for text, values in (translated or {}).items()
            if normalize_source_text(text) in wanted
        }
        remember(namespace, fresh, log=log)
        found.update({text: values for text, values in fresh.items() if values.get("ru") and values.get("en")})
    return found, usage
