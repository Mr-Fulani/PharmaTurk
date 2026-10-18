"""Правило владения текстами товара между парсером и AI.

Если к товару применён AI-результат (или его утвердил модератор), тексты
карточки — название, описание, переводы, SEO — принадлежат AI/менеджеру.
Повторный парсинг их не перезаписывает: свежий исходный текст сохраняется в
external_data["source_description"], а его изменение помечается
external_data["ai_source_changed_at"] как сигнал к переобработке.
"""

import hashlib

from apps.ai.models import AIApplicationStatus, AIProcessingLog, AIProcessingStatus

SOURCE_DESCRIPTION_KEY = "source_description"
SOURCE_DESCRIPTION_HASH_KEY = "source_description_sha256"
SOURCE_CHANGED_KEY = "ai_source_changed_at"


def has_applied_ai_content(product) -> bool:
    if not getattr(product, "pk", None):
        return False
    return AIProcessingLog.objects.filter(product_id=product.pk).filter(
        application_status__in=[AIApplicationStatus.APPLIED, AIApplicationStatus.PARTIAL]
    ).exists() or AIProcessingLog.objects.filter(
        product_id=product.pk, status=AIProcessingStatus.APPROVED
    ).exists()


def remember_source_description(
    external_data: dict,
    text: str,
    *,
    current_description: str,
    ai_owned: bool,
    now_iso: str,
) -> bool:
    """Запоминает исходный текст; для AI-товара помечает смену исходника.

    Полный текст хранится, только если он отличается от описания карточки
    (иначе он и так в description) — чтобы не дублировать тексты в БД.
    Возвращает True, если external_data изменился.
    """
    text = (text or "").strip()
    if not text:
        return False
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    previous = external_data.get(SOURCE_DESCRIPTION_HASH_KEY)
    keep_text = text != (current_description or "").strip()
    if previous == digest and keep_text == (SOURCE_DESCRIPTION_KEY in external_data):
        return False
    if keep_text:
        external_data[SOURCE_DESCRIPTION_KEY] = text
    else:
        external_data.pop(SOURCE_DESCRIPTION_KEY, None)
    external_data[SOURCE_DESCRIPTION_HASH_KEY] = digest
    if previous == digest:
        return True
    if ai_owned and previous:
        external_data[SOURCE_CHANGED_KEY] = now_iso
    return True
