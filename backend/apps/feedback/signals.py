"""Сигналы для удаления медиа-файлов отзывов из хранилища и авто-скачивания из URL."""
import logging

from django.db.models.signals import post_delete, pre_save
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


def _is_internal_url(url: str) -> bool:
    """Проверить что URL уже из нашего CDN/R2 (не нужно скачивать)."""
    if not url:
        return False
    try:
        from django.conf import settings
        r2_public = (getattr(settings, "R2_CONFIG", {}).get("public_url", "") or "").rstrip("/")
        if r2_public and url.startswith(r2_public):
            return True
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.path.startswith("/media/") or parsed.path.startswith("/testimonials/")
    except Exception:
        return False


def _download_and_save(instance, url: str, file_attr: str, label: str):
    """Скачать файл по URL и сохранить в file_attr инстанса (без вызова .save())."""
    try:
        import requests
        import os
        import uuid
        from urllib.parse import urlparse
        from django.core.files.base import ContentFile

        resp = requests.get(url, stream=True, timeout=10)
        if resp.status_code == 200:
            ext = os.path.splitext(urlparse(url).path)[1] or ".jpg"
            filename = f"{uuid.uuid4().hex[:12]}{ext}"
            setattr(instance, file_attr, ContentFile(resp.content, name=filename))
            logger.info("%s: скачано %s → %s", label, url, filename)
    except Exception as e:
        logger.warning("%s: ошибка скачивания %s — %s", label, url, e)


# ── Testimonial: аватар автора ────────────────────────────────────────────────

@receiver(pre_save, sender=Testimonial)
def auto_download_testimonial_avatar(sender, instance, **kwargs):
    """Авто-скачивание аватара автора отзыва из внешнего URL."""
    # У модели нет url-поля для аватара — аватар загружается только через файл.
    # Оставляем hook на случай если в будущем добавят avatar_url.
    pass


@receiver(post_delete, sender=Testimonial)
def delete_testimonial_avatar(sender, instance, **kwargs):
    _delete_file_from_storage(instance.author_avatar)


# ── TestimonialMedia: изображение и видео ─────────────────────────────────────

@receiver(pre_save, sender=TestimonialMedia)
def auto_download_testimonial_media(sender, instance, **kwargs):
    """
    Авто-скачивание медиа отзыва из внешнего URL на R2.
    - Тип 'image': если image пустой — скачиваем из video_url (используется как image_url при создании через API)
    - Тип 'video': прямые файлы скачиваем (YouTube/Vimeo — оставляем embed)
    - Тип 'video_file': скачивается напрямую если video_url — прямая ссылка
    """
    if instance.media_type == "image":
        # Файл уже есть — ничего не делаем
        if instance.image and instance.image.name:
            return
        # Ищем URL — это может быть video_url (в API иногда передаётся так)
        candidate_url = getattr(instance, "video_url", None) or ""
        if candidate_url and not _is_internal_url(candidate_url):
            # Проверяем что это не YouTube/Vimeo
            if not any(d in candidate_url for d in ("youtube.com", "youtu.be", "vimeo.com")):
                _download_and_save(instance, candidate_url, "image", "TestimonialMedia.image")

    elif instance.media_type in ("video", "video_file"):
        if instance.video_file and instance.video_file.name:
            return
        url = getattr(instance, "video_url", None) or ""
        if url and not _is_internal_url(url):
            # YouTube/Vimeo — это embed, не скачиваем
            if not any(d in url for d in ("youtube.com", "youtu.be", "vimeo.com")):
                _download_and_save(instance, url, "video_file", "TestimonialMedia.video_file")


@receiver(post_delete, sender=TestimonialMedia)
def delete_testimonial_media_files(sender, instance, **kwargs):
    """Удаляем файлы отзыва из R2 при удалении записи."""
    _delete_file_from_storage(instance.image)
    _delete_file_from_storage(instance.video_file)
