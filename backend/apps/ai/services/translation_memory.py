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


def remember(
    namespace: str,
    translations: Translations,
    *,
    log: AIProcessingLog | None = None,
) -> int:
    """Сохранить новые переводы; существующие строки не трогаются. → сколько создано."""
    rows = []
    for text, values in translations.items():
        normalized = normalize_source_text(text)
        ru, en = str((values or {}).get("ru") or "").strip(), str((values or {}).get("en") or "").strip()
        if normalized and ru and en:
            rows.append(
                AITranslationMemory(
                    namespace=namespace,
                    source_hash=source_hash(normalized),
                    source_text=normalized,
                    ru_text=ru,
                    en_text=en,
                    source_log=log,
                )
            )
    if not rows:
        return 0
    before = AITranslationMemory.objects.filter(namespace=namespace).count()
    AITranslationMemory.objects.bulk_create(rows, ignore_conflicts=True)
    return AITranslationMemory.objects.filter(namespace=namespace).count() - before


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
