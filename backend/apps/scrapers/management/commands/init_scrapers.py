"""Django команда для инициализации парсеров."""

from django.core.management.base import BaseCommand
from apps.scrapers.models import ScraperConfig


class Command(BaseCommand):
    """Команда для создания начальных конфигураций парсеров."""
    
    help = 'Создает начальные конфигурации парсеров'
    
    def handle(self, *args, **options):
        """Обработчик команды."""
        
        # Создаем конфигурацию для ilacabak.com
        ilacabak_config, created = ScraperConfig.objects.get_or_create(
            name='ilacabak',
            defaults={
                'parser_class': 'ilacabak',
                'base_url': 'https://ilacabak.com',
                'description': 'Парсер для турецких медикаментов и БАДов с сайта ilacabak.com',
                'status': 'active',
                'is_enabled': True,
                'priority': 10,
                'delay_min': 2.0,
                'delay_max': 4.0,
                'timeout': 30,
                'max_retries': 3,
                'max_pages_per_run': 5,
                'max_products_per_run': 100,
                'sync_enabled': True,
                'sync_interval_hours': 24,
                'use_proxy': False,
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS('Создана конфигурация парсера ilacabak')
            )
        else:
            self.stdout.write(
                self.style.WARNING('Конфигурация парсера ilacabak уже существует')
            )
        
        # Создаем конфигурацию для zara.com
        zara_config, created = ScraperConfig.objects.get_or_create(
            name='zara',
            defaults={
                'parser_class': 'zara',
                'base_url': 'https://www.zara.com',
                'description': 'Парсер для одежды и аксессуаров с сайта zara.com',
                'status': 'active',
                'is_enabled': True,
                'priority': 20,
                'delay_min': 3.0,
                'delay_max': 5.0,
                'timeout': 45,
                'max_retries': 3,
                'max_pages_per_run': 3,
                'max_products_per_run': 50,
                'sync_enabled': True,
                'sync_interval_hours': 48,
                'use_proxy': False,
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS('Создана конфигурация парсера zara')
            )
        else:
            self.stdout.write(
                self.style.WARNING('Конфигурация парсера zara уже существует')
            )
        
        # Показываем статистику
        total_configs = ScraperConfig.objects.count()
        active_configs = ScraperConfig.objects.filter(is_enabled=True).count()
        
        self.stdout.write('')
        self.stdout.write(f'Всего конфигураций парсеров: {total_configs}')
        self.stdout.write(f'Активных конфигураций: {active_configs}')
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS('Инициализация парсеров завершена!')
        )
