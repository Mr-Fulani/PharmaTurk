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
        # Проверяем, нужно ли обрабатывать (можно добавить доп. логику или флаги)
        # Например, если товар создан парсером
        logger.info(f"New product created: {instance.id}. Triggering AI processing.")
        
        # Запускаем задачу асинхронно
        process_product_ai_task.delay(
            product_id=instance.id,
            processing_type='full',
            auto_apply=False  # По умолчанию не применяем сразу, нужна модерация или ручное подтверждение
        )
