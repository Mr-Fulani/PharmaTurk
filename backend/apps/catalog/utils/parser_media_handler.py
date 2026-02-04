"""Универсальная загрузка медиа (фото/видео/гиф) из парсеров в R2/локальное хранилище."""
import logging
import os
from io import BytesIO

import httpx
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.catalog.utils.image_optimizer import ImageOptimizer
from apps.catalog.utils.storage_paths import (
    _build_readable_filename,
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
        media_type = detect_media_type(url)
        parser_slug = parser_name.lower().replace(" ", "-").replace("_", "-")

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers=headers or {})
            response.raise_for_status()
            content = response.content

        if media_type == "image":
            optimizer = ImageOptimizer()
            try:
                file_to_save = optimizer.optimize_image(BytesIO(content))
                ext = ".jpg"
            except Exception as e:
                logger.warning("Image optimization failed, saving as-is: %s", e)
                file_to_save = ContentFile(content)
                ext = os.path.splitext(url.split("?")[0].lower())[1] or ".jpg"
        else:
            file_to_save = ContentFile(content)
            ext = os.path.splitext(url.split("?")[0].lower())[1]
            if media_type == "video":
                ext = ext or ".mp4"
            elif media_type == "gif":
                ext = ".gif"
            else:
                ext = ext or ".jpg"

        filename = _build_readable_filename(
            [parser_slug, str(product_id), str(index)],
            f"{parser_slug}-{product_id}-{index}{ext}",
            f"{parser_slug}-{product_id}-{index}",
        )
        path = get_parsed_media_upload_path(parser_name, media_type, filename)
        saved_path = default_storage.save(path, file_to_save)
        return default_storage.url(saved_path)

    except Exception as e:
        logger.warning("Failed to download/save parsed media %s: %s", url, e)
        return ""
