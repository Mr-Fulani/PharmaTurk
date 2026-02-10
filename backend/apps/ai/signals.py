from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.catalog.models import Product
from .tasks import process_product_ai_task
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Product)
def trigger_ai_processing(sender, instance, created, **kwargs):
    """
    Автоматический запуск AI обработки при создании товара только если товар
    от парсера/скрапера (по ТЗ: source == 'parser' или есть supplier / source в external_data).
    """
    if not created:
        return
    external = instance.external_data or {}
    is_from_parser = (
        external.get("source") == "parser"
        or bool(external.get("source"))  # любой источник = парсер/скрапер
        or bool(external.get("scraped_sources"))
        or getattr(instance, "supplier", None) is not None
    )
    if not is_from_parser:
        logger.debug(
            "AI обработка пропущена для товара %s (не от парсера)",
            instance.id,
        )
        return
    # Не ставим задачу, если описание и SEO уже заполнены (например, скрапнуты парсером)
    desc = (instance.description or "").strip()
    meta_title = (instance.meta_title or "").strip()
    meta_desc = (instance.meta_description or "").strip()
    meta_kw = (instance.meta_keywords or "").strip()
    if desc and meta_title and meta_desc and meta_kw:
        logger.debug(
            "AI обработка пропущена для товара %s (описание и SEO уже заполнены)",
            instance.id,
        )
        return
    logger.info("New product from parser: %s. Triggering AI processing.", instance.id)
    process_product_ai_task.delay(
        product_id=instance.id,
        processing_type="full",
        auto_apply=False,
    )
