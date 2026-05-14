"""Celery задачи для парсинга сайтов."""

import logging
from typing import Dict, List, Optional

import requests
from celery import shared_task, current_app
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db.models import F
from django.utils import timezone

from .models import ScraperConfig, ScrapingSession, SiteScraperTask
from .services import ScraperIntegrationService, DeduplicationService, ScraperTaskCancelled

logger = logging.getLogger(__name__)


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
            logger.warning("Не удалось отправить Telegram-уведомление о дубликатах: %s", response.text)
            return False
        logger.info("Telegram-уведомление о кандидатах в дубликаты отправлено")
        return True
    except requests.RequestException as exc:
        logger.warning("Ошибка отправки Telegram-уведомления о дубликатах: %s", exc)
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


def revoke_site_scraper_task(task: SiteScraperTask, *, terminate: bool = True) -> bool:
    """Отзывает текущую Celery-задачу для SiteScraperTask, если task_id известен."""
    if not task.task_id:
        return False
    current_app.control.revoke(task.task_id, terminate=terminate, signal="SIGTERM")
    return True


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_scraper_task(self,
                    scraper_config_id: int,
                    start_url: Optional[str] = None,
                    max_pages: Optional[int] = None,
                    max_products: Optional[int] = None,
                    max_images_per_product: Optional[int] = None,
                    site_task_id: Optional[int] = None,
                    start_page: int = 1,
                    total_scraped: int = 0) -> Dict:
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
        
        log_lines = [
            f"Парсер: {scraper_config.name}",
            f"URL: {start_url or scraper_config.base_url}",
            f"Страница старт: {start_page}",
            f"Страниц в чанке: {max_pages or scraper_config.max_pages_per_run}",
            f"Макс. товаров всего: {max_products or scraper_config.max_products_per_run}",
            f"Макс. медиа: {max_images_per_product or scraper_config.max_images_per_product}",
            f"Старт: {timezone.now().isoformat()}"
        ]

        target_category = None
        if site_task:
            if _is_site_task_cancelled(site_task.id):
                return {
                    "status": "cancelled",
                    "message": "Задача остановлена пользователем до старта чанка.",
                    "scraper_name": scraper_config.name,
                }
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
            max_pages=max_pages,
            max_products=max_products,
            max_images_per_product=max_images_per_product,
            target_category=target_category,
            start_page=start_page,
            site_task_id=site_task_id,
            total_scraped=total_scraped,
            celery_task_id=self.request.id,
        )

        result = {
            'status': 'success',
            'scraper_name': scraper_config.name,
            'session_id': session.id,
            'start_page': start_page,
            'products_found': session.products_found,
            'products_created': session.products_created,
            'products_updated': session.products_updated,
            'products_skipped': session.products_skipped,
            'pages_processed': session.pages_processed,
            'errors_count': session.errors_count,
            'duration': str(session.duration) if session.duration else None,
            'timestamp': timezone.now().isoformat()
        }

        log_lines.extend([
            f"Найдено товаров (чанк): {session.products_found}",
            f"Создано: {session.products_created}",
            f"Обновлено: {session.products_updated}",
            f"Пропущено: {session.products_skipped}",
            f"Обработано страниц: {session.pages_processed}",
            f"Ошибок: {session.errors_count}",
            f"Финиш: {timezone.now().isoformat()}"
        ])

        if site_task:
            site_task.refresh_from_db()
            if site_task.status == "cancelled":
                return {
                    **result,
                    "status": "cancelled",
                    "message": "Задача остановлена пользователем.",
                }
            products_this_chunk = session.products_found
            new_total = total_scraped + products_this_chunk
            chunk_pages = max_pages or scraper_config.max_pages_per_run
            effective_max = site_task.max_products

            # Продолжаем цепочку если: нашли хоть что-то И не достигли лимита
            should_chain = (
                site_task.status != "cancelled"
                and products_this_chunk > 0
                and new_total < effective_max
            )

            common_updates = dict(
                session=session,
                products_found=new_total,  # абсолютное значение, не F() — midway уже ставит абсолютные
                products_created=F('products_created') + session.products_created,
                products_updated=F('products_updated') + session.products_updated,
                products_skipped=F('products_skipped') + session.products_skipped,
                pages_processed=F('pages_processed') + session.pages_processed,
                errors_count=F('errors_count') + session.errors_count,
                log_output="\n".join(log_lines),
            )

            if should_chain:
                next_task = run_scraper_task.apply_async(kwargs=dict(
                    scraper_config_id=scraper_config_id,
                    start_url=start_url,
                    max_pages=max_pages,
                    max_products=max_products,
                    max_images_per_product=max_images_per_product,
                    site_task_id=site_task_id,
                    start_page=start_page + chunk_pages,
                    total_scraped=new_total,
                ))
                SiteScraperTask.objects.filter(id=site_task.id).update(
                    **common_updates,
                    task_id=next_task.id,
                )
                logger.info(
                    f"Парсер {scraper_config.name}: чанк стр.{start_page} готов "
                    f"({products_this_chunk} товаров, всего {new_total}/{effective_max}). "
                    f"Следующий чанк со стр.{start_page + chunk_pages}"
                )
            else:
                SiteScraperTask.objects.filter(id=site_task.id).update(
                    **common_updates,
                    status='completed',
                    finished_at=timezone.now(),
                )
                logger.info(
                    f"Парсер {scraper_config.name} завершён: "
                    f"всего {new_total} товаров за {start_page + chunk_pages - 1} страниц"
                )
        else:
            logger.info(f"Парсер {scraper_config.name} завершен успешно: {session.products_found} товаров найдено")

        return result

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

    except Exception as e:
        error_msg = f"Ошибка в задаче парсинга: {e}"
        logger.error(error_msg)
        if site_task:
            SiteScraperTask.objects.filter(id=site_task.id).update(
                status='failed',
                error_message=error_msg,
                log_output=error_msg,
                finished_at=timezone.now()
            )
        
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


