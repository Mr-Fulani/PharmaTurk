"""Django команда для запуска парсеров."""

import sys
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.scrapers.models import ScraperConfig
from apps.scrapers.services import ScraperIntegrationService
from apps.scrapers.tasks import run_scraper_task


class Command(BaseCommand):
    """Команда для запуска парсеров."""
    
    help = 'Запускает парсер сайта'
    
    def add_arguments(self, parser):
        """Добавляет аргументы команды."""
        parser.add_argument(
            'scraper_name',
            nargs='?',
            type=str,
            help='Имя парсера для запуска'
        )
        parser.add_argument(
            '--url',
            type=str,
            help='Начальный URL для парсинга (необязательно)'
        )
        parser.add_argument(
            '--max-pages',
            type=int,
            help='Максимальное количество страниц для парсинга'
        )
        parser.add_argument(
            '--max-products',
            type=int,
            help='Максимальное количество товаров для парсинга'
        )
        parser.add_argument(
            '--async',
            action='store_true',
            help='Запустить асинхронно через Celery'
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='Показать список доступных парсеров'
        )
        parser.add_argument(
            '--status',
            type=str,
            choices=['active', 'inactive', 'error', 'maintenance'],
            help='Показать парсеры с определенным статусом'
        )
    
    def handle(self, *args, **options):
        """Обработчик команды."""
        # Показать список парсеров
        if options['list']:
            self.show_scrapers_list(options.get('status'))
            return
        
        scraper_name = options.get('scraper_name')
        
        if not scraper_name and not options['list']:
            raise CommandError('Укажите имя парсера или используйте --list')
        
        try:
            # Находим конфигурацию парсера
            scraper_config = ScraperConfig.objects.get(name=scraper_name)
            
            if not scraper_config.is_enabled:
                raise CommandError(f'Парсер "{scraper_name}" отключен')
            
            # Запускаем парсер
            if options['async']:
                self.run_async(scraper_config, options)
            else:
                self.run_sync(scraper_config, options)
                
        except ScraperConfig.DoesNotExist:
            raise CommandError(f'Парсер "{scraper_name}" не найден')
        except Exception as e:
            raise CommandError(f'Ошибка при запуске парсера: {e}')
    
    def show_scrapers_list(self, status_filter=None):
        """Показывает список доступных парсеров."""
        queryset = ScraperConfig.objects.all()
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if not queryset.exists():
            self.stdout.write(
                self.style.WARNING('Парсеры не найдены')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS('Доступные парсеры:')
        )
        self.stdout.write('')
        
        # Заголовок таблицы
        self.stdout.write(
            f"{'Имя':<20} {'Статус':<12} {'URL':<30} {'Последний запуск':<20}"
        )
        self.stdout.write('-' * 82)
        
        for config in queryset.order_by('priority', 'name'):
            last_run = 'Никогда'
            if config.last_run_at:
                delta = timezone.now() - config.last_run_at
                if delta.days > 0:
                    last_run = f'{delta.days} дн. назад'
                elif delta.seconds > 3600:
                    hours = delta.seconds // 3600
                    last_run = f'{hours} ч. назад'
                else:
                    minutes = delta.seconds // 60
                    last_run = f'{minutes} мин. назад'
            
            status_color = {
                'active': self.style.SUCCESS,
                'inactive': self.style.WARNING,
                'error': self.style.ERROR,
                'maintenance': self.style.NOTICE
            }.get(config.status, self.style.SUCCESS)
            
            self.stdout.write(
                f"{config.name:<20} "
                f"{status_color(config.get_status_display()):<20} "
                f"{config.base_url[:28]:<30} "
                f"{last_run:<20}"
            )
    
    def run_async(self, scraper_config, options):
        """Запускает парсер асинхронно через Celery."""
        self.stdout.write(
            f'Запуск парсера "{scraper_config.name}" в фоне...'
        )
        
        # Запускаем задачу Celery
        task = run_scraper_task.delay(
            scraper_config_id=scraper_config.id,
            start_url=options.get('url'),
            max_pages=options.get('max_pages'),
            max_products=options.get('max_products')
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Парсер запущен! ID задачи: {task.id}'
            )
        )
        self.stdout.write(
            f'Отслеживать прогресс можно в админке или логах Celery'
        )
    
    def run_sync(self, scraper_config, options):
        """Запускает парсер синхронно."""
        self.stdout.write(
            f'Запуск парсера "{scraper_config.name}"...'
        )
        
        # Запускаем парсер напрямую
        integration_service = ScraperIntegrationService()
        
        try:
            session = integration_service.run_scraper(
                scraper_config=scraper_config,
                start_url=options.get('url'),
                max_pages=options.get('max_pages'),
                max_products=options.get('max_products')
            )
            
            # Показываем результаты
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('Парсинг завершен!'))
            self.stdout.write('')
            self.stdout.write(f'Статус: {session.get_status_display()}')
            self.stdout.write(f'Найдено товаров: {session.products_found}')
            self.stdout.write(f'Создано товаров: {session.products_created}')
            self.stdout.write(f'Обновлено товаров: {session.products_updated}')
            self.stdout.write(f'Пропущено товаров: {session.products_skipped}')
            self.stdout.write(f'Обработано страниц: {session.pages_processed}')
            self.stdout.write(f'Ошибок: {session.errors_count}')
            
            if session.duration:
                self.stdout.write(f'Время выполнения: {session.duration}')
            
            if session.error_message:
                self.stdout.write(
                    self.style.ERROR(f'Ошибка: {session.error_message}')
                )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Ошибка при запуске парсера: {e}')
            )
            sys.exit(1)
