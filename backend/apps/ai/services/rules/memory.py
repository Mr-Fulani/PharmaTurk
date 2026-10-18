"""Память переводов описаний товаров поверх общей ``translation_memory``."""

from __future__ import annotations

from typing import Any

from apps.ai.models import AIProcessingLog, AIProcessingStatus, AITranslationMemory
from apps.ai.services import translation_memory

NAMESPACE_PREFIX = "product_description"
# Переиспользуем только принятые результаты: модерация/ошибка/отклонение — нет.
REUSABLE_LOG_STATUSES = (AIProcessingStatus.COMPLETED, AIProcessingStatus.APPROVED)


def namespace_for(category_id: Any) -> str:
    """Категория входит в namespace: от неё зависит перевод многозначных слов."""
    return f"{NAMESPACE_PREFIX}:{category_id or 0}"


def lookup(namespace: str, source_text: str) -> dict[str, Any] | None:
    found = translation_memory.lookup(namespace, [source_text], log_statuses=REUSABLE_LOG_STATUSES)
    texts = next(iter(found.values()), None)
    if not texts:
        return None
    entry = AITranslationMemory.objects.only("pk", "source_log_id").get(
        namespace=namespace, source_hash=translation_memory.source_hash(source_text)
    )
    return {**texts, "memory_id": entry.pk, "source_log_id": entry.source_log_id}


def remember(namespace: str, source_text: str, ru: str, en: str, log: AIProcessingLog | None) -> None:
    if translation_memory.remember(namespace, {source_text: {"ru": ru, "en": en}}, log=log):
        return
    # Старая автоматическая запись, чей лог не принят, уступает свежему переводу.
    stale = AITranslationMemory.objects.filter(
        namespace=namespace,
        source_hash=translation_memory.source_hash(source_text),
        source_log__isnull=False,
    ).exclude(source_log__status__in=REUSABLE_LOG_STATUSES)
    stale.update(ru_text=ru, en_text=en, source_log=log)
