"""Команда для создания дополнительных тестовых медикаментов."""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from decimal import Decimal
from apps.catalog.models import Category, Brand, Product


class Command(BaseCommand):
    help = 'Создает дополнительные тестовые медикаменты'

    def handle(self, *args, **options):
        self.stdout.write('Создание дополнительных медикаментов...')
        
        # Получаем или создаем бренды
        brands = self._get_or_create_brands()
        
        # Создаем медикаменты без категории (как показано в старом коде)
        self._create_uncategorized_medicines(brands)
        
        self.stdout.write(
            self.style.SUCCESS('Дополнительные медикаменты успешно созданы!')
        )

    def _get_or_create_brands(self):
        """Получает или создает бренды для медикаментов."""
        brands_data = [
            'Bayer', 'Pfizer', 'Novartis', 'Roche', 'Merck', 
            'Sanofi', 'AstraZeneca', 'Johnson & Johnson', 
            'GlaxoSmithKline', 'Eli Lilly'
        ]
        
        brands = {}
        for name in brands_data:
            slug = slugify(name)
            brand, created = Brand.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'is_active': True}
            )
            brands[name] = brand
        
        return brands

    def _create_uncategorized_medicines(self, brands):
        """Создает медикаменты без категории."""
        medicines_data = [
            {
                'name': 'Анальгин 500мг',
                'description': 'Метамизол натрия для снятия боли и жара',
                'price': Decimal('45.00'),
                'brand': brands['Bayer'],
                'sku': 'ANALG-500'
            },
            {
                'name': 'Но-шпа 40мг',
                'description': 'Спазмолитик для снятия спазмов гладкой мускулатуры',
                'price': Decimal('180.00'),
                'brand': brands['Sanofi'],
                'sku': 'NOSPA-40'
            },
            {
                'name': 'Супрастин 25мг',
                'description': 'Антигистаминный препарат при аллергии',
                'price': Decimal('120.00'),
                'brand': brands['AstraZeneca'],
                'sku': 'SUPR-25'
            },
            {
                'name': 'Лоперамид 2мг',
                'description': 'Противодиарейный препарат',
                'price': Decimal('85.00'),
                'brand': brands['Johnson & Johnson'],
                'sku': 'LOPER-2'
            },
            {
                'name': 'Фестал',
                'description': 'Ферментный препарат для улучшения пищеварения',
                'price': Decimal('240.00'),
                'brand': brands['Sanofi'],
                'sku': 'FESTAL'
            },
            {
                'name': 'Кетанов 10мг',
                'description': 'Обезболивающий препарат при сильных болях',
                'price': Decimal('95.00'),
                'brand': brands['Pfizer'],
                'sku': 'KETAN-10'
            },
            {
                'name': 'Мукалтин',
                'description': 'Отхаркивающее средство растительного происхождения',
                'price': Decimal('35.00'),
                'brand': brands['Novartis'],
                'sku': 'MUKAL'
            },
            {
                'name': 'Валидол',
                'description': 'Седативное средство при стрессе и тревоге',
                'price': Decimal('25.00'),
                'brand': brands['Merck'],
                'sku': 'VALID'
            },
            {
                'name': 'Корвалол',
                'description': 'Седативное и спазмолитическое средство',
                'price': Decimal('65.00'),
                'brand': brands['GlaxoSmithKline'],
                'sku': 'KORVAL'
            },
            {
                'name': 'Фуразолидон 50мг',
                'description': 'Антимикробный препарат широкого спектра',
                'price': Decimal('55.00'),
                'brand': brands['Eli Lilly'],
                'sku': 'FURAZ-50'
            }
        ]
        
        created_count = 0
        for data in medicines_data:
            # Создаем качественный slug из названия
            base_slug = slugify(data['name'])
            slug = f"{base_slug}-{data['sku'].lower()}"
            
            product, created = Product.objects.get_or_create(
                slug=slug,
                defaults={
                    'name': data['name'],
                    'description': data['description'],
                    'price': data['price'],
                    'currency': 'RUB',
                    'brand': data['brand'],
                    'sku': data['sku'],
                    'category': None,  # Оставляем без категории
                    'is_active': True,
                    'is_available': True,
                    'stock_quantity': 50,
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(f'Создан медикамент: {product.name} - {product.price} {product.currency}')
            else:
                self.stdout.write(f'Медикамент уже существует: {product.name}')
        
        self.stdout.write(f'Создано новых медикаментов: {created_count}')
