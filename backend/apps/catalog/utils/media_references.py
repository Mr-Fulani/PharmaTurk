"""Ссылки БД на файлы медиа — перед удалением файла из хранилища.

Резервной копии медиа товаров нет (инцидент 14.06.2026), поэтому проверка
закрыта при сбое: если хоть одно поле прочитать не удалось, вызывающий
ничего не удаляет (``MediaReferenceCheckError``).
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from django.apps import apps
from django.db import models

# Текстовые поля, где по имени может лежать путь или URL медиа (main_image, video_url…).
_MEDIA_NAME = re.compile(r"image|video|photo|poster|thumb|media|file")


class MediaReferenceCheckError(Exception):
    """Ссылки проверить не удалось — удалять нельзя."""


def media_reference_fields() -> list[tuple[type[models.Model], str]]:
    """Все поля всех моделей, где может храниться путь или URL файла.

    FileField/URLField — как у ``cleanup_orphaned_media``; плюс CharField/TextField
    с медийным именем. JSONField не просматриваются.
    """
    fields = []
    for model in apps.get_models():
        if model._meta.proxy:
            continue  # та же таблица, что у конкретной модели
        for field in model._meta.local_concrete_fields:
            if isinstance(field, (models.FileField, models.URLField)) or (
                isinstance(field, (models.CharField, models.TextField)) and _MEDIA_NAME.search(field.name)
            ):
                fields.append((model, field.name))
    return fields


def referenced_media_paths(fragment: str) -> set[str]:
    """Пути, начинающиеся с ``fragment``, на которые ссылается хоть одно поле БД.

    Один запрос на поле (``LIKE %fragment%``), а не на каждый файл. Путь ищется
    в любом месте значения: в имени файла, в URL CDN и в ``?path=`` proxy-media.
    """
    pattern = re.compile(re.escape(fragment) + r"[^?#&\s\"'<>]*")
    found: set[str] = set()
    for model, name in media_reference_fields():
        try:
            values = (
                model._base_manager.filter(**{f"{name}__contains": fragment})
                .values_list(name, flat=True)
                .iterator(chunk_size=2000)
            )
            for value in values:
                text = str(getattr(value, "name", value) or "")
                found.update(pattern.findall(text))
                found.update(pattern.findall(unquote(text)))
        except Exception as exc:  # noqa: BLE001 — любая ошибка = «не знаем», удалять нельзя
            raise MediaReferenceCheckError(f"{model._meta.label}.{name}: {exc}") from exc
    return found
