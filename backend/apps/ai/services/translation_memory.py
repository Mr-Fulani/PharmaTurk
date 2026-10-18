"""Память переводов фрагментов (МНН, абзацы инструкций): батч-поиск и запись.

Ключ — sha256 текста после схлопывания пробелов. Запись с ручной правкой
(is_manual) автоматический перевод не перезаписывает.
"""

from __future__ import annotations

import hashlib
import re

from django.db.models import F

from apps.ai.models import AITranslationMemory


def normalize_source(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def source_hash(text: str) -> str:
    return hashlib.sha256(normalize_source(text).encode("utf-8")).hexdigest()


def lookup(namespace: str, texts: list[str], *, count_hits: bool = True) -> dict[str, dict[str, str]]:
    """{текст: {"ru", "en"}} для найденных в памяти; счётчик hits растёт."""
    hashes: dict[str, list[str]] = {}
    for text in texts:
        hashes.setdefault(source_hash(text), []).append(text)
    if not hashes:
        return {}
    entries = list(
        AITranslationMemory.objects.filter(namespace=namespace, source_hash__in=list(hashes))
        .exclude(ru_text="")
        .exclude(en_text="")
        .values("pk", "source_hash", "ru_text", "en_text")
    )
    if entries and count_hits:
        AITranslationMemory.objects.filter(pk__in=[e["pk"] for e in entries]).update(hits=F("hits") + 1)
    found = {}
    for entry in entries:
        for text in hashes[entry["source_hash"]]:
            found[text] = {"ru": entry["ru_text"], "en": entry["en_text"]}
    return found


def remember(namespace: str, translations: dict[str, dict[str, str]]) -> None:
    """Сохранить проверенные переводы; существующие записи не меняются."""
    rows = {}
    for text, value in translations.items():
        ru = str(value.get("ru") or "").strip()
        en = str(value.get("en") or "").strip()
        if ru and en:
            rows[source_hash(text)] = AITranslationMemory(
                namespace=namespace,
                source_hash=source_hash(text),
                source_text=normalize_source(text),
                ru_text=ru,
                en_text=en,
            )
    if rows:
        AITranslationMemory.objects.bulk_create(rows.values(), ignore_conflicts=True)
