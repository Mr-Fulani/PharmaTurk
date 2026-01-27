"""Management команда для инициализации конфигурации Instagram парсера."""

from django.core.management.base import BaseCommand
from apps.scrapers.models import ScraperConfig


class Command(BaseCommand):
    help = 'Создает начальную конфигурацию для Instagram парсера'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('بسم الله الرحمن الرحيم'))
        self.stdout.write('Инициализация Instagram парсера...\n')

        # Создаем конфигурацию для Instagram парсера
        config, created = ScraperConfig.objects.get_or_create(
            name='Instagram Books Parser',
            defaults={
                'parser_class': 'instagram',
                'base_url': 'https://www.instagram.com',
                'description': 'Парсер для сбора постов из Instagram с медиа и описаниями для книг',
                'status': 'active',
                'is_enabled': True,
                'priority': 100,
                'delay_min': 5.0,
                'delay_max': 10.0,
                'timeout': 30,
                'max_retries': 3,
                'max_pages_per_run': 50,
                'max_products_per_run': 100,
                'sync_enabled': False,  # Отключено по умолчанию
                'sync_interval_hours': 24,
                'use_proxy': False,
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'✓ Создана конфигурация: {config.name} (ID: {config.id})')
            )
            self.stdout.write('\nДля запуска парсера используйте:')
            self.stdout.write(
                f'  python manage.py run_instagram_scraper --config-id {config.id} --max-posts 50'
            )
            self.stdout.write('\nИли напрямую:')
            self.stdout.write(
                '  python manage.py run_instagram_scraper --username <profile> --max-posts 30'
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'⚠ Конфигурация уже существует: {config.name} (ID: {config.id})')
            )

        self.stdout.write('\n' + self.style.SUCCESS('✓ Инициализация завершена'))
        self.stdout.write('\nСледующие шаги:')
        self.stdout.write('1. Создайте категорию "books" в Django Admin (Catalog → Categories)')
        self.stdout.write('2. Запустите парсер с --dry-run для тестирования')
        self.stdout.write('3. Установите цены для спарсенных товаров через админку')
        self.stdout.write('\nПодробная документация: INSTAGRAM_PARSER_GUIDE.md')
