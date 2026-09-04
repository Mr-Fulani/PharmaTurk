"""Celery задачи для парсинга сайтов."""

import logging
from typing import Dict, List, Optional

import requests
from celery import shared_task, current_app
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .base.scraper import ScraperAccessBlockedError
from .models import (
    InstagramScraperTask,
    ScraperConfig,
    ScrapingSession,
    SiteScraperTask,
)
from .parsers.registry import get_parser
from .services import (
    ScraperIntegrationService,
    DeduplicationService,
    ScraperTaskCancelled,
    ScraperTaskPaused,
    ScraperTaskSuperseded,
)

logger = logging.getLogger(__name__)


def _proxy_account_error_message(exc: Exception) -> Optional[str]:
    """Возвращает понятное администратору описание блокировки прокси-аккаунта."""
    error_text = str(exc).lower()
    if "407" in error_text and "account is suspended" in error_text:
        return (
            "Прокси недоступен: аккаунт прокси-сервиса приостановлен (HTTP 407). "
            "Проверьте оплату, баланс и статус аккаунта у провайдера прокси."
        )
    return None


def _build_duplicate_candidates_notification_text(result: Dict) -> str:
    duplicates_found = result.get("duplicates_found", 0)
    created = result.get("candidates_created", 0)
    updated = result.get("candidates_updated", 0)
    admin_url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}/admin/scrapers/productduplicatecandidate/"

    lines = [
        "🔎 Найдены кандидаты в дубликаты товаров",
        "",
        f"Всего найдено: {duplicates_found}",
        f"Создано новых: {created}",
        f"Обновлено существующих: {updated}",
    ]

    duplicates = result.get("duplicates") or []
    if duplicates:
        lines.extend(["", "Примеры:"])
        for item in duplicates[:5]:
            lines.append(
                f"- {item.get('canonical_product_name')} ↔ {item.get('duplicate_product_name')} "
                f"(скор {float(item.get('score', 0)):.1f})"
            )

    if admin_url and admin_url.startswith(("http://", "https://")):
        lines.extend(["", f"Модерация: {admin_url}"])

    return "\n".join(lines)


def _send_duplicate_candidates_notification(result: Dict) -> bool:
    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "") or ""
    if not bot_token or not chat_id:
        logger.info("Telegram не настроен — уведомление о дубликатах пропущено")
        return False

    duplicates_found = int(result.get("duplicates_found", 0) or 0)
    created = int(result.get("candidates_created", 0) or 0)
    updated = int(result.get("candidates_updated", 0) or 0)
    if duplicates_found <= 0 and created <= 0 and updated <= 0:
        logger.info("Новых или обновлённых кандидатов в дубликаты нет — уведомление не отправляем")
        return False

    text = _build_duplicate_candidates_notification_text(result)
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        if not response.ok:
            logger.warning(
                "Не удалось отправить Telegram-уведомление о дубликатах: HTTP %s",
                response.status_code,
            )
            return False
        logger.info("Telegram-уведомление о кандидатах в дубликаты отправлено")
        return True
    except requests.RequestException:
        # requests exceptions may include the API URL, which embeds the bot token.
        logger.warning("Ошибка отправки Telegram-уведомления о дубликатах")
        return False


def _is_site_task_cancelled(site_task_id: Optional[int]) -> bool:
    """Возвращает True, если задачу отменили из админки."""
    if not site_task_id:
        return False
    status = (
        SiteScraperTask.objects.filter(id=site_task_id).values_list("status", flat=True).first()
    )
    return status == "cancelled"


def _cancel_site_task(site_task_id: int, message: str) -> None:
    """Фиксирует отмену задачи в БД."""
    SiteScraperTask.objects.filter(id=site_task_id).update(
        status="cancelled",
        error_message=message,
        log_output=message,
        finished_at=timezone.now(),
    )


def _sweep_parsed_orphans(parser_name: str) -> int:
    """Удаляет из products/parsed/<parser>/ файлы без единой ссылки в БД.

    Сигнал переноса чистит parsed-оригиналы у сохранённых товаров, но у
    пропущенных (дубли) скачанное медиа оставалось орфаном. Этот sweep после
    скрейпа гарантирует, что products/parsed/ не копится. Удаляем ТОЛЬКО файлы
    с нулём ссылок — это не массовый cleanup, риска вайпа нет.
    """
    try:
        from django.apps import apps
        from django.core.files.storage import default_storage
        from apps.catalog.utils.r2_utils import get_r2_client
        from django.conf import settings

        prefix = f"products/parsed/{(parser_name or '').lower()}/"
        client = get_r2_client()
        bucket = settings.R2_BUCKET_NAME
        paginator = client.get_paginator("list_objects_v2")
        keys = [
            obj["Key"]
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
            for obj in page.get("Contents", [])
        ]
        if not keys:
            return 0

        image_fields = []
        for model in apps.get_app_config("catalog").get_models():
            for field in model._meta.get_fields():
                fname = getattr(field, "name", "")
                if hasattr(field, "attname") and any(
                    k in fname for k in ("image_url", "image_file", "main_image", "video")
                ):
                    image_fields.append((model, fname))

        def referenced(key: str) -> bool:
            for model, fname in image_fields:
                try:
                    if model.objects.filter(**{f"{fname}__contains": key}).exists():
                        return True
                except Exception:
                    continue
            return False

        orphans = [k for k in keys if not referenced(k)]
        for key in orphans:
            try:
                default_storage.delete(key)
            except Exception:
                pass
        if orphans:
            logger.info("parsed-sweep %s: удалено орфанов %s/%s", parser_name, len(orphans), len(keys))
        return len(orphans)
    except Exception as exc:  # noqa: BLE001 — sweep не должен ронять задачу
        logger.warning("parsed-sweep %s не удался: %s", parser_name, exc)
        return 0


def _site_task_status(site_task_id: Optional[int]) -> Optional[str]:
    """Текущий статус задачи (или None)."""
    if not site_task_id:
        return None
    return (
        SiteScraperTask.objects.filter(id=site_task_id).values_list("status", flat=True).first()
    )


def _pause_site_task(site_task_id: int, message: str) -> None:
    """Фиксирует паузу: статус сохраняется, resume_page уже стоит на текущем чанке."""
    SiteScraperTask.objects.filter(id=site_task_id).update(
        status="paused",
        error_message=message,
        log_output=message,
        finished_at=timezone.now(),
    )


def revoke_site_scraper_task(task: SiteScraperTask, *, terminate: bool = True) -> bool:
    """Отзывает текущую Celery-задачу для SiteScraperTask, если task_id известен."""
    if not task.task_id:
        return False
    current_app.control.revoke(task.task_id, terminate=terminate, signal="SIGTERM")
    return True


