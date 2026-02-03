"""Сигналы для удаления медиа-файлов отзывов из хранилища."""
import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Testimonial, TestimonialMedia

logger = logging.getLogger(__name__)


def _delete_file_from_storage(file_field):
    if file_field and hasattr(file_field, "name") and file_field.name:
        try:
            from django.core.files.storage import default_storage
            default_storage.delete(file_field.name)
        except Exception as e:
            logger.warning("Failed to delete file %s: %s", getattr(file_field, "name", ""), e)


@receiver(post_delete, sender=Testimonial)
def delete_testimonial_avatar(sender, instance, **kwargs):
    _delete_file_from_storage(instance.author_avatar)


@receiver(post_delete, sender=TestimonialMedia)
def delete_testimonial_media_files(sender, instance, **kwargs):
    _delete_file_from_storage(instance.image)
    _delete_file_from_storage(instance.video_file)
