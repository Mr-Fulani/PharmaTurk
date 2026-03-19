"""Сигналы для удаления медиа-файлов пользователя из хранилища."""
import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import User

logger = logging.getLogger(__name__)


def _delete_file_from_storage(file_field):
    if file_field and hasattr(file_field, "name") and file_field.name:
        try:
            from django.core.files.storage import default_storage
            default_storage.delete(file_field.name)
        except Exception as e:
            logger.warning("Failed to delete file %s: %s", getattr(file_field, "name", ""), e)


@receiver(post_delete, sender=User)
def delete_user_avatar(sender, instance, **kwargs):
    _delete_file_from_storage(instance.avatar)
