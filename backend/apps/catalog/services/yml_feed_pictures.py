"""
Копии маленьких фото для фидов.

ВК не принимает фото меньше 400×400, а у БАДов с ilacfiyati они 368×250. Задача
catalog.prepare_feed_pictures проверяет каждую ссылку фида один раз и для маленьких
кладёт в хранилище копию на белом квадрате; в фид идёт копия, сайт её не использует.
"""
from __future__ import annotations

import hashlib
import logging
from io import BytesIO
from typing import Iterable

import requests
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps, UnidentifiedImageError

from ..models_vk import YMLFeedPicture

logger = logging.getLogger(__name__)

MIN_SIDE = 400
COPY_SIDE = 800
COPY_QUALITY = 85
HEADER_BYTES = 64 * 1024  # размер картинки читается из начала файла
REQUEST_TIMEOUT = 20
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MudarobaFeed/1.0)"}


def picture_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def load_picture_copies() -> dict[str, str]:
    """picture_key исходной ссылки → ссылка на копию."""
    rows = YMLFeedPicture.objects.exclude(file="").values_list("source_key", "file")
    return {key: default_storage.url(name) for key, name in rows.iterator()}


def padded_copy(data: bytes) -> bytes:
    """JPEG COPY_SIDE×COPY_SIDE: фото увеличено по длинной стороне, поля белые."""
    with Image.open(BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
    scale = COPY_SIDE / max(image.size)
    image = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGB", (COPY_SIDE, COPY_SIDE), "white")
    canvas.paste(image, ((COPY_SIDE - image.width) // 2, (COPY_SIDE - image.height) // 2), image)
    output = BytesIO()
    canvas.save(output, "JPEG", quality=COPY_QUALITY, optimize=True)
    return output.getvalue()


def _download(url: str, *, header_only: bool = False) -> bytes:
    headers = dict(REQUEST_HEADERS)
    if header_only:
        headers["Range"] = f"bytes=0-{HEADER_BYTES - 1}"
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.content


def _copy_if_small(url: str) -> bytes | None:
    try:
        with Image.open(BytesIO(_download(url, header_only=True))) as image:
            if min(image.size) >= MIN_SIDE:
                return None
    except UnidentifiedImageError:
        pass  # заголовок не уместился в начало файла: решит полный файл
    data = _download(url)
    with Image.open(BytesIO(data)) as image:
        if min(image.size) >= MIN_SIDE:
            return None
    return padded_copy(data)


def prepare_feed_pictures(urls: Iterable[str]) -> dict[str, int]:
    """Проверяет новые ссылки. Сбой не запоминается: ссылка повторится при следующем запуске."""
    known = set(YMLFeedPicture.objects.values_list("source_key", flat=True))
    result = {"checked": 0, "copied": 0, "failed": 0}
    for url in urls:
        key = picture_key(url)
        if key in known:
            continue
        known.add(key)
        try:
            copy = _copy_if_small(url)
        except OSError as exc:  # сеть (RequestException) и битая картинка
            logger.warning("Фото фида не проверено: %s (%s)", url, exc)
            result["failed"] += 1
            continue
        record = YMLFeedPicture(source_key=key)
        if copy is not None:
            record.file.save(f"{key[:32]}.jpg", ContentFile(copy), save=False)
            result["copied"] += 1
        record.save()
        result["checked"] += 1
    logger.info("prepare_feed_pictures: %s", result)
    return result
