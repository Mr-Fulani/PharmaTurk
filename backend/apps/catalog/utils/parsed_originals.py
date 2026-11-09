"""Удаление parsed-оригиналов парсера после переноса в читаемый путь.

Парсер качает фото в ``products/parsed/<парсер>/…``, сигнал (``_auto_download_impl``)
копирует его в читаемый путь товара ``products/<тип>/<slug>/…``. Оригинал после этого
никому не нужен, но оставался в R2, и еженедельная ``cleanup_orphaned_media`` отменяла
удаление из-за лимита (08.11.2026: 15 856 оригиналов SuperStep).

Теперь прогон парсера (``collect_parsed_originals``) собирает пары «оригинал → копия»
только после записи строки в БД и фиксации транзакции, а в конце прогона удаляет
оригинал, если одновременно:

- ключ лежит в ``products/parsed/<парсер>/`` и не защищён ``_is_protected_path``;
- это не видео (папка ``videos/`` или расширение видео): запас на случай, если старый
  parsed-URL видео всё же попадёт в поле товара. Повторный прогон берёт свои файлы
  прошлого прохода по parsed-URL (``_stored_media_reuse``), а в главное фото и видео
  товара пишет их читаемую копию (``ScraperIntegrationService._reused_copy``);
- копия лежит вне ``products/parsed/`` и есть в хранилище;
- ни одно поле БД на оригинал не ссылается (``referenced_media_paths``: те же
  FileField/URLField, что у ``cleanup_orphaned_media``, плюс текстовые поля с медиа);
- проверка ссылок прошла без ошибок, в БД не меньше 100 товаров, ``DEBUG`` выключен;
- нет другой сессии этого парсера в статусе «running» моложе
  ``PARSED_MEDIA_SWEEP_MIN_AGE_HOURS`` (имена parsed-файлов постоянны, параллельный
  прогон мог взять тот же оригинал и ещё не записать строку).

Резервной копии медиа нет (инцидент 14.06.2026): любой сбой — ничего не удаляем.
Ошибка удаления не ломает сохранение товара — только предупреждение в лог.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta

from celery.exceptions import SoftTimeLimitExceeded
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

PARSED_ROOT = "products/parsed/"
_PARSED_KEY = re.compile(r"products/parsed/([a-z0-9_-]+)/.+")
# Пустая или чужая БД (стек 14.06.2026) сочла бы ничейным всё.
_MIN_PRODUCTS = 100

# Пары «оригинал → копия» текущего прогона; None — сбор выключен.
_collected: ContextVar[dict[str, str] | None] = ContextVar("parsed_originals_collected", default=None)

# Имя атрибута экземпляра: переносы из pre_save ждут post_save этой строки.
PENDING_ATTR = "_resaved_parsed_originals"


def note_resaved_original(instance, field_name: str, parsed_key: str) -> None:
    """pre_save: файл поля скопирован из parsed_key. Учтётся, когда строка сохранится."""
    readable_key = getattr(getattr(instance, field_name, None), "name", "") or ""
    instance.__dict__.setdefault(PENDING_ATTR, []).append((field_name, parsed_key, readable_key))


def remember_saved_instance(instance) -> None:
    """post_save: строка записана — после commit пара попадает в сбор прогона."""
    pending = instance.__dict__.pop(PENDING_ATTR, None)
    collected = _collected.get()
    if not pending or collected is None:
        return
    for field_name, parsed_key, readable_key in pending:
        current = getattr(getattr(instance, field_name, None), "name", "") or ""
        if not readable_key or current != readable_key:
            continue  # поле успели поменять — копия не та, что сохранена
        # Откат транзакции отменяет callback: оригинал остаётся.
        transaction.on_commit(lambda p=parsed_key, r=readable_key: collected.__setitem__(p, r))


@contextmanager
def collect_parsed_originals():
    """Собрать перенесённые оригиналы за прогон и удалить их в конце (и при ошибке прогона)."""
    if _collected.get() is not None:
        yield  # внешний сбор уже идёт — удалит он
        return
    collected: dict[str, str] = {}
    token = _collected.set(collected)
    try:
        yield
    finally:
        _collected.reset(token)
        delete_resaved_originals(collected)


def delete_resaved_originals(pairs: dict[str, str]) -> int:
    """Удалить оригиналы пар «оригинал → копия». Возвращает число удалённых файлов."""
    if not pairs:
        return 0
    try:
        return _delete_resaved_originals(pairs)
    except SoftTimeLimitExceeded:
        raise  # лимит времени задачи Celery: прогон должен остановиться, а не «успеть»
    except Exception as exc:  # noqa: BLE001 — удаление оригинала не должно ронять парсинг
        logger.warning("parsed-оригиналы не удалены: %s", exc)
        return 0


def _delete_resaved_originals(pairs: dict[str, str]) -> int:
    from django.conf import settings
    from django.core.files.storage import default_storage

    from apps.catalog.models import Product
    from apps.catalog.tasks import _is_protected_path, _normalize_media_path
    from apps.catalog.utils.storage_paths import detect_media_type
    from apps.catalog.utils.media_references import MediaReferenceCheckError, referenced_media_paths
    from apps.scrapers.models import ScrapingSession

    if settings.DEBUG:
        # Как cleanup_orphaned_media: у разработчиков общий R2-префикс, а БД у каждого своя.
        logger.info("parsed-оригиналы: DEBUG=True, не удаляются (%s)", len(pairs))
        return 0
    if Product.objects.count() < _MIN_PRODUCTS:
        logger.error("parsed-оригиналы: в БД меньше %s товаров, ничего не удалено", _MIN_PRODUCTS)
        return 0

    by_parser: dict[str, dict[str, str]] = defaultdict(dict)
    for parsed_key, readable_key in pairs.items():
        match = _PARSED_KEY.fullmatch(parsed_key or "")
        if (
            not match
            or _normalize_media_path(parsed_key) != parsed_key
            or _is_protected_path(parsed_key)
            or not readable_key
            or PARSED_ROOT in readable_key
            or "/videos/" in parsed_key
            or detect_media_type(parsed_key) == "video"
        ):
            continue
        by_parser[match.group(1)][parsed_key] = readable_key

    deleted = 0
    busy_since = timezone.now() - timedelta(hours=settings.PARSED_MEDIA_SWEEP_MIN_AGE_HOURS)
    for parser, items in by_parser.items():
        # Имена parsed-файлов постоянны: параллельный прогон того же парсера мог взять
        # этот же оригинал и ещё не записать строку. Свой прогон к этому моменту уже
        # завершил сессию; «running» старше лимита — следы убитых воркеров.
        if ScrapingSession.objects.filter(
            scraper_config__parser_class__iexact=parser, status="running", started_at__gte=busy_since
        ).exists():
            logger.info("parsed-оригиналы %s: идёт другой прогон парсера, оставлены %s", parser, len(items))
            continue
        try:
            referenced = referenced_media_paths(f"{PARSED_ROOT}{parser}/")
        except MediaReferenceCheckError as exc:
            logger.error("parsed-оригиналы %s: ссылки не проверены, ничего не удалено: %s", parser, exc)
            continue
        for parsed_key, readable_key in items.items():
            if parsed_key in referenced:
                continue
            try:
                if not default_storage.exists(readable_key):
                    logger.warning("parsed-оригинал %s оставлен: нет копии %s", parsed_key, readable_key)
                    continue
                default_storage.delete(parsed_key)
                deleted += 1
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("parsed-оригинал %s не удалён: %s", parsed_key, exc)
    if deleted:
        logger.info("parsed-оригиналы: удалено %s из %s перенесённых", deleted, len(pairs))
    return deleted
