"""Универсальная загрузка медиа (фото/видео/гиф) из парсеров в R2/локальное хранилище."""
import hashlib
import logging
import os
from io import BytesIO

import httpx
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.catalog.utils.image_optimizer import ImageOptimizer
from apps.catalog.utils.storage_paths import (
    detect_media_type,
    get_parsed_media_upload_path,
)

logger = logging.getLogger(__name__)


def download_and_optimize_parsed_media(
    url,
    parser_name,
    product_id,
    index,
    headers=None,
    timeout=15,
):
    """
    Универсальная функция для загрузки медиа (фото/видео/гиф) из любого парсера.

    Args:
        url: URL медиа-файла
        parser_name: Имя парсера (instagram, ilacabak, zara и т.д.)
        product_id: ID или external_id товара
        index: Индекс файла (0 для главного)
        headers: Опциональные HTTP-заголовки
        timeout: Таймаут запроса в секундах

    Returns:
        str: URL загруженного файла в R2/локальном хранилище или пустая строка при ошибке
    """
    if not url:
        return ""

    try:
        parser_slug = parser_name.lower().replace(" ", "-").replace("_", "-")

        content = None
        content_type = ""
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            head_response = client.head(url, headers=headers or {})
            if head_response.status_code < 400:
                content_type = (head_response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if not content_type:
                response = client.get(url, headers=headers or {})
                response.raise_for_status()
                content = response.content
                content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()

            media_type = detect_media_type(url)
            if content_type:
                if content_type.startswith("video/"):
                    media_type = "video"
                elif content_type == "image/gif" or content_type.endswith("+gif"):
                    media_type = "gif"
                elif content_type.startswith("image/"):
                    media_type = "image"

            ext = os.path.splitext(url.split("?")[0].lower())[1]
            if not ext and content_type:
                ext = {
                    "video/mp4": ".mp4",
                    "video/webm": ".webm",
                    "video/quicktime": ".mov",
                    "video/x-msvideo": ".avi",
                    "video/x-matroska": ".mkv",
                    "image/png": ".png",
                    "image/jpeg": ".jpg",
                    "image/webp": ".webp",
                    "image/gif": ".gif",
                }.get(content_type, "")
            if media_type == "video":
                ext = ext or ".mp4"
            elif media_type == "gif":
                ext = ".gif"
            else:
                ext = ext or ".jpg"

            url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
            filename = f"{parser_slug}-{product_id}-{index}-{url_hash}{ext}"
            path = get_parsed_media_upload_path(parser_name, media_type, filename)
            if default_storage.exists(path):
                return default_storage.url(path)

        if content is None:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(url, headers=headers or {})
                response.raise_for_status()
                content = response.content

        if media_type == "image":
            optimizer = ImageOptimizer()
            try:
                file_to_save = optimizer.optimize_image(BytesIO(content))
            except Exception as e:
                logger.warning("Image optimization failed, saving as-is: %s", e)
                file_to_save = ContentFile(content)
        else:
            file_to_save = ContentFile(content)

        saved_path = default_storage.save(path, file_to_save)

        return default_storage.url(saved_path)


    except Exception as e:
        logger.warning("Failed to download/save parsed media %s: %s", url, e)
        return ""
