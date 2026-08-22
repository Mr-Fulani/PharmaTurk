"""Единая проверка качества результата AI и создание задач модерации."""

import re
from typing import List

from apps.ai.models import AIProcessingLog, AIModerationQueue
from apps.ai.services.semantic_validator import SemanticValidationReport, SemanticValidator


def get_moderation_reasons(
    log: AIProcessingLog,
    *,
    semantic_report: SemanticValidationReport | None = None,
) -> List[str]:
    """
    Определить, требуется ли ручная модерация результата.
    Критерии: низкая уверенность в категории, подозрительная цена,
    подозрительные слова в описании, слишком короткое описание.
    """
    reasons = []
    if log.category_confidence is not None and log.category_confidence < 0.75:
        reasons.append("low_confidence")

    # Подозрительно низкая цена (возможна ошибка парсера)
    input_data = log.input_data or {}
    if input_data.get("price"):
        try:
            price = float(input_data["price"])
            currency = str(input_data.get("currency") or "").upper()
            thresholds = {"RUB": 100, "TRY": 10, "USD": 1, "EUR": 1, "KZT": 500}
            threshold = thresholds.get(currency)
            if threshold is not None and price < threshold:
                reasons.append("suspicious_price")
        except (TypeError, ValueError):
            pass

    # Подозрительные слова в описании
    desc = (log.generated_description or "").lower()
    if re.search(r"\b(реплика|копия|fake|подделка|replica|copy)\b", desc, re.IGNORECASE):
        reasons.append("sensitive_content")

    # Слишком короткое описание
    if len(re.findall(r"\b\w+\b", log.generated_description or "", re.UNICODE)) < 20:
        reasons.append("short_description")

    semantic_report = semantic_report or SemanticValidator().validate_log(log)
    reasons.extend(semantic_report.reasons)

    return list(dict.fromkeys(reasons))


def check_needs_moderation(log: AIProcessingLog) -> bool:
    """Совместимый булев интерфейс для существующих вызовов."""
    return bool(get_moderation_reasons(log))


def create_moderation_task(
    log: AIProcessingLog,
    reasons: List[str] | None = None,
) -> None:
    """Создать или повторно открыть запись в очереди модерации для лога."""
    reasons = reasons if reasons is not None else get_moderation_reasons(log)
    reason = reasons[0] if reasons else "manual_review"
    priority = 2 if reason in {"low_confidence", "title_category_mismatch", "untranslated_attribute"} else 3
    task, created = AIModerationQueue.objects.get_or_create(
        log_entry=log,
        defaults={"priority": priority, "reason": reason},
    )
    if not created:
        update_fields = []
        if task.reason != reason:
            task.reason = reason
            update_fields.append("reason")
        if task.priority != priority:
            task.priority = priority
            update_fields.append("priority")
        if task.resolved_at is not None:
            task.resolved_at = None
            update_fields.append("resolved_at")
        if update_fields:
            task.save(update_fields=update_fields)