_STUB_REFRESH_BATCH_SIZE = 50


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_stub_refresh_task(self, site_task_id: int, scraper_config_id: int, offset: int = 0) -> Dict:
    """Обходит товары-заглушки и парсит каждую по URL через основной парсер."""
    site_task = SiteScraperTask.objects.filter(id=site_task_id).first()

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

        batch = list(
            MedicineProduct.objects
            .filter(external_data__is_stub=True, external_url__gt='')
            .select_related('base_product')
            .order_by('id')[offset:offset + _STUB_REFRESH_BATCH_SIZE]
        )

        if not batch:
            SiteScraperTask.objects.filter(id=site_task_id).update(
                status='completed',
                finished_at=timezone.now(),
                log_output='Нет заглушек с external_url для обновления.',
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
        chunk_updated = chunk_skipped = chunk_errors = 0

        with parser_class(
            base_url=scraper_config.base_url,
            timeout=scraper_config.timeout,
            max_retries=scraper_config.max_retries,
            use_proxy=scraper_config.use_proxy,
            username=scraper_config.scraper_username,
            password=scraper_config.scraper_password,
        ) as parser:
            parser.delay_range = (scraper_config.delay_min, scraper_config.delay_max)
            if scraper_config.user_agent:
                parser.user_agent = scraper_config.user_agent

            for i, stub in enumerate(batch):
                if _is_site_task_cancelled(site_task_id):
                    raise ScraperTaskCancelled("Задача остановлена пользователем.")
                try:
                    scraped = parser.parse_product_detail(stub.external_url)
                    if not scraped:
                        chunk_skipped += 1
                    else:
                        integration_service._update_existing_product(session, scraped, stub.base_product)
                        chunk_updated += 1
                except Exception as exc:
                    chunk_errors += 1
                    logger.error(f"Ошибка обновления заглушки {stub.external_url}: {exc}")

                if (i + 1) % 10 == 0:
                    SiteScraperTask.objects.filter(id=site_task_id).update(
                        products_found=offset + i + 1,
                        products_updated=F('products_updated') + chunk_updated,
                        products_skipped=F('products_skipped') + chunk_skipped,
                        errors_count=F('errors_count') + chunk_errors,
                    )
                    chunk_updated = chunk_skipped = chunk_errors = 0

        new_offset = offset + len(batch)
        SiteScraperTask.objects.filter(id=site_task_id).update(
            products_found=new_offset,
            products_updated=F('products_updated') + chunk_updated,
            products_skipped=F('products_skipped') + chunk_skipped,
            errors_count=F('errors_count') + chunk_errors,
        )

        session.status = 'completed'
        session.finished_at = timezone.now()
        session.save(update_fields=['status', 'finished_at'])

        effective_max = site_task.max_products if site_task else new_offset
        if site_task:
            site_task.refresh_from_db()
        should_chain = (
            (not site_task or site_task.status != "cancelled")
            and len(batch) == _STUB_REFRESH_BATCH_SIZE
            and new_offset < effective_max
        )

        if should_chain:
            next_task = run_stub_refresh_task.apply_async(kwargs=dict(
                site_task_id=site_task_id,
                scraper_config_id=scraper_config_id,
                offset=new_offset,
            ))
            SiteScraperTask.objects.filter(id=site_task_id).update(task_id=next_task.id)
            logger.info(f"stub_refresh: обработано {new_offset} заглушек, продолжаем со смещения {new_offset}")
        else:
            SiteScraperTask.objects.filter(id=site_task_id).update(
                status='completed',
                finished_at=timezone.now(),
                session=session,
            )
            logger.info(f"stub_refresh: завершено, обработано {new_offset} заглушек")

        return {'status': 'success', 'offset': offset, 'batch_size': len(batch)}

    except ScraperTaskCancelled as e:
        error_msg = str(e)
        logger.info("Задача обновления заглушек %s отменена: %s", site_task_id, error_msg)
        if site_task:
            _cancel_site_task(site_task_id, error_msg)
        return {'status': 'cancelled', 'error': error_msg, 'timestamp': timezone.now().isoformat()}

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
        if site_task:
            SiteScraperTask.objects.filter(id=site_task_id).update(
                status='failed', error_message=error_msg, finished_at=timezone.now()
            )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        return {'status': 'error', 'error': error_msg, 'timestamp': timezone.now().isoformat()}
