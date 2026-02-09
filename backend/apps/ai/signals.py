from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.catalog.models import Product
from .tasks import process_product_ai_task
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Product)
def trigger_ai_processing(sender, instance, created, **kwargs):
    """
    Автоматический запуск AI обработки при создании товара.
    """
    if created:
        external = instance.external_data or {}
        if external.get("source"):
            logger.info(
                f"AI обработка пропущена для товара {instance.id} (источник: {external.get('source')})"
            )
            return
        logger.info(f"New product created: {instance.id}. Triggering AI processing.")

        process_product_ai_task.delay(
            product_id=instance.id,
            processing_type="full",
            auto_apply=False,
        )
