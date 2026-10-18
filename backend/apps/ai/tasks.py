from celery import shared_task
from django.apps import apps
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Q

import logging
from datetime import timedelta
from typing import List

import openai
import requests

from apps.catalog.models import Product
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.models import AIProcessingLog, AIProcessingStatus

logger = logging.getLogger(__name__)

# PENDING/PROCESSING-лог без движения дольше этого срока считается зависшим
# (воркер упал, задача потерялась) и не блокирует повторную постановку.
STALE_AI_LOG_AFTER = timedelta(minutes=60)
ACTIVE_AI_LOG_STATUSES = (AIProcessingStatus.PENDING, AIProcessingStatus.PROCESSING)


def _is_retryable_ai_error(exc: Exception) -> bool:
    """Повторяем только временные сбои: сеть, таймаут, 429 и 5xx."""
    if "insufficient_quota" in str(exc).lower():
        return False
    if isinstance(exc, openai.APIConnectionError):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    if isinstance(exc, requests.HTTPError):
        status = getattr(exc.response, "status_code", None)
        return status is not None and (status == 429 or status >= 500)
    return isinstance(exc, (requests.ConnectionError, requests.Timeout, ConnectionError, TimeoutError))


def _resolve_processing_type(processing_type: str, options: dict | None) -> str:
    if not options:
        return processing_type
    if options.get("generate_description", True):
        return "full" if options.get("categorize", True) else "description_only"
    if options.get("categorize", True):
        return "categorization_only"
    if options.get("analyze_images", True):
        return "image_analysis"
    return processing_type


@transaction.atomic
def enqueue_product_ai_task(
    *,
    product_id: int,
    processing_type: str = "full",
    auto_apply: bool = False,
    options: dict | None = None,
    force: bool = False,
    index_vectors: bool = True,
):
    """Создать видимый pending-лог и после commit поставить задачу в очередь.

    Возвращает ``(log, task_id, submitted)``. Повторное нажатие не плодит
    pending-задачи и не запускает уже успешно обработанный товар без ``force``.
    ``index_vectors=False`` отключает переиндексацию рекомендаций после
    обработки (на время массового прогона).
    """
    import uuid

    resolved_type = _resolve_processing_type(processing_type, options)
    # Блокировка строки товара делает проверку/создание pending-лога атомарной
    # при двойном клике или параллельных admin/API запросах.
    product = Product.objects.select_for_update().get(pk=product_id)
    AIProcessingLog.objects.filter(
        product=product,
        processing_type=resolved_type,
        status__in=ACTIVE_AI_LOG_STATUSES,
        updated_at__lt=timezone.now() - STALE_AI_LOG_AFTER,
    ).update(
        status=AIProcessingStatus.FAILED,
        error_message="Задача зависла: лог не обновлялся дольше "
        f"{int(STALE_AI_LOG_AFTER.total_seconds() // 60)} мин",
        completed_at=timezone.now(),
    )
    reusable_statuses = list(ACTIVE_AI_LOG_STATUSES)
    if not force:
        reusable_statuses.extend(
            [
                AIProcessingStatus.COMPLETED,
                AIProcessingStatus.APPROVED,
                AIProcessingStatus.MODERATION,
            ]
        )
    existing = AIProcessingLog.objects.filter(
        product=product,
        processing_type=resolved_type,
        status__in=reusable_statuses,
    ).order_by("-created_at").first()
    if existing:
        task_id = str((existing.input_data or {}).get("celery_task_id") or "")
        return existing, task_id, False

    task_id = str(uuid.uuid4())
    log_entry = AIProcessingLog.objects.create(
        product=product,
        processing_type=resolved_type,
        status=AIProcessingStatus.PENDING,
        input_data={
            "celery_task_id": task_id,
            "queued_at": timezone.now().isoformat(),
            "auto_apply": bool(auto_apply),
        },
    )

    def submit():
        try:
            process_product_ai_task.apply_async(
                kwargs={
                    "product_id": product_id,
                    "processing_type": resolved_type,
                    "auto_apply": auto_apply,
                    "options": options,
                    "force": force,
                    "log_entry_id": log_entry.id,
                    "index_vectors": index_vectors,
                },
                task_id=task_id,
                priority=9,
            )
        except Exception as exc:
            AIProcessingLog.objects.filter(pk=log_entry.id).update(
                status=AIProcessingStatus.FAILED,
                error_message=f"Не удалось поставить задачу в Celery: {exc}",
                completed_at=timezone.now(),
            )
            raise

    transaction.on_commit(submit)
    return log_entry, task_id, True


