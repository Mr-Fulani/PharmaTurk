from celery import shared_task, group
from django.apps import apps
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
    force: bool = False,
):
    """Обработка одного товара AI (описание, категория, анализ изображений)."""
    try:
        if options is None:
            options = {}
        if force:
            options["force"] = True

        logger.info(
            "Starting AI processing for product %s, type=%s, force=%s",
            product_id,
            processing_type,
            force,
        )
        generator = ContentGenerator()
        log_entry = generator.process_product(
            product_id=product_id,
            processing_type=processing_type,
            auto_apply=auto_apply,
            options=options,
        )

        if log_entry.status in [AIProcessingStatus.COMPLETED, AIProcessingStatus.APPROVED, AIProcessingStatus.MODERATION] and not force:
             # Если статус уже финальный и мы не форсировали, значит лог был возвращен существующий
             logger.info(
                "AI processing skipped for product %s (already exists). Log ID: %s",
                product_id,
                log_entry.id,
            )
        else:
            logger.info(
                "AI processing completed for product %s. Log ID: %s",
                product_id,
                log_entry.id,
            )
        if processing_type in ("full", "description_only"):
            prepare_variant_ai_candidates_task.delay(product_id=product_id, force=force)
        from apps.recommendations.tasks import index_product_vectors
        index_product_vectors.apply_async(args=[[product_id]], countdown=60)
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
def prepare_variant_ai_candidates_task(product_id: int, force: bool = False):
    """Собирает очередь вариантов, для которых потенциально нужна отдельная AI-обработка."""
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        logger.warning("prepare_variant_ai_candidates_task: product %s not found", product_id)
        return {"status": "missing", "product_id": product_id}

    generator = ContentGenerator()
    variant_context = generator._collect_variant_context(product) or {}

    queue_payload = {
        "status": "not_needed",
        "updated_at": timezone.now().isoformat(),
        "variant_axis": variant_context.get("variant_axis"),
        "variant_count": variant_context.get("variant_count", 0),
        "candidate_count": 0,
        "candidates": [],
    }

    if variant_context.get("needs_separate_variant_copy"):
        queue_payload.update(
            {
                "status": "pending_review",
                "candidate_count": variant_context.get("variant_copy_candidate_count", 0),
                "candidates": variant_context.get("variant_copy_candidates", []),
                "strategy": variant_context.get("content_strategy"),
            }
        )

    external_data = dict(product.external_data) if isinstance(product.external_data, dict) else {}
    previous_queue = external_data.get("ai_variant_processing_queue")
    if not force and previous_queue == queue_payload:
        return {
            "status": "unchanged",
            "product_id": product_id,
            "candidate_count": queue_payload["candidate_count"],
        }

    external_data["ai_variant_processing_queue"] = queue_payload
    product.external_data = external_data
    product.save(update_fields=["external_data"])

    logger.info(
        "Prepared variant AI queue for product %s: %s candidates",
        product_id,
        queue_payload["candidate_count"],
    )
    return {
        "status": "success",
        "product_id": product_id,
        "candidate_count": queue_payload["candidate_count"],
    }


@shared_task(bind=True, max_retries=3)
def process_variant_ai_task(self, model_label: str, variant_id: int, force: bool = False):
    """Ручная AI-обработка варианта товара. Результат сохраняется только в external_data варианта."""
    try:
        VariantModel = apps.get_model(model_label)
        variant = VariantModel.objects.select_related("product").get(pk=variant_id)
        generator = ContentGenerator()
        payload = generator.process_variant_content(variant, force=force)
        return {
            "status": payload.get("status", "success"),
            "model_label": model_label,
            "variant_id": variant_id,
        }
    except Exception as e:
        logger.exception("Error in variant AI task for %s:%s: %s", model_label, variant_id, e)
        try:
            VariantModel = apps.get_model(model_label)
            variant = VariantModel.objects.get(pk=variant_id)
            external_data = dict(variant.external_data) if isinstance(variant.external_data, dict) else {}
            external_data["ai_variant_content"] = {
                "status": "failed",
                "updated_at": timezone.now().isoformat(),
                "error_message": str(e),
            }
            variant.external_data = external_data
            variant.save(update_fields=["external_data"])
        except Exception:
            logger.exception("Failed to persist variant AI error for %s:%s", model_label, variant_id)
        return {
            "status": "error",
            "error": str(e),
            "model_label": model_label,
            "variant_id": variant_id,
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
