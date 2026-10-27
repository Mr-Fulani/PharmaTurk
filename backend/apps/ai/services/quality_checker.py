"""Единая проверка качества результата AI и создание задач модерации."""

import json
import re
from typing import List

from django.utils import timezone

from apps.ai.models import AIProcessingLog, AIModerationQueue, AIProcessingStatus
from apps.ai.services.semantic_validator import SemanticValidationReport, SemanticValidator


# Вкладки ilacfiyati с текстом инструкции (без «equivalents», «sgk_equivalents», «ilac_bilgileri»).
_INSTRUCTION_TABS = (
    "summary", "indications", "before_use_warnings", "usage_instructions", "side_effects", "storage_conditions",
)
_MIXED_SCRIPT_WORD = re.compile(r"\b[^\W\d_]*(?:[A-Za-z][А-Яа-яЁё]|[А-Яа-яЁё][A-Za-z])[^\W\d_]*\b")
_META_DESCRIPTION = re.compile(
    r"исходн\w* данн|в данных|не указан|см\.\s*(?:данные|в инструкции|инструкцию)|подробн\w* сведения",
    re.IGNORECASE,
)


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

    # Испорченный символ «�» в ответе модели (пилот 27.10.2026: «MENOPUR 75 М�МЕ» применилось).
    if "\ufffd" in json.dumps(
        [getattr(log, field, None) for field in ("generated_title", "generated_description", "extracted_attributes")],
        ensure_ascii=False,
        default=str,
    ):
        reasons.append("garbled_text")
    # Слово из букв двух алфавитов: «Рufинамид» (очередь модерации 27.10.2026) — тот же сбой ответа.
    elif _MIXED_SCRIPT_WORD.search(log.generated_description or ""):
        reasons.append("garbled_text")

    # Подозрительные слова в описании
    desc = (log.generated_description or "").lower()
    if re.search(r"\b(реплика|копия|fake|подделка|replica|copy)\b", desc, re.IGNORECASE):
        reasons.append("sensitive_content")

    # Карточка лекарства намеренно краткая: клинические сведения хранятся в
    # отдельных полях, а не раздувают маркетинговое описание. Для остальных
    # категорий сохраняем прежний порог.
    product_type = getattr(getattr(log, "product", None), "product_type", None)
    minimum_description_words = 12 if product_type == "medicines" else 20
    # Описание-из-фактов (источник без текста) короткое намеренно: в нём
    # только подтверждённые атрибуты, «воду» дописывать нечем.
    raw_response = getattr(log, "raw_llm_response", None)
    rule_content = raw_response.get("rule_content") if isinstance(raw_response, dict) else None
    from_facts = isinstance(rule_content, dict) and rule_content.get("description_source") == "template"
    if isinstance(rule_content, dict):
        # Узкий запрос пересказывает источник без «воды»: короткий исходник даёт
        # короткое описание. Порог ловит только пустой/сломанный ответ.
        minimum_description_words = 10
    tabs = (input_data.get("attributes") or {}).get("source_tabs") if isinstance(input_data.get("attributes"), dict) else None
    tabs = tabs if isinstance(tabs, dict) else {}
    if product_type == "medicines" and not any(
        str((tabs.get(key).get("text") if isinstance(tabs.get(key), dict) else tabs.get(key)) or "").strip()
        for key in _INSTRUCTION_TABS
    ):
        # У источника нет инструкции: описание — из справочных фактов (форма, путь введения,
        # рецепт), 8–11 слов; так у 95 из 110 лекарств очереди 27.10.2026. Вкладки аналогов
        # и «İlaç bilgileri» — не инструкция (42 из 46 «коротких» в очереди 27.10.2026).
        minimum_description_words = 6
    if product_type == "medicines" and _META_DESCRIPTION.search(log.generated_description or ""):
        # «Лекарственная форма … в исходных данных не указаны», «см. в инструкции» — рассуждение
        # модели о данных вместо описания.
        reasons.append("description_meta_text")
    if not from_facts and (
        len(re.findall(r"\b\w+\b", log.generated_description or "", re.UNICODE))
        < minimum_description_words
    ):
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


def close_superseded_logs(log: AIProcessingLog) -> List[int]:
    """Закрыть более старые непроверенные логи товара, которые заменил ``log``.

    Иначе в модерации висят два результата одного товара, а применение
    старого перезаписало бы карточку устаревшим текстом. Полная обработка
    заменяет логи любого типа, частичная — только своего.
    """
    older = AIProcessingLog.objects.filter(
        product_id=log.product_id,
        pk__lt=log.pk,
        status__in=(AIProcessingStatus.COMPLETED, AIProcessingStatus.MODERATION),
    )
    if log.processing_type != "full":
        older = older.filter(processing_type=log.processing_type)
    closed_at = timezone.now()
    note = f"Закрыто автоматически: заменено более новой обработкой #{log.pk}."
    closed = []
    for old_log in older:
        old_log.status = AIProcessingStatus.REJECTED
        old_log.moderation_date = closed_at
        old_log.moderation_notes = "\n".join(filter(None, [old_log.moderation_notes, note]))
        old_log.save(update_fields=["status", "moderation_date", "moderation_notes", "updated_at"])
        closed.append(old_log.pk)
    if closed:
        AIModerationQueue.objects.filter(log_entry_id__in=closed, resolved_at__isnull=True).update(
            resolved_at=closed_at
        )
    return closed
