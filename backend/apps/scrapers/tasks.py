"""Celery задачи для парсинга сайтов."""

import logging
from typing import Dict, List, Optional
from celery import shared_task
from django.utils import timezone

from .models import ScraperConfig, ScrapingSession
from .services import ScraperIntegrationService, DeduplicationService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_scraper_task(self, 
                    scraper_config_id: int,
                    start_url: Optional[str] = None,
                    max_pages: Optional[int] = None,
                    max_products: Optional[int] = None) -> Dict:
    """Задача: запуск парсера.
    
    Args:
        scraper_config_id: ID конфигурации парсера
        start_url: Начальный URL
        max_pages: Максимальное количество страниц
        max_products: Максимальное количество товаров
        
    Returns:
        Результаты парсинга
    """
    try:
        # Получаем конфигурацию
        scraper_config = ScraperConfig.objects.get(id=scraper_config_id)
        
        if not scraper_config.is_enabled:
            return {
                'status': 'skipped',
                'message': 'Парсер отключен',
                'scraper_name': scraper_config.name
            }
        
        # Проверяем статус парсера
        if scraper_config.status == 'maintenance':
            return {
                'status': 'skipped',
                'message': 'Парсер на обслуживании',
                'scraper_name': scraper_config.name
            }
        
        # Запускаем парсер
        integration_service = ScraperIntegrationService()
        session = integration_service.run_scraper(
            scraper_config=scraper_config,
            start_url=start_url,
            max_pages=max_pages,
            max_products=max_products
        )
        
        result = {
            'status': 'success',
            'scraper_name': scraper_config.name,
            'session_id': session.id,
            'products_found': session.products_found,
            'products_created': session.products_created,
            'products_updated': session.products_updated,
            'products_skipped': session.products_skipped,
            'pages_processed': session.pages_processed,
            'errors_count': session.errors_count,
            'duration': str(session.duration) if session.duration else None,
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(f"Парсер {scraper_config.name} завершен успешно: {session.products_found} товаров найдено")
        return result
        
    except ScraperConfig.DoesNotExist:
        error_msg = f"Конфигурация парсера с ID {scraper_config_id} не найдена"
        logger.error(error_msg)
        return {
            'status': 'error',
            'error': error_msg,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        error_msg = f"Ошибка в задаче парсинга: {e}"
        logger.error(error_msg)
        
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
    """Задача: поиск и объединение дубликатов товаров.
    
    Returns:
        Результаты дедупликации
    """
    try:
        dedup_service = DeduplicationService()
        
        # Находим дубликаты
        duplicates = dedup_service.find_duplicates()
        
        result = {
            'status': 'success',
            'duplicates_found': len(duplicates),
            'merged_count': 0,
            'errors_count': 0,
            'duplicates': [],
            'timestamp': timezone.now().isoformat()
        }
        
        # Обрабатываем каждую группу дубликатов
        for duplicate_group in duplicates:
            try:
                api_products = duplicate_group['api_products']
                scraped_products = duplicate_group['scraped_products']
                
                if api_products and scraped_products:
                    # Берем первый API товар как основной
                    main_api_product_id = api_products[0]['id']
                    scraped_product_ids = [p['id'] for p in scraped_products]
                    
                    # Объединяем дубликаты
                    success = dedup_service.merge_duplicates(main_api_product_id, scraped_product_ids)
                    
                    if success:
                        result['merged_count'] += 1
                        result['duplicates'].append({
                            'name': duplicate_group['name'],
                            'main_product_id': main_api_product_id,
                            'merged_ids': scraped_product_ids,
                            'status': 'merged'
                        })
                    else:
                        result['errors_count'] += 1
                        result['duplicates'].append({
                            'name': duplicate_group['name'],
                            'status': 'error'
                        })
                        
            except Exception as e:
                logger.error(f"Ошибка при объединении дубликатов для {duplicate_group['name']}: {e}")
                result['errors_count'] += 1
        
        logger.info(f"Дедупликация завершена: найдено {len(duplicates)} групп, объединено {result['merged_count']}")
        return result
        
    except Exception as e:
        error_msg = f"Ошибка при дедупликации: {e}"
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