# acks_late + reject_on_worker_lost: при деплое/падении celery_ai задача
# возвращается в очередь и продолжает тот же PROCESSING-лог.
@shared_task(bind=True, max_retries=3, acks_late=True, reject_on_worker_lost=True)
def process_product_ai_task(
    self,
    product_id: int,
    processing_type: str = "full",
    auto_apply: bool = False,
    options: dict = None,
    force: bool = False,
    log_entry_id: int | None = None,
    index_vectors: bool = True,
):
    """Обработка одного товара AI (описание, категория, анализ изображений)."""
    if log_entry_id is not None and not AIProcessingLog.objects.filter(
        pk=log_entry_id, status__in=ACTIVE_AI_LOG_STATUSES
    ).exists():
        # Лог признан зависшим и заменён новым (или уже завершён) — не дублируем.
        logger.info("AI task skipped: log %s is no longer active", log_entry_id)
        return {"status": "skipped", "log_id": log_entry_id, "product_id": product_id}
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
            log_entry_id=log_entry_id,
        )
        try:
            product = Product.objects.get(id=product_id)
            generator.sync_variant_titles_from_parent(product, log_entry=log_entry)
        except Exception:
            logger.exception("Variant title sync failed for product %s", product_id)

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
        if index_vectors:
            from apps.recommendations.tasks import index_product_vectors
            index_product_vectors.apply_async(args=[[product_id]], countdown=60)
        return {
            "status": "success",
            "log_id": log_entry.id,
            "product_id": product_id,
        }
    except Exception as e:
        logger.exception("Error in AI task for product %s: %s", product_id, e)
        if _is_retryable_ai_error(e) and self.request.retries < self.max_retries:
            # Повтор продолжает тот же лог: возвращаем его в PENDING, чтобы
            # process_product подхватил его, а не создал новый.
            reopened = 1
            if log_entry_id:
                reopened = AIProcessingLog.objects.filter(
                    pk=log_entry_id,
                    status__in=[*ACTIVE_AI_LOG_STATUSES, AIProcessingStatus.FAILED],
                ).update(
                    status=AIProcessingStatus.PENDING,
                    error_message=f"Повтор {self.request.retries + 1}/{self.max_retries}: {e}",
                    completed_at=None,
                    updated_at=timezone.now(),
                )
            if reopened:
                raise self.retry(exc=e, countdown=min(60 * (2 ** self.request.retries), 300))
        if log_entry_id:
            AIProcessingLog.objects.filter(
                pk=log_entry_id,
                status__in=ACTIVE_AI_LOG_STATUSES,
            ).update(
                status=AIProcessingStatus.FAILED,
                error_message=str(e),
                completed_at=timezone.now(),
            )
        raise


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


@shared_task(bind=True)
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
    """Пакетная постановка с видимым pending-логом для каждого товара."""
    if not product_ids:
        return {"task_id": None, "total": 0, "submitted": False}
    submitted = 0
    task_ids = []
    for product_id in product_ids:
        _, task_id, was_submitted = enqueue_product_ai_task(
            product_id=product_id,
            processing_type=processing_type,
            auto_apply=auto_apply,
        )
        if was_submitted:
            submitted += 1
            task_ids.append(task_id)
    return {
        "task_id": task_ids[0] if task_ids else None,
        "total": len(product_ids),
        "submitted": submitted,
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
        enqueue_product_ai_task(
            product_id=log.product_id,
            processing_type=log.processing_type,
            auto_apply=False,
            force=True,
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
