import logging

logger = logging.getLogger(__name__)

# AI обработка запускается ТОЛЬКО вручную через кнопки в админке («Полная AI обработка»
# и «Полная AI обработка + авто-применение»). Автоматического сигнала нет, чтобы избежать
# неконтролируемых трат токенов при каждом сохранении товара.


from django.db.models.signals import post_save  # noqa: E402
from django.dispatch import receiver  # noqa: E402

from apps.ai.models import AITranslationMemory  # noqa: E402


@receiver(post_save, sender=AITranslationMemory, dispatch_uid="ai_propagate_medicine_inn")
def propagate_medicine_inn_edit(sender, instance, created, **kwargs):
    """Правка МНН в памяти переводов сразу применяется ко всем лекарствам с этим веществом."""
    from apps.ai.services.medicine_memory import INN_NAMESPACE, propagate_inn_translations

    if instance.namespace != INN_NAMESPACE or not (instance.ru_text and instance.en_text):
        return
    updated = propagate_inn_translations({instance.source_text})
    logger.info("INN %r propagated to %s medicine translations", instance.source_text, updated)
