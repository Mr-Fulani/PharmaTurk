"""Память переводов описаний: одинаковый текст источника → один вызов LLM."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F

from apps.ai.models import AIProcessingLog, AIProcessingStatus, AITranslationMemory

NAMESPACE = "product_description"
# Переиспользуем только принятые результаты: модерация/ошибка/отклонение — нет.
REUSABLE_LOG_STATUSES = (AIProcessingStatus.COMPLETED, AIProcessingStatus.APPROVED)


def source_key(product_type: str, category_id: Any, source_text: str) -> str:
    """Категория входит в ключ: от неё зависит перевод многозначных слов."""
    normalized = re.sub(r"\s+", " ", str(source_text or "")).strip().casefold()
    raw = f"{product_type}|{category_id or ''}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _log_descriptions(log: AIProcessingLog) -> dict[str, str]:
    attrs = log.extracted_attributes if isinstance(log.extracted_attributes, dict) else {}
    seo = attrs.get("seo_translations") if isinstance(attrs.get("seo_translations"), dict) else {}
    ru = str((seo.get("ru") or {}).get("generated_description") or log.generated_description or "").strip()
    en = str((seo.get("en") or {}).get("generated_description") or "").strip()
    return {"ru": ru, "en": en}


def lookup(key: str) -> dict[str, Any] | None:
    entry = (
        AITranslationMemory.objects.filter(namespace=NAMESPACE, source_hash=key)
        .select_related("source_log")
        .first()
    )
    if entry is None:
        return None
    texts = {"ru": entry.ru_text, "en": entry.en_text}
    if entry.source_log is not None:
        if entry.source_log.status not in REUSABLE_LOG_STATUSES:
            return None
        texts = _log_descriptions(entry.source_log)
    if not texts["ru"] or not texts["en"]:
        return None
    AITranslationMemory.objects.filter(pk=entry.pk).update(hits=F("hits") + 1)
    return {**texts, "memory_id": entry.pk, "source_log_id": entry.source_log_id}


def remember(key: str, ru: str, en: str, log: AIProcessingLog | None) -> None:
    if not (ru and en):
        return
    values = {"ru_text": ru, "en_text": en, "source_log": log}
    try:
        with transaction.atomic():
            entry, created = AITranslationMemory.objects.get_or_create(
                namespace=NAMESPACE, source_hash=key, defaults=values
            )
    except IntegrityError:  # параллельная задача с тем же текстом успела раньше
        return
    if created:
        return
    # Старая запись, чей лог не принят, уступает свежему переводу.
    source = entry.source_log
    if source is None or source.status not in REUSABLE_LOG_STATUSES:
        AITranslationMemory.objects.filter(pk=entry.pk).update(**values)
