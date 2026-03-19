"""Django команда для инициализации парсеров."""

from django.core.management.base import BaseCommand
from apps.scrapers.models import ScraperConfig, CategoryMapping
from apps.catalog.models import Category

class Command(BaseCommand):
    """Команда для создания начальных конфигураций парсеров."""
    
    help = 'Создает начальные конфигурации парсеров'
    
    def handle(self, *args, **options):
        """Обработчик команды."""
        
        # ... (ilacabak and zara configs remain unchanged) ...

        # Создаем конфигурацию для umma-land.com
        ummaland_config, created = ScraperConfig.objects.get_or_create(
            name='ummaland',
            defaults={
                'parser_class': 'ummaland',
                'base_url': 'https://umma-land.com',
                'description': 'Парсер для книг и исламских товаров с сайта umma-land.com',
                'status': 'active',
                'is_enabled': True,
                'priority': 30,
                'delay_min': 1.0,
                'delay_max': 3.0,
                'timeout': 30,
                'max_retries': 3,
                'max_pages_per_run': 1000,
                'max_products_per_run': 1000,
                'sync_enabled': False,
                'sync_interval_hours': 24,
                'use_proxy': False,
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS('Создана конфигурация парсера ummaland')
            )
            
            # Настройка маппинга категорий
            try:
                # Пытаемся найти внутреннюю категорию "Книги"
                internal_category = Category.objects.filter(slug='books').first()
                
                if not internal_category:
                    internal_category = Category.objects.filter(name__iexact='Книги').first()
                
                if internal_category:
                    CategoryMapping.objects.get_or_create(
                        scraper_config=ummaland_config,
                        external_category_name='Книги',
                        defaults={
                            'internal_category': internal_category,
                            'external_category_url': 'https://umma-land.com/product-category/books',
                            'external_category_id': '16',
                            'is_active': True
                        }
                    )
                    self.stdout.write(self.style.SUCCESS('Создан маппинг категории Книги'))
                else:
                    self.stdout.write(self.style.WARNING('Внутренняя категория Книги не найдена, маппинг не создан'))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Ошибка при создании маппинга: {e}'))
                
        else:
            self.stdout.write(
                self.style.WARNING('Конфигурация парсера ummaland уже существует')
            )
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
        
        # Создаем конфигурацию для umma-land.com
        ummaland_config, created = ScraperConfig.objects.get_or_create(
            name='ummaland',
            defaults={
                'parser_class': 'ummaland',
                'base_url': 'https://umma-land.com',
                'description': 'Парсер для книг и исламских товаров с сайта umma-land.com',
                'status': 'active',
                'is_enabled': True,
                'priority': 30,
                'delay_min': 1.0,
                'delay_max': 3.0,
                'timeout': 30,
                'max_retries': 3,
                'max_pages_per_run': 1000,
                'max_products_per_run': 1000,
                'sync_enabled': False,
                'sync_interval_hours': 24,
                'use_proxy': False,
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS('Создана конфигурация парсера ummaland')
            )
            
            # Настройка маппинга категорий
            try:
                # Пытаемся найти внутреннюю категорию "Книги"
                internal_category = Category.objects.filter(slug='books').first()
                
                if not internal_category:
                    internal_category = Category.objects.filter(name__iexact='Книги').first()
                
                if internal_category:
                    CategoryMapping.objects.get_or_create(
                        scraper_config=ummaland_config,
                        external_category_name='Книги',
                        defaults={
                            'internal_category': internal_category,
                            'external_category_url': 'https://umma-land.com/product-category/books',
                            'external_category_id': '16',
                            'is_active': True
                        }
                    )
                    self.stdout.write(self.style.SUCCESS('Создан маппинг категории Книги'))
                else:
                    self.stdout.write(self.style.WARNING('Внутренняя категория Книги не найдена, маппинг не создан'))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Ошибка при создании маппинга: {e}'))
                
        else:
            self.stdout.write(
                self.style.WARNING('Конфигурация парсера ummaland уже существует')
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
