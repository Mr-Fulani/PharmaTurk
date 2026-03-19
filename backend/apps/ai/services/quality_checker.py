"""Проверка качества результата AI и создание задач модерации."""

from apps.ai.models import AIProcessingLog, AIModerationQueue


def check_needs_moderation(log: AIProcessingLog) -> bool:
    """
    Определить, требуется ли ручная модерация результата.
    Критерии: низкая уверенность в категории, подозрительная цена,
    подозрительные слова в описании, слишком короткое описание.
    """
    # Низкая уверенность в категории
    if log.category_confidence is not None and log.category_confidence < 0.75:
        return True

    # Подозрительно низкая цена (возможна ошибка парсера)
    input_data = log.input_data or {}
    if input_data.get("price"):
        try:
            price = float(input_data["price"])
            if price < 100:
                return True
        except (TypeError, ValueError):
            pass

    # Подозрительные слова в описании
    suspicious_words = [
        "реплика", "копия", "fake", "подделка", "replica", "copy"
    ]
    desc = (log.generated_description or "").lower()
    if any(word in desc for word in suspicious_words):
        return True

    # Слишком короткое описание
    if len(log.generated_description or "") < 100:
        return True

    return False


def create_moderation_task(log: AIProcessingLog) -> None:
    """Создать запись в очереди модерации для лога."""
    if getattr(log, "moderation_queue", None):
        return

    reason = (
        "low_confidence"
        if (log.category_confidence or 1) < 0.75
        else "manual_review"
    )
    priority = 2 if reason == "low_confidence" else 3
    AIModerationQueue.objects.get_or_create(
        log_entry=log,
        defaults={"priority": priority, "reason": reason},
    )
