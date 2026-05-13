"""Celery задачи для парсинга сайтов."""

import logging
from typing import Dict, List, Optional
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db.models import F
from django.utils import timezone

from .models import ScraperConfig, ScrapingSession, SiteScraperTask
from .services import ScraperIntegrationService, DeduplicationService

logger = logging.getLogger(__name__)


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
            # Первый чанк: переводим в 'running'. Последующие: already running, условие не сработает.
            SiteScraperTask.objects.filter(id=site_task.id, status='pending').update(
                status='running'
            )
            SiteScraperTask.objects.filter(id=site_task.id, started_at__isnull=True).update(
                started_at=timezone.now()
            )
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
            products_this_chunk = session.products_found
            new_total = total_scraped + products_this_chunk
            chunk_pages = max_pages or scraper_config.max_pages_per_run
            effective_max = site_task.max_products

            # Продолжаем цепочку если: нашли хоть что-то И не достигли лимита
            should_chain = products_this_chunk > 0 and new_total < effective_max

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
                SiteScraperTask.objects.filter(id=site_task.id).update(**common_updates)
                run_scraper_task.apply_async(kwargs=dict(
                    scraper_config_id=scraper_config_id,
                    start_url=start_url,
                    max_pages=max_pages,
                    max_products=max_products,
                    max_images_per_product=max_images_per_product,
                    site_task_id=site_task_id,
                    start_page=start_page + chunk_pages,
                    total_scraped=new_total,
                ))
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


_STUB_REFRESH_BATCH_SIZE = 50


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_stub_refresh_task(self, site_task_id: int, scraper_config_id: int, offset: int = 0) -> Dict:
    """Обходит товары-заглушки и парсит каждую по URL через основной парсер."""
    site_task = SiteScraperTask.objects.filter(id=site_task_id).first()

    try:
        from apps.catalog.models import MedicineProduct
        from .parsers.registry import get_parser

        scraper_config = ScraperConfig.objects.get(id=scraper_config_id)

        SiteScraperTask.objects.filter(id=site_task_id, status='pending').update(status='running')
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
        should_chain = len(batch) == _STUB_REFRESH_BATCH_SIZE and new_offset < effective_max

        if should_chain:
            run_stub_refresh_task.apply_async(kwargs=dict(
                site_task_id=site_task_id,
                scraper_config_id=scraper_config_id,
                offset=new_offset,
            ))
            logger.info(f"stub_refresh: обработано {new_offset} заглушек, продолжаем со смещения {new_offset}")
        else:
            SiteScraperTask.objects.filter(id=site_task_id).update(
                status='completed',
                finished_at=timezone.now(),
                session=session,
            )
            logger.info(f"stub_refresh: завершено, обработано {new_offset} заглушек")

        return {'status': 'success', 'offset': offset, 'batch_size': len(batch)}

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