def revoke_instagram_scraper_task(
    task: InstagramScraperTask,
    *,
    terminate: bool = True,
) -> bool:
    """Отзывает текущую Celery-задачу Instagram, если её ID уже известен."""
    if not task.task_id:
        return False
    current_app.control.revoke(task.task_id, terminate=terminate, signal="SIGTERM")
    return True


def _append_instagram_task_log(
    task_id: int,
    line: str,
    *,
    expected_task_id: str = "",
) -> None:
    """Добавляет строку в журнал задачи, не затирая live-progress worker-а."""
    from django.db import transaction

    with transaction.atomic():
        task = (
            InstagramScraperTask.objects.select_for_update()
            .filter(id=task_id)
            .first()
        )
        if not task:
            return
        if expected_task_id and task.task_id != expected_task_id:
            return
        task.log_output = "\n".join(
            part for part in (task.log_output.rstrip(), line) if part
        )
        task.save(update_fields=["log_output"])


def _resolve_instagram_task_category(task: InstagramScraperTask):
    """Подкатегория → целевая категория → legacy slug."""
    from apps.catalog.models import Category

    if task.target_subcategory_id:
        return task.target_subcategory
    if task.target_category_id:
        return task.target_category
    if task.category:
        category = Category.objects.filter(slug=task.category).first()
        if category:
            return category
    return None


