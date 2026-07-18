"""Единая проверка качества результата AI и создание задач модерации."""

import re
from typing import List

from apps.ai.models import AIProcessingLog, AIModerationQueue
from apps.ai.services.semantic_validator import SemanticValidator


def get_moderation_reasons(log: AIProcessingLog) -> List[str]:
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

    reasons.extend(SemanticValidator().validate_log(log).reasons)

    return list(dict.fromkeys(reasons))


def check_needs_moderation(log: AIProcessingLog) -> bool:
    """Совместимый булев интерфейс для существующих вызовов."""
    return bool(get_moderation_reasons(log))


def create_moderation_task(log: AIProcessingLog) -> None:
    """Создать запись в очереди модерации для лога."""
    if getattr(log, "moderation_queue", None):
        return

    reasons = get_moderation_reasons(log)
    reason = reasons[0] if reasons else "manual_review"
    priority = 2 if reason in {"low_confidence", "title_category_mismatch", "untranslated_attribute"} else 3
    AIModerationQueue.objects.get_or_create(
        log_entry=log,
        defaults={"priority": priority, "reason": reason},
    )
