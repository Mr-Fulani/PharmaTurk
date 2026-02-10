from celery import shared_task, group
from django.utils import timezone
from django.db.models import Count, Q

import logging
from typing import List

from apps.catalog.models import Product
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.models import AIProcessingLog, AIProcessingStatus

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_product_ai_task(
    self,
    product_id: int,
    processing_type: str = "full",
    auto_apply: bool = False,
    options: dict = None,
):
    """Обработка одного товара AI (описание, категория, анализ изображений)."""
    try:
        logger.info(
            "Starting AI processing for product %s, type=%s",
            product_id,
            processing_type,
        )
        generator = ContentGenerator()
        log_entry = generator.process_product(
            product_id=product_id,
            processing_type=processing_type,
            auto_apply=auto_apply,
            options=options,
        )
        logger.info(
            "AI processing completed for product %s. Log ID: %s",
            product_id,
            log_entry.id,
        )
        return {
            "status": "success",
            "log_id": log_entry.id,
            "product_id": product_id,
        }
    except Exception as e:
        logger.exception("Error in AI task for product %s: %s", product_id, e)
        return {
            "status": "error",
            "error": str(e),
            "product_id": product_id,
        }


@shared_task
def batch_process_products(
    product_ids: List[int],
    processing_type: str = "full",
    auto_apply: bool = False,
):
    """Пакетная обработка списка товаров (группа задач)."""
    if not product_ids:
        return {"task_id": None, "total": 0, "submitted": False}
    job = group(
        process_product_ai_task.s(pid, processing_type, auto_apply)
        for pid in product_ids
    )
    result = job.apply_async()
    return {
        "task_id": result.id,
        "total": len(product_ids),
        "submitted": True,
    }


@shared_task
def process_uncategorized(limit: int = 100):
    """По расписанию: обработать товары без категории (только категоризация)."""
    products = (
        Product.objects.filter(category__isnull=True)
        .annotate(log_count=Count("ai_logs"))
        .filter(log_count=0)[:limit]
    )
    product_ids = list(products.values_list("id", flat=True))
    if not product_ids:
        return {"processed": 0}
    batch_process_products.delay(
        product_ids,
        processing_type="categorization_only",
        auto_apply=False,
    )
    return {"processed": len(product_ids), "product_ids": product_ids[:10]}


@shared_task
def process_without_description(limit: int = 100):
    """По расписанию: обработать товары без описания (категория должна быть)."""
    products = (
        Product.objects.filter(category__isnull=False)
        .filter(Q(description__isnull=True) | Q(description=""))
        .annotate(log_count=Count("ai_logs"))
        .filter(log_count=0)[:limit]
    )
    product_ids = list(products.values_list("id", flat=True))
    if not product_ids:
        return {"processed": 0}
    batch_process_products.delay(
        product_ids,
        processing_type="description_only",
        auto_apply=False,
    )
    return {"processed": len(product_ids), "product_ids": product_ids[:10]}


@shared_task
def retry_failed_processing(limit: int = 50):
    """Повторная обработка неудачных попыток за последние 7 дней."""
    since = timezone.now() - timezone.timedelta(days=7)
    failed_logs = AIProcessingLog.objects.filter(
        status=AIProcessingStatus.FAILED,
        created_at__gte=since,
    )[:limit]
    retried = 0
    for log in failed_logs:
        process_product_ai_task.delay(
            log.product_id,
            processing_type=log.processing_type,
            auto_apply=False,
        )
        retried += 1
    return {"retried": retried}


@shared_task
def cleanup_old_ai_logs(days: int = 90):
    """Очистка старых логов AI (GDPR/хранение)."""
    cutoff = timezone.now() - timezone.timedelta(days=days)
    deleted, _ = AIProcessingLog.objects.filter(
        created_at__lt=cutoff,
        status__in=(AIProcessingStatus.COMPLETED, AIProcessingStatus.APPROVED),
    ).delete()
    return {"deleted_logs": deleted}