def _get_instagram_scraper_config(default_category=None) -> ScraperConfig:
    """Возвращает Instagram config или безопасно создаёт его при наличии категории."""
    from apps.catalog.models import Category

    config = ScraperConfig.objects.filter(parser_class="instagram").first()
    if config:
        if not config.is_enabled:
            raise ValueError("Конфигурация парсера Instagram отключена")
        return config

    default_category = default_category or Category.objects.first()
    if default_category is None:
        raise ValueError(
            "ScraperConfig для Instagram не найден и не может быть создан: "
            "в каталоге нет ни одной категории"
        )
    return ScraperConfig.objects.create(
        name="instagram",
        parser_class="instagram",
        base_url="https://www.instagram.com",
        is_enabled=True,
        delay_min=5.0,
        delay_max=15.0,
        max_pages_per_run=100,
        max_products_per_run=100,
        max_images_per_product=10,
        default_category=default_category,
    )


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True)
def run_instagram_scraper_task(
    self,
    instagram_task_id: int,
    resume: bool = False,
) -> Dict:
    """Асинхронный запуск Instagram с live-progress и управлением из Admin."""
    try:
        task = InstagramScraperTask.objects.select_related(
            "target_category",
            "target_subcategory",
        ).get(id=instagram_task_id)
    except InstagramScraperTask.DoesNotExist:
        return {
            "status": "error",
            "error": f"Instagram-задача с ID {instagram_task_id} не найдена",
        }

    celery_task_id = str(self.request.id or "")
    if task.status == "cancelled":
        return {"status": "cancelled", "message": "Задача остановлена до запуска"}
    if task.status == "paused":
        return {"status": "paused", "message": "Задача поставлена на паузу до запуска"}
    if celery_task_id and task.task_id and task.task_id != celery_task_id:
        return {
            "status": "superseded",
            "message": f"Задачу уже выполняет другой запуск {task.task_id}",
        }

    baseline_found = task.products_found if resume else 0
    baseline_created = task.products_created if resume else 0
    baseline_updated = task.products_updated if resume else 0
    baseline_skipped = task.products_skipped if resume else 0
    baseline_posts = task.posts_processed if resume else 0
    baseline_errors = task.errors_count if resume else 0
    username = (task.instagram_username or "").strip().lstrip("@")
    start_url = task.post_url or (
        f"https://www.instagram.com/{username}/" if username else ""
    )
    if not start_url:
        error_msg = "Не задана ссылка на пост или Instagram username"
        InstagramScraperTask.objects.filter(id=task.id).update(
            status="failed",
            error_message=error_msg,
            finished_at=timezone.now(),
        )
        return {"status": "error", "error": error_msg}

    InstagramScraperTask.objects.filter(id=task.id).update(
        status="running",
        task_id=celery_task_id,
        started_at=task.started_at or timezone.now(),
        finished_at=None,
        error_message="",
    )
    mode = "Продолжение" if resume else "Запуск"
    _append_instagram_task_log(
        task.id,
        "\n".join(
            [
                f"--- {mode} Instagram-задачи ---",
                f"Источник: {start_url}",
                f"Максимум постов: {task.max_posts}",
                f"Celery task id: {celery_task_id or '-'}",
                f"Старт: {timezone.now().isoformat()}",
            ]
        ),
        expected_task_id=celery_task_id,
    )

    try:
        if baseline_found >= task.max_posts:
            InstagramScraperTask.objects.filter(
                id=task.id,
                task_id=celery_task_id,
            ).update(
                status="completed",
                finished_at=timezone.now(),
            )
            _append_instagram_task_log(
                task.id,
                "Лимит товаров уже достигнут; задача завершена.",
                expected_task_id=celery_task_id,
            )
            return {"status": "success", "instagram_task_id": task.id}

        target_category = _resolve_instagram_task_category(task)
        scraper_config = _get_instagram_scraper_config(target_category)
        session = ScraperIntegrationService().run_scraper(
            scraper_config=scraper_config,
            start_url=start_url,
            max_pages=task.max_posts,
            max_products=task.max_posts,
            target_category=target_category,
            instagram_task_id=task.id,
            instagram_run_token=str(task.run_token),
            total_scraped=baseline_found,
            total_created=baseline_created,
            total_updated=baseline_updated,
            total_skipped=baseline_skipped,
            total_posts_processed=baseline_posts,
            total_errors_count=baseline_errors,
            celery_task_id=celery_task_id,
        )

        totals = {
            "products_found": baseline_found + session.products_found,
            "products_created": baseline_created + session.products_created,
            "products_updated": baseline_updated + session.products_updated,
            "products_skipped": baseline_skipped + session.products_skipped,
            "errors_count": baseline_errors + session.errors_count,
            "posts_processed": max(baseline_posts, session.pages_processed),
        }
        updated = InstagramScraperTask.objects.filter(
            id=task.id,
            task_id=celery_task_id,
        ).update(
            status="completed",
            session=session,
            finished_at=timezone.now(),
            error_message="",
            **totals,
        )
        if not updated:
            return {
                "status": "superseded",
                "message": "Результат старого Instagram-запуска отброшен",
            }
        _append_instagram_task_log(
            task.id,
            "\n".join(
                [
                    "--- Итог ---",
                    f"Сессия: #{session.id}",
                    f"Постов обработано: {totals['posts_processed']}/{task.max_posts}",
                    f"Товаров найдено: {totals['products_found']}",
                    f"Создано: {totals['products_created']}",
                    f"Обновлено: {totals['products_updated']}",
                    f"Пропущено: {totals['products_skipped']}",
                    f"Ошибок: {totals['errors_count']}",
                    f"Финиш: {timezone.now().isoformat()}",
                ]
            ),
            expected_task_id=celery_task_id,
        )
        return {
            "status": "success",
            "instagram_task_id": task.id,
            "session_id": session.id,
            **totals,
        }

    except ScraperTaskSuperseded as exc:
        logger.info("Instagram-задача #%s заменена новым запуском: %s", task.id, exc)
        return {"status": "superseded", "message": str(exc)}
    except ScraperTaskPaused as exc:
        InstagramScraperTask.objects.filter(id=task.id, task_id=celery_task_id).update(
            status="paused",
            finished_at=timezone.now(),
            error_message=str(exc),
        )
        _append_instagram_task_log(
            task.id,
            f"Пауза: {exc}",
            expected_task_id=celery_task_id,
        )
        return {"status": "paused", "message": str(exc)}
    except ScraperTaskCancelled as exc:
        InstagramScraperTask.objects.filter(id=task.id, task_id=celery_task_id).update(
            status="cancelled",
            finished_at=timezone.now(),
            error_message=str(exc),
        )
        _append_instagram_task_log(
            task.id,
            f"Остановлено: {exc}",
            expected_task_id=celery_task_id,
        )
        return {"status": "cancelled", "message": str(exc)}
    except SoftTimeLimitExceeded:
        error_msg = (
            "Instagram-задача автоматически поставлена на паузу после достижения "
            "лимита времени. Нажмите «Продолжить» — уже сохранённые посты не потеряны."
        )
        InstagramScraperTask.objects.filter(
            id=task.id,
            task_id=celery_task_id,
        ).update(
            status="paused",
            finished_at=timezone.now(),
            error_message=error_msg,
        )
        _append_instagram_task_log(
            task.id,
            error_msg,
            expected_task_id=celery_task_id,
        )
        return {"status": "paused", "message": error_msg}
    except Exception as exc:
        error_msg = _proxy_account_error_message(exc) or str(exc)
        updated = InstagramScraperTask.objects.filter(
            id=task.id,
            task_id=celery_task_id,
        ).update(
            status="failed",
            finished_at=timezone.now(),
            error_message=error_msg,
        )
        if updated:
            _append_instagram_task_log(
                task.id,
                f"Ошибка: {error_msg}\nФиниш: {timezone.now().isoformat()}",
                expected_task_id=celery_task_id,
            )
        logger.exception("Ошибка Instagram-задачи #%s", task.id)
        return {
            "status": "error",
            "instagram_task_id": task.id,
            "error": error_msg,
        }


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    # Подтверждаем чанк только после завершения. При пересоздании worker Redis
    # вернёт его в очередь, и цепочка продолжится без ручного перезапуска.
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_scraper_task(self,
                    scraper_config_id: int,
                    start_url: Optional[str] = None,
                    max_pages: Optional[int] = None,
                    max_products: Optional[int] = None,
                    max_images_per_product: Optional[int] = None,
                    site_task_id: Optional[int] = None,
                    start_page: int = 1,
                    total_scraped: int = 0,
                    total_created: int = 0,
                    total_updated: int = 0,
                    total_skipped: int = 0,
                    total_analogs_found: int = 0,
                    total_analog_links_saved: int = 0,
                    total_analog_stubs_created: int = 0,
                    total_analog_stubs_upgraded: int = 0,
                    total_analog_errors: int = 0) -> Dict:
    """Задача: запуск парсера.

    start_page / total_scraped используются для авточепочки при парсинге больших каталогов.
    Каждый чанк (max_pages страниц) самостоятельно планирует следующий чанк через apply_async,
    пока не будет достигнут лимит max_products или каталог не исчерпан.
    """
    site_task = None
    if site_task_id:
        site_task = SiteScraperTask.objects.filter(id=site_task_id).first()

    try:
        # Получаем конфигурацию
        scraper_config = ScraperConfig.objects.get(id=scraper_config_id)
        
        if not scraper_config.is_enabled:
            result = {
                'status': 'skipped',
                'message': 'Парсер отключен',
                'scraper_name': scraper_config.name
            }
            if site_task:
                SiteScraperTask.objects.filter(id=site_task.id).update(
                    status='failed',
                    error_message='Парсер отключен',
                    log_output='Парсер отключен',
                    finished_at=timezone.now()
                )
            return result
        
        # Проверяем статус парсера
        if scraper_config.status == 'maintenance':
            result = {
                'status': 'skipped',
                'message': 'Парсер на обслуживании',
                'scraper_name': scraper_config.name
            }
            if site_task:
                SiteScraperTask.objects.filter(id=site_task.id).update(
                    status='failed',
                    error_message='Парсер на обслуживании',
                    log_output='Парсер на обслуживании',
                    finished_at=timezone.now()
                )
            return result
        
        requested_chunk_pages = max_pages or scraper_config.max_pages_per_run
        parser_class = get_parser(scraper_config.parser_class)
        max_pages_per_chunk = getattr(parser_class, "MAX_PAGES_PER_CHUNK", None)
        runtime_max_pages = (
            min(requested_chunk_pages, max_pages_per_chunk)
            if max_pages_per_chunk
            else requested_chunk_pages
        )

        log_lines = [
            f"Парсер: {scraper_config.name}",
            f"URL: {start_url or scraper_config.base_url}",
            f"Страница старт: {start_page}",
            f"Страниц в чанке: {runtime_max_pages}",
            f"Макс. товаров всего: {max_products or scraper_config.max_products_per_run}",
            f"Макс. медиа: {max_images_per_product or scraper_config.max_images_per_product}",
            f"Старт: {timezone.now().isoformat()}"
        ]

        target_category = None
        if site_task:
            status_before = _site_task_status(site_task.id)
            if status_before == "cancelled":
                return {
                    "status": "cancelled",
                    "message": "Задача остановлена пользователем до старта чанка.",
                    "scraper_name": scraper_config.name,
                }
            if status_before == "paused":
                # Пауза успела сработать до старта чанка: resume_page = текущая
                # страница, чтобы «Продолжить» возобновил именно с неё.
                SiteScraperTask.objects.filter(id=site_task.id).update(resume_page=start_page)
                return {
                    "status": "paused",
                    "message": "Задача поставлена на паузу до старта чанка.",
                    "scraper_name": scraper_config.name,
                }
            # Курсор возобновления = страница текущего чанка. Так даже при сбое
            # воркера «Продолжить» возобновит с начала недообработанного чанка.
            SiteScraperTask.objects.filter(id=site_task.id).update(resume_page=start_page)
            # Первый чанк: переводим в 'running'. Последующие: already running, условие не сработает.
            SiteScraperTask.objects.filter(id=site_task.id, status='pending').update(
                status='running'
            )
            SiteScraperTask.objects.filter(id=site_task.id).update(
                task_id=self.request.id or "",
            )
            SiteScraperTask.objects.filter(id=site_task.id, started_at__isnull=True).update(started_at=timezone.now())
            # Получаем свежие данные задачи
            site_task.refresh_from_db()
            if max_images_per_product is None:
                max_images_per_product = site_task.max_images_per_product
            # Как в админке Instagram/Site: подкатегория приоритетнее корневой целевой категории
            if getattr(site_task, "target_subcategory_id", None):
                target_category = site_task.target_subcategory
            elif site_task.target_category_id:
                target_category = site_task.target_category

        # Запускаем парсер
        integration_service = ScraperIntegrationService()
        session = integration_service.run_scraper(
            scraper_config=scraper_config,
            start_url=start_url,
            max_pages=runtime_max_pages,
            max_products=max_products,
            max_images_per_product=max_images_per_product,
            target_category=target_category,
            target_brand=(site_task.target_brand if site_task else None),
            gender=(site_task.gender if site_task else ""),
            start_page=start_page,
            site_task_id=site_task_id,
            total_scraped=total_scraped,
            total_created=total_created,
            total_updated=total_updated,
            total_skipped=total_skipped,
            total_analogs_found=total_analogs_found,
            total_analog_links_saved=total_analog_links_saved,
            total_analog_stubs_created=total_analog_stubs_created,
            total_analog_stubs_upgraded=total_analog_stubs_upgraded,
            total_analog_errors=total_analog_errors,
            celery_task_id=self.request.id,
        )
        session_analogs_found = int(getattr(session, "analogs_found", 0) or 0)
        session_analog_links_saved = int(getattr(session, "analog_links_saved", 0) or 0)
        session_analog_stubs_created = int(getattr(session, "analog_stubs_created", 0) or 0)
        session_analog_stubs_upgraded = int(getattr(session, "analog_stubs_upgraded", 0) or 0)
        session_analog_errors = int(getattr(session, "analog_errors", 0) or 0)

        result = {
            'status': 'success',
            'scraper_name': scraper_config.name,
            'session_id': session.id,
            'start_page': start_page,
            'products_found': session.products_found,
            'products_created': session.products_created,
            'products_updated': session.products_updated,
            'products_skipped': session.products_skipped,
            'analogs_found': session_analogs_found,
            'analog_links_saved': session_analog_links_saved,
            'analog_stubs_created': session_analog_stubs_created,
            'analog_stubs_upgraded': session_analog_stubs_upgraded,
            'analog_errors': session_analog_errors,
            'pages_processed': session.pages_processed,
            'errors_count': session.errors_count,
            'stop_reason': str(getattr(session, "_stop_reason", "") or ""),
            'duration': str(session.duration) if session.duration else None,
            'timestamp': timezone.now().isoformat()
        }

        is_ilacfiyati = getattr(parser_class, "__name__", "") == "IlacFiyatiParser"
        primary_label = "Основных препаратов" if is_ilacfiyati else "Товаров"
        show_analog_stats = is_ilacfiyati or any(
            (
                session_analogs_found,
                session_analog_links_saved,
                session_analog_stubs_created,
                session_analog_stubs_upgraded,
                session_analog_errors,
            )
        )
        log_lines.extend([
            f"{primary_label} найдено (чанк): {session.products_found}",
            f"{primary_label} создано: {session.products_created}",
            f"{primary_label} обновлено: {session.products_updated}",
            f"{primary_label} пропущено: {session.products_skipped}",
        ])
        if show_analog_stats:
            log_lines.extend([
                f"Аналогов найдено в источнике: {session_analogs_found}",
                f"Связей аналогов сохранено: {session_analog_links_saved}",
                f"Заглушек аналогов создано: {session_analog_stubs_created}",
                f"Заглушек заполнено полными данными: {session_analog_stubs_upgraded}",
                f"Ошибок обработки аналогов: {session_analog_errors}",
            ])
        log_lines.extend([
            f"Обработано страниц: {session.pages_processed}",
            f"Ошибок всего: {session.errors_count}",
            f"Финиш: {timezone.now().isoformat()}"
        ])
        stop_reason = str(getattr(session, "_stop_reason", "") or "")
        if stop_reason:
            log_lines.append(f"Причина остановки: {stop_reason}")

        if site_task:
            site_task.refresh_from_db()
            products_this_chunk = session.products_found
            new_total = total_scraped + products_this_chunk
            new_created = total_created + session.products_created
            new_updated = total_updated + session.products_updated
            new_skipped = total_skipped + session.products_skipped
            new_analogs_found = total_analogs_found + session_analogs_found
            new_analog_links_saved = total_analog_links_saved + session_analog_links_saved
            new_analog_stubs_created = total_analog_stubs_created + session_analog_stubs_created
            new_analog_stubs_upgraded = total_analog_stubs_upgraded + session_analog_stubs_upgraded
            new_analog_errors = total_analog_errors + session_analog_errors
            new_pages_total = site_task.pages_processed + session.pages_processed
            chunk_pages = session.max_pages
            effective_max = site_task.max_products
            reported_next_page = getattr(session, "_next_start_page", None)
            next_start_page = (
                reported_next_page
                if isinstance(reported_next_page, int) and reported_next_page >= 1
                else start_page + chunk_pages
            )

            log_lines.extend([
                "--- Итого по всей задаче ---",
                f"{primary_label} найдено: {new_total}",
            ])
            if show_analog_stats:
                log_lines.extend([
                    f"Аналогов найдено в источнике: {new_analogs_found}",
                    f"Связей аналогов сохранено: {new_analog_links_saved}",
                    f"Заглушек аналогов создано: {new_analog_stubs_created}",
                    f"Заглушек заполнено полными данными: {new_analog_stubs_upgraded}",
                    f"Ошибок обработки аналогов: {new_analog_errors}",
                ])

            # Абсолютные значения (не F()): live-апдейт в процессе ставит ту же
            # абсолютную сумму total_X + текущий чанк, поэтому финал чанка совпадает
            # с последним live-значением — без двойного счёта.
            common_updates = dict(
                session=session,
                products_found=new_total,
                products_created=new_created,
                products_updated=new_updated,
                products_skipped=new_skipped,
                analogs_found=new_analogs_found,
                analog_links_saved=new_analog_links_saved,
                analog_stubs_created=new_analog_stubs_created,
                analog_stubs_upgraded=new_analog_stubs_upgraded,
                analog_errors=new_analog_errors,
                pages_processed=F('pages_processed') + session.pages_processed,
                errors_count=F('errors_count') + session.errors_count,
                log_output="\n".join(log_lines),
            )

            if site_task.status in ("cancelled", "paused"):
                # Финализируем счётчики тем, что успели спарсить до остановки,
                # иначе created/updated залипают в 0. Статус (cancelled/paused)
                # сохраняем — для paused resume_page уже стоит на текущем чанке,
                # «Продолжить» возобновит с него.
                SiteScraperTask.objects.filter(id=site_task.id).update(
                    **common_updates,
                    finished_at=timezone.now(),
                )
                message = (
                    "Задача остановлена пользователем."
                    if site_task.status == "cancelled"
                    else "Задача поставлена на паузу — можно продолжить."
                )
                return {
                    **result,
                    "status": site_task.status,
                    "message": message,
                }

            # Авточепочка только для парсеров с настоящей постраничной пагинацией
            # (start_page). Иначе следующий чанк переоткрыл бы те же товары, раздувая
            # счётчики (например, 510 «обновлений» на 104 реальные карточки).
            parser_class = get_parser(scraper_config.parser_class)
            supports_url_chunking = getattr(parser_class, "supports_page_chunking_for_url", None)
            if callable(supports_url_chunking):
                supports_chunking = bool(
                    supports_url_chunking(start_url or scraper_config.base_url)
                )
            else:
                supports_chunking = bool(getattr(parser_class, "SUPPORTS_PAGE_CHUNKING", False))

            # Повторно сохранённые товары могли быть отфильтрованы cache, а при
            # soft-timeout следующий чанк обязан начать с той же страницы.
            chunk_made_progress = bool(
                products_this_chunk > 0
                or session.pages_processed > 0
                or (
                    getattr(session, "_chunk_interrupted", False)
                    and getattr(session, "_reports_next_start_page", False)
                )
            )
            should_chain = (
                supports_chunking
                and site_task.status != "cancelled"
                and chunk_made_progress
                and new_total < effective_max
                and getattr(session, "_has_more_pages", None) is not False
            )

            if should_chain:
                next_task = run_scraper_task.apply_async(kwargs=dict(
                    scraper_config_id=scraper_config_id,
                    start_url=start_url,
                    max_pages=runtime_max_pages,
                    max_products=max_products,
                    max_images_per_product=max_images_per_product,
                    site_task_id=site_task_id,
                    start_page=next_start_page,
                    total_scraped=new_total,
                    total_created=new_created,
                    total_updated=new_updated,
                    total_skipped=new_skipped,
                    total_analogs_found=new_analogs_found,
                    total_analog_links_saved=new_analog_links_saved,
                    total_analog_stubs_created=new_analog_stubs_created,
                    total_analog_stubs_upgraded=new_analog_stubs_upgraded,
                    total_analog_errors=new_analog_errors,
                ))
                SiteScraperTask.objects.filter(id=site_task.id).update(
                    **common_updates,
                    task_id=next_task.id,
                )
                logger.info(
                    f"Парсер {scraper_config.name}: чанк стр.{start_page} готов "
                    f"({products_this_chunk} товаров, всего {new_total}/{effective_max}). "
                    f"Следующий чанк со стр.{next_start_page}"
                )
            else:
                SiteScraperTask.objects.filter(id=site_task.id).update(
                    **common_updates,
                    status='completed',
                    resume_page=1,
                    finished_at=timezone.now(),
                )
                logger.info(
                    f"Парсер {scraper_config.name} завершён: "
                    f"всего {new_total} товаров, реально обработано "
                    f"{new_pages_total} страниц"
                )
                # Цепочка завершена — подчищаем parsed-орфаны парсера (от пропущенных дублей).
                _sweep_parsed_orphans(scraper_config.parser_class)
        else:
            logger.info(f"Парсер {scraper_config.name} завершен успешно: {session.products_found} товаров найдено")

        return result

    except ScraperTaskSuperseded as e:
        # Новый force-restart уже владеет SiteScraperTask. Старый worker не должен
        # менять его статус или счётчики после обнаружения нового task_id.
        logger.info("Старый запуск парсера %s остановлен: %s", scraper_config_id, e)
        return {
            "status": "superseded",
            "message": str(e),
            "scraper_config_id": scraper_config_id,
            "timestamp": timezone.now().isoformat(),
        }

    except ScraperTaskCancelled as e:
        error_msg = str(e)
        logger.info("Задача парсинга %s отменена: %s", scraper_config_id, error_msg)
        if site_task:
            _cancel_site_task(site_task.id, error_msg)
        return {
            "status": "cancelled",
            "message": error_msg,
            "scraper_config_id": scraper_config_id,
            "timestamp": timezone.now().isoformat(),
        }

    except ScraperTaskPaused as e:
        # Пауза посреди чанка: resume_page уже стоит на странице текущего чанка,
        # счётчики обновлены инкрементально — «Продолжить» возобновит с неё.
        msg = str(e)
        logger.info("Задача парсинга %s на паузе: %s", scraper_config_id, msg)
        if site_task:
            _pause_site_task(site_task.id, msg)
        return {
            "status": "paused",
            "message": msg,
            "scraper_config_id": scraper_config_id,
            "timestamp": timezone.now().isoformat(),
        }
        
    except SoftTimeLimitExceeded:
        error_msg = "Задача превысила лимит времени (soft limit)"
        logger.warning(f"SoftTimeLimitExceeded для задачи парсера {scraper_config_id}")
        if site_task:
            SiteScraperTask.objects.filter(id=site_task.id).update(
                status='failed',
                error_message=error_msg,
                log_output=error_msg,
                finished_at=timezone.now()
            )
        raise

    except ScraperConfig.DoesNotExist:
        error_msg = f"Конфигурация парсера с ID {scraper_config_id} не найдена"
        logger.error(error_msg)
        if site_task:
            SiteScraperTask.objects.filter(id=site_task.id).update(
                status='failed',
                error_message=error_msg,
                log_output=error_msg,
                finished_at=timezone.now()
            )
        return {
            'status': 'error',
            'error': error_msg,
            'timestamp': timezone.now().isoformat()
        }

    except ScraperAccessBlockedError as e:
        # Постоянный 401/403 не исправится повтором через минуту: показываем причину
        # администратору и не создаём лишнюю нагрузку на защищаемый сайт.
        error_msg = f"Доступ к источнику отклонён: {e}"
        logger.error(error_msg)
        if site_task:
            SiteScraperTask.objects.filter(id=site_task.id).update(
                status='failed',
                error_message=error_msg,
                log_output=error_msg,
                finished_at=timezone.now(),
            )
        return {
            'status': 'error',
            'error': error_msg,
            'scraper_config_id': scraper_config_id,
            'timestamp': timezone.now().isoformat(),
        }

    except Exception as e:
        proxy_error_msg = _proxy_account_error_message(e)
        error_msg = proxy_error_msg or f"Ошибка в задаче парсинга: {e}"
        logger.error(error_msg)
        if site_task:
            SiteScraperTask.objects.filter(id=site_task.id).update(
                status='failed',
                error_message=error_msg,
                log_output=error_msg,
                finished_at=timezone.now()
            )

        # Приостановленный аккаунт прокси не восстановится от автоматического
        # повтора: завершаем задачу сразу и показываем администратору инструкцию.
        if proxy_error_msg:
            return {
                'status': 'error',
                'error': error_msg,
                'scraper_config_id': scraper_config_id,
                'timestamp': timezone.now().isoformat(),
            }
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        return {
            'status': 'error',
            'error': error_msg,
            'scraper_config_id': scraper_config_id,
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def run_all_active_scrapers(self) -> Dict:
    """Задача: запуск всех активных парсеров.
    
    Returns:
        Сводные результаты
    """
    try:
        # Получаем все активные конфигурации
        active_configs = ScraperConfig.objects.filter(
            is_enabled=True,
            sync_enabled=True,
            status='active'
        ).order_by('priority')
        
        results = {
            'total_scrapers': active_configs.count(),
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'scrapers': [],
            'total_products_found': 0,
            'total_products_created': 0,
            'total_products_updated': 0,
            'started_at': timezone.now().isoformat()
        }
        
        for config in active_configs:
            try:
                # Проверяем, не запускался ли парсер недавно
                if config.last_run_at:
                    time_since_last_run = timezone.now() - config.last_run_at
                    if time_since_last_run.total_seconds() < config.sync_interval_hours * 3600:
                        logger.info(f"Пропускаем парсер {config.name} - еще рано для следующего запуска")
                        results['skipped'] += 1
                        continue
                
                # Запускаем парсер асинхронно
                task_result = run_scraper_task.delay(config.id)
                
                scraper_result = {
                    'scraper_name': config.name,
                    'task_id': task_result.id,
                    'status': 'started'
                }
                
                results['scrapers'].append(scraper_result)
                results['successful'] += 1
                
            except Exception as e:
                logger.error(f"Ошибка запуска парсера {config.name}: {e}")
                results['failed'] += 1
                results['scrapers'].append({
                    'scraper_name': config.name,
                    'status': 'error',
                    'error': str(e)
                })
        
        results['finished_at'] = timezone.now().isoformat()
        
        logger.info(f"Запущено {results['successful']} парсеров, пропущено {results['skipped']}, ошибок {results['failed']}")
        return results
        
    except Exception as e:
        error_msg = f"Ошибка при запуске всех парсеров: {e}"
        logger.error(error_msg)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        return {
            'status': 'error',
            'error': error_msg,
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def scrape_category_task(self, 
                        scraper_name: str, 
                        category_url: str,
                        max_pages: int = 5) -> Dict:
    """Задача: парсинг конкретной категории.
    
    Args:
        scraper_name: Имя парсера
        category_url: URL категории
        max_pages: Максимальное количество страниц
        
    Returns:
        Результаты парсинга категории
    """
    try:
        # Находим конфигурацию парсера
        scraper_config = ScraperConfig.objects.filter(name=scraper_name).first()
        if not scraper_config:
            return {
                'status': 'error',
                'error': f'Парсер {scraper_name} не найден'
            }
        
        # Запускаем парсинг категории
        return run_scraper_task.delay(
            scraper_config_id=scraper_config.id,
            start_url=category_url,
            max_pages=max_pages
        ).get()
        
    except Exception as e:
        error_msg = f"Ошибка при парсинге категории {category_url}: {e}"
        logger.error(error_msg)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        return {
            'status': 'error',
            'error': error_msg,
            'category_url': category_url,
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def search_products_task(self, 
                        scraper_name: str, 
                        query: str,
                        max_results: int = 50) -> Dict:
    """Задача: поиск товаров по запросу.
    
    Args:
        scraper_name: Имя парсера
        query: Поисковый запрос
        max_results: Максимальное количество результатов
        
    Returns:
        Результаты поиска
    """
    try:
        # Находим конфигурацию парсера
        scraper_config = ScraperConfig.objects.filter(name=scraper_name).first()
        if not scraper_config:
            return {
                'status': 'error',
                'error': f'Парсер {scraper_name} не найден'
            }
        
        # Формируем URL поиска (зависит от сайта)
        if 'ilacabak' in scraper_name:
            search_url = f"{scraper_config.base_url}/arama?q={query}"
        elif 'zara' in scraper_name:
            search_url = f"{scraper_config.base_url}/search?searchTerm={query}"
        else:
            search_url = f"{scraper_config.base_url}/search?q={query}"
        
        # Запускаем поиск
        return run_scraper_task.delay(
            scraper_config_id=scraper_config.id,
            start_url=search_url,
            max_products=max_results
        ).get()
        
    except Exception as e:
        error_msg = f"Ошибка при поиске товаров '{query}': {e}"
        logger.error(error_msg)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        return {
            'status': 'error',
            'error': error_msg,
            'query': query,
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def cleanup_old_sessions(self, days_to_keep: int = 30) -> Dict:
    """Задача: очистка старых сессий парсинга.
    
    Args:
        days_to_keep: Количество дней для хранения сессий
        
    Returns:
        Результаты очистки
    """
    try:
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=days_to_keep)
        
        # Удаляем старые сессии
        old_sessions = ScrapingSession.objects.filter(created_at__lt=cutoff_date)
        deleted_count = old_sessions.count()
        old_sessions.delete()
        
        # Очищаем старые логи товаров
        from .models import ScrapedProductLog
        old_logs = ScrapedProductLog.objects.filter(created_at__lt=cutoff_date)
        deleted_logs = old_logs.count()
        old_logs.delete()
        
        result = {
            'status': 'success',
            'deleted_sessions': deleted_count,
            'deleted_logs': deleted_logs,
            'cutoff_date': cutoff_date.isoformat(),
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(f"Очистка завершена: удалено {deleted_count} сессий и {deleted_logs} логов")
        return result
        
    except Exception as e:
        error_msg = f"Ошибка при очистке старых сессий: {e}"
        logger.error(error_msg)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        return {
            'status': 'error',
            'error': error_msg,
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def find_and_merge_duplicates(self) -> Dict:
    """Задача: поиск кандидатов в дубликаты товаров для ручной модерации.
    
    Returns:
        Результаты поиска кандидатов
    """
    try:
        dedup_service = DeduplicationService()
        
        # Находим кандидатов в дубликаты
        duplicates = dedup_service.find_duplicates()
        stored = dedup_service.store_candidates(duplicates)
        
        result = {
            'status': 'success',
            'duplicates_found': len(duplicates),
            'candidates_created': stored['created'],
            'candidates_updated': stored['updated'],
            'duplicates': [],
            'timestamp': timezone.now().isoformat()
        }
        
        # Сохраняем краткую сводку для логов/админки
        for duplicate_group in duplicates:
            result['duplicates'].append({
                'pair_key': duplicate_group['pair_key'],
                'score': duplicate_group['score'],
                'canonical_product_id': duplicate_group['canonical_product'].id,
                'duplicate_product_id': duplicate_group['duplicate_product'].id,
                'canonical_product_name': duplicate_group['canonical_product'].name,
                'duplicate_product_name': duplicate_group['duplicate_product'].name,
                'reasons': duplicate_group['reasons'],
                'status': 'pending_moderation',
            })
        
        logger.info(
            "Поиск кандидатов в дубликаты завершён: найдено %s, создано %s, обновлено %s",
            len(duplicates),
            stored['created'],
            stored['updated'],
        )
        _send_duplicate_candidates_notification(result)
        return result
        
    except Exception as e:
        error_msg = f"Ошибка при поиске кандидатов в дубликаты: {e}"
        logger.error(error_msg)
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        
        return {
            'status': 'error',
            'error': error_msg,
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def update_scraper_status(self, scraper_config_id: int, status: str) -> Dict:
    """Задача: обновление статуса парсера.
    
    Args:
        scraper_config_id: ID конфигурации парсера
        status: Новый статус
        
    Returns:
        Результат обновления
    """
    try:
        scraper_config = ScraperConfig.objects.get(id=scraper_config_id)
        old_status = scraper_config.status
        scraper_config.status = status
        scraper_config.save()
        
        result = {
            'status': 'success',
            'scraper_name': scraper_config.name,
            'old_status': old_status,
            'new_status': status,
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(f"Статус парсера {scraper_config.name} изменен с {old_status} на {status}")
        return result
        
    except ScraperConfig.DoesNotExist:
        error_msg = f"Конфигурация парсера с ID {scraper_config_id} не найдена"
        logger.error(error_msg)
        return {
            'status': 'error',
            'error': error_msg
        }
        
    except Exception as e:
        error_msg = f"Ошибка при обновлении статуса парсера: {e}"
        logger.error(error_msg)

        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)

        return {
            'status': 'error',
            'error': error_msg,
            'timestamp': timezone.now().isoformat()
        }


_STUB_REFRESH_BATCH_SIZE = 10


def _checkpoint_stub_refresh_product(
    *,
    site_task_id: int,
    processed_total: int,
    product_id: int,
    updated: int = 0,
    skipped: int = 0,
    errors: int = 0,
) -> None:
    """Persist one completed stub so a worker restart can resume after it."""
    SiteScraperTask.objects.filter(id=site_task_id).update(
        products_found=processed_total,
        products_updated=F("products_updated") + updated,
        products_skipped=F("products_skipped") + skipped,
        errors_count=F("errors_count") + errors,
        stub_cursor_id=product_id,
    )


def _finish_stub_refresh_session(
    session: ScrapingSession | None,
    *,
    status: str,
    found: int,
    updated: int,
    skipped: int,
    errors: int,
    message: str = "",
) -> None:
    if session is None:
        return
    session.status = status
    session.products_found = found
    session.products_updated = updated
    session.products_skipped = skipped
    session.errors_count = errors
    session.finished_at = timezone.now()
    session.error_message = message
    session.save(
        update_fields=[
            "status",
            "products_found",
            "products_updated",
            "products_skipped",
            "errors_count",
            "analog_stubs_upgraded",
            "analog_errors",
            "finished_at",
            "error_message",
        ]
    )


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_stub_refresh_task(
    self,
    site_task_id: int,
    scraper_config_id: int,
    offset: int = 0,
    after_id: int = 0,
) -> Dict:
    """Обходит заглушки короткими чанками с устойчивым ID-курсором."""
    site_task = SiteScraperTask.objects.filter(id=site_task_id).first()
    session = None
    chunk_found = chunk_updated = chunk_skipped = chunk_errors = 0
    processed_total = max(int(offset or 0), 0)
    last_processed_id = max(int(after_id or 0), 0)

    try:
        from apps.catalog.models import MedicineProduct
        from .parsers.registry import get_parser

        scraper_config = ScraperConfig.objects.get(id=scraper_config_id)

        if _is_site_task_cancelled(site_task_id):
            return {"status": "cancelled", "message": "Задача остановлена пользователем до старта чанка."}

        SiteScraperTask.objects.filter(id=site_task_id, status='pending').update(status='running')
        SiteScraperTask.objects.filter(id=site_task_id).update(task_id=self.request.id or "")
        SiteScraperTask.objects.filter(id=site_task_id, started_at__isnull=True).update(started_at=timezone.now())
        if site_task:
            site_task.refresh_from_db()

            # A late-ack redelivery may carry the original arguments after a
            # worker loss. Continue from the durable per-product checkpoint.
            if site_task.products_found > processed_total:
                processed_total = site_task.products_found
                last_processed_id = max(last_processed_id, site_task.stub_cursor_id or 0)

        effective_max = site_task.max_products if site_task else _STUB_REFRESH_BATCH_SIZE
        remaining = max(effective_max - processed_total, 0)
        if remaining == 0:
            SiteScraperTask.objects.filter(id=site_task_id).update(
                status="completed",
                finished_at=timezone.now(),
                error_message="",
            )
            return {
                "status": "completed",
                "message": "Достигнут лимит товаров",
                "offset": processed_total,
            }

        batch_size = min(_STUB_REFRESH_BATCH_SIZE, remaining)

        batch = list(
            MedicineProduct.objects
            .filter(
                external_data__is_stub=True,
                external_url__gt="",
                id__gt=last_processed_id,
            )
            .select_related('base_product')
            .order_by("id")[:batch_size]
        )

        if not batch:
            SiteScraperTask.objects.filter(id=site_task_id).update(
                status='completed',
                finished_at=timezone.now(),
                error_message="",
                log_output=(
                    "Нет заглушек с external_url для обновления."
                    if processed_total == 0
                    else f"Обновление заглушек завершено: обработано {processed_total}."
                ),
            )
            return {'status': 'completed', 'message': 'Нет заглушек'}

        parser_class = get_parser(scraper_config.parser_class)
        if not parser_class:
            raise ValueError(f"Парсер {scraper_config.parser_class} не найден")

        session = ScrapingSession.objects.create(
            scraper_config=scraper_config,
            max_pages=1,
            max_products=site_task.max_products if site_task else _STUB_REFRESH_BATCH_SIZE,
            status='running',
            task_id=self.request.id or "",
            started_at=timezone.now(),
        )

        integration_service = ScraperIntegrationService()
        with parser_class(
            base_url=scraper_config.base_url,
            timeout=scraper_config.timeout,
            max_retries=scraper_config.max_retries,
            use_proxy=scraper_config.use_proxy,
            username=scraper_config.scraper_username,
            password=scraper_config.scraper_password,
        ) as parser:
            parser.delay_range = (scraper_config.delay_min, scraper_config.delay_max)
            parser.configure_request_identity(
                user_agent=scraper_config.user_agent,
                headers=scraper_config.headers,
                cookies=scraper_config.cookies,
            )

            for stub in batch:
                if _is_site_task_cancelled(site_task_id):
                    raise ScraperTaskCancelled("Задача остановлена пользователем.")
                try:
                    scraped = parser.parse_product_detail(stub.external_url)
                    if not scraped:
                        next_processed_total = processed_total + 1
                        with transaction.atomic():
                            _checkpoint_stub_refresh_product(
                                site_task_id=site_task_id,
                                processed_total=next_processed_total,
                                product_id=stub.id,
                                skipped=1,
                            )
                        processed_total = next_processed_total
                        chunk_found += 1
                        chunk_skipped += 1
                        last_processed_id = stub.id
                    else:
                        # Product update and durable cursor move are atomic: a
                        # killed worker can neither skip the product nor count it twice.
                        next_processed_total = processed_total + 1
                        with transaction.atomic():
                            integration_service._update_existing_product(
                                session,
                                scraped,
                                stub.base_product,
                            )
                            _checkpoint_stub_refresh_product(
                                site_task_id=site_task_id,
                                processed_total=next_processed_total,
                                product_id=stub.id,
                                updated=1,
                            )
                        processed_total = next_processed_total
                        chunk_found += 1
                        chunk_updated += 1
                        last_processed_id = stub.id
                except SoftTimeLimitExceeded:
                    raise
                except Exception as exc:
                    chunk_errors += 1
                    logger.error(f"Ошибка обновления заглушки {stub.external_url}: {exc}")
                    next_processed_total = processed_total + 1
                    with transaction.atomic():
                        _checkpoint_stub_refresh_product(
                            site_task_id=site_task_id,
                            processed_total=next_processed_total,
                            product_id=stub.id,
                            errors=1,
                        )
                    processed_total = next_processed_total
                    chunk_found += 1
                    last_processed_id = stub.id

        _finish_stub_refresh_session(
            session,
            status="completed",
            found=chunk_found,
            updated=chunk_updated,
            skipped=chunk_skipped,
            errors=chunk_errors,
        )

        if site_task:
            site_task.refresh_from_db()
        has_more_stubs = MedicineProduct.objects.filter(
            external_data__is_stub=True,
            external_url__gt="",
            id__gt=last_processed_id,
        ).exists()
        should_chain = (
            (not site_task or site_task.status != "cancelled")
            and processed_total < effective_max
            and has_more_stubs
        )

        if should_chain:
            next_task = run_stub_refresh_task.apply_async(kwargs=dict(
                site_task_id=site_task_id,
                scraper_config_id=scraper_config_id,
                offset=processed_total,
                after_id=last_processed_id,
            ))
            SiteScraperTask.objects.filter(id=site_task_id).update(task_id=next_task.id)
            logger.info(
                "stub_refresh: обработано %s заглушек, продолжаем после product id=%s",
                processed_total,
                last_processed_id,
            )
        else:
            SiteScraperTask.objects.filter(id=site_task_id).update(
                status='completed',
                finished_at=timezone.now(),
                session=session,
                error_message="",
            )
            logger.info(f"stub_refresh: завершено, обработано {processed_total} заглушек")

        return {
            'status': 'success',
            'offset': processed_total,
            'batch_size': len(batch),
            'after_id': last_processed_id,
        }

    except ScraperTaskCancelled as e:
        error_msg = str(e)
        logger.info("Задача обновления заглушек %s отменена: %s", site_task_id, error_msg)
        _finish_stub_refresh_session(
            session,
            status="cancelled",
            found=chunk_found,
            updated=chunk_updated,
            skipped=chunk_skipped,
            errors=chunk_errors,
            message=error_msg,
        )
        if site_task:
            _cancel_site_task(site_task_id, error_msg)
        return {'status': 'cancelled', 'error': error_msg, 'timestamp': timezone.now().isoformat()}

    except SoftTimeLimitExceeded:
        error_msg = (
            "Чанк обновления заглушек достиг мягкого лимита времени; "
            "продолжение поставлено в очередь с последней сохранённой позиции."
        )
        _finish_stub_refresh_session(
            session,
            status="failed",
            found=chunk_found,
            updated=chunk_updated,
            skipped=chunk_skipped,
            errors=chunk_errors,
            message=error_msg,
        )
        current_task = SiteScraperTask.objects.filter(id=site_task_id).first()
        if current_task and current_task.status == "cancelled":
            return {
                "status": "cancelled",
                "message": "Задача остановлена пользователем во время чанка.",
            }

        if current_task:
            processed_total = current_task.products_found
            last_processed_id = current_task.stub_cursor_id or last_processed_id
            if processed_total >= current_task.max_products:
                SiteScraperTask.objects.filter(id=site_task_id).update(
                    status="completed",
                    finished_at=timezone.now(),
                    error_message="",
                )
                return {"status": "completed", "offset": processed_total}

        try:
            next_task = run_stub_refresh_task.apply_async(
                kwargs={
                    "site_task_id": site_task_id,
                    "scraper_config_id": scraper_config_id,
                    "offset": processed_total,
                    "after_id": last_processed_id,
                }
            )
        except Exception as enqueue_error:
            if self.request.retries < self.max_retries:
                raise self.retry(exc=enqueue_error)
            raise

        SiteScraperTask.objects.filter(id=site_task_id).update(
            status="running",
            task_id=next_task.id,
            error_message="",
            log_output=error_msg,
        )
        logger.warning(
            "stub_refresh: soft limit after %s products; continuation queued after id=%s",
            processed_total,
            last_processed_id,
        )
        return {
            "status": "continued",
            "offset": processed_total,
            "after_id": last_processed_id,
            "message": error_msg,
        }

    except ScraperConfig.DoesNotExist:
        error_msg = f"Конфигурация парсера с ID {scraper_config_id} не найдена"
        logger.error(error_msg)
        if site_task:
            SiteScraperTask.objects.filter(id=site_task_id).update(
                status='failed', error_message=error_msg, finished_at=timezone.now()
            )
        return {'status': 'error', 'error': error_msg}

    except Exception as e:
        error_msg = f"Ошибка обновления заглушек: {e}"
        logger.error(error_msg)
        _finish_stub_refresh_session(
            session,
            status="failed",
            found=chunk_found,
            updated=chunk_updated,
            skipped=chunk_skipped,
            errors=chunk_errors,
            message=error_msg,
        )
        if site_task:
            SiteScraperTask.objects.filter(id=site_task_id).update(
                status='failed', error_message=error_msg, finished_at=timezone.now()
            )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        return {'status': 'error', 'error': error_msg, 'timestamp': timezone.now().isoformat()}
