import re

from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _


MEDIA_HELP_TEXTS = {
    "card_media": _("Загрузите файл медиа для карточки. Поддерживаются изображение, видео или GIF."),
    "card_media_external_url": _("Укажите внешнюю ссылку на медиа (CDN/S3). Если заполнено, ссылка приоритетнее файла."),
    "main_image": _("Внешняя ссылка на основное изображение. Можно оставить пустым и загрузить файл рядом."),
    "main_image_file": _("Загрузите основное изображение файлами, если не используете внешний URL."),
    "video_url": _("Внешняя ссылка на видео. Можно оставить пустым и загрузить видеофайл."),
    "main_video_file": _("Загрузите видеофайл, если не используете внешний URL."),
    "image_url": _("Внешняя ссылка на изображение. Можно оставить пустым и загрузить файл."),
    "image_file": _("Загрузите изображение файлами, если не используете внешний URL."),
    "video_file": _("Загрузите видеофайл, если не используете внешний URL."),
    "before_image_url": _("Внешняя ссылка на фото до начала работ."),
    "before_image_file": _("Загрузите фото до начала работ."),
    "after_image_url": _("Внешняя ссылка на фото после завершения работ."),
    "after_image_file": _("Загрузите фото после завершения работ."),
    "alt_text": _("Короткое описание изображения для SEO и доступности."),
    "alt_text_en": _("Английское описание изображения для SEO и доступности."),
    "logo": _("URL логотипа бренда. Используется в карточках и на витрине брендов."),
    "gif_file": _("Загрузите GIF файл, если не используете внешний URL."),
    "gif_url": _("Внешняя ссылка на GIF. Можно оставить пустым и загрузить файл."),
}


def _append_help_text(current, extra):
    current = str(current or "").strip()
    extra = str(extra or "").strip()
    if not extra:
        return current
    if not current:
        return extra
    if extra in current:
        return current
    return f"{current} {extra}"


def resolve_media_url(obj, file_attr: str, url_attr: str) -> str:
    file_field = getattr(obj, file_attr, None)
    if file_field:
        try:
            return file_field.url
        except Exception:
            pass
    return str(getattr(obj, url_attr, "") or "").strip()


def render_media_preview(url: str, *, max_width: int = 180, max_height: int = 100):
    if not url:
        return _("Нет медиа")

    lower_url = url.split("?")[0].lower()
    match = re.search(
        r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|m\.youtube\.com\/watch\?v=)([^"&?\/\s]{11})',
        url,
        re.IGNORECASE,
    ) or re.search(
        r'(?:youtube\.com\/shorts\/|m\.youtube\.com\/shorts\/)([^"&?\/\s]+)',
        url,
        re.IGNORECASE,
    )
    if match and match.group(1):
        thumb = f"https://img.youtube.com/vi/{match.group(1)}/hqdefault.jpg"
        return format_html(
            '<img src="{}" style="max-width:{}px; max-height:{}px; border-radius:8px;" />',
            thumb,
            max_width,
            max_height,
        )

    if lower_url.endswith(("mp4", "mov", "webm", "m4v", "avi", "mkv")):
        return format_html(
            '<video src="{}" style="max-width:{}px; max-height:{}px; border-radius:8px;" muted loop playsinline controls></video>',
            url,
            max_width,
            max_height,
        )

    return format_html(
        '<img src="{}" style="max-width:{}px; max-height:{}px; border-radius:8px;" />',
        url,
        max_width,
        max_height,
    )


class AdminMediaHelpTextMixin:
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        extra_help = MEDIA_HELP_TEXTS.get(db_field.name)
        if extra_help and field:
            field.help_text = _append_help_text(getattr(field, "help_text", ""), extra_help)
        return field
