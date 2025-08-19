"""Команда для создания тестовых данных."""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from apps.catalog.models import (
    ClothingCategory, ClothingProduct, ShoeCategory, ShoeProduct,
    ElectronicsCategory, ElectronicsProduct, Brand
)


class Command(BaseCommand):
    help = 'Создает тестовые данные для одежды, обуви и электроники'

    def handle(self, *args, **options):
        self.stdout.write('Создание тестовых данных...')
        
        # Создаем бренды
        brands = self._create_brands()
        
        # Создаем категории и товары одежды
        self._create_clothing_data(brands)
        
        # Создаем категории и товары обуви
        self._create_shoes_data(brands)
        
        # Создаем категории и товары электроники
        self._create_electronics_data(brands)
        
        self.stdout.write(
            self.style.SUCCESS('Тестовые данные успешно созданы!')
        )

    def _create_brands(self):
        """Создает бренды."""
        brands_data = [
            {'name': 'Zara', 'description': 'Испанский бренд одежды'},
            {'name': 'Nike', 'description': 'Американский спортивный бренд'},
            {'name': 'Apple', 'description': 'Американская технологическая компания'},
            {'name': 'Samsung', 'description': 'Южнокорейская технологическая компания'},
        ]
        
        brands = {}
        for brand_data in brands_data:
            brand, created = Brand.objects.get_or_create(
                name=brand_data['name'],
                defaults={
                    'slug': slugify(brand_data['name']),
                    'description': brand_data['description'],
                    'is_active': True
                }
            )
            brands[brand_data['name']] = brand
            if created:
                self.stdout.write(f'Создан бренд: {brand.name}')
        
        return brands

    def _create_clothing_data(self, brands):
        """Создает данные для одежды."""
        # Создаем категории одежды
        women_clothing = ClothingCategory.objects.create(
            name='Женская одежда',
            slug='women-clothing',
            gender='women',
            clothing_type='general',
            is_active=True,
            sort_order=1
        )
        
        dresses = ClothingCategory.objects.create(
            name='Платья',
            slug='dresses',
            gender='women',
            clothing_type='dresses',
            parent=women_clothing,
            is_active=True,
            sort_order=1
        )
        
        blouses = ClothingCategory.objects.create(
            name='Блузки',
            slug='blouses',
            gender='women',
            clothing_type='blouses',
            parent=women_clothing,
            is_active=True,
            sort_order=2
        )
        
        # Создаем товары одежды
        clothing_products = [
            {
                'name': 'Платье Zara Test',
                'category': dresses,
                'brand': brands['Zara'],
                'price': 2999.00,
                'size': 'M',
                'color': 'Черный',
                'material': 'Полиэстер',
                'season': 'Лето',
                'description': 'Элегантное платье от Zara'
            },
            {
                'name': 'Блузка Zara',
                'category': blouses,
                'brand': brands['Zara'],
                'price': 1999.00,
                'size': 'S',
                'color': 'Белый',
                'material': 'Хлопок',
                'season': 'Лето',
                'description': 'Классическая блузка'
            },
            {
                'name': 'Спортивный костюм Nike',
                'category': women_clothing,
                'brand': brands['Nike'],
                'price': 5999.00,
                'size': 'L',
                'color': 'Серый',
                'material': 'Полиэстер',
                'season': 'Демисезон',
                'description': 'Удобный спортивный костюм'
            }
        ]
        
        for product_data in clothing_products:
            product, created = ClothingProduct.objects.get_or_create(
                name=product_data['name'],
                defaults={
                    'slug': slugify(product_data['name']),
                    'category': product_data['category'],
                    'brand': product_data['brand'],
                    'price': product_data['price'],
                    'currency': 'RUB',
                    'size': product_data['size'],
                    'color': product_data['color'],
                    'material': product_data['material'],
                    'season': product_data['season'],
                    'description': product_data['description'],
                    'is_active': True,
                    'is_available': True
                }
            )
            if created:
                self.stdout.write(f'Создан товар одежды: {product.name}')

    def _create_shoes_data(self, brands):
        """Создает данные для обуви."""
        # Создаем категории обуви
        women_shoes = ShoeCategory.objects.create(
            name='Женская обувь',
            slug='women-shoes',
            gender='women',
            shoe_type='general',
            is_active=True,
            sort_order=1
        )
        
        sneakers = ShoeCategory.objects.create(
            name='Кроссовки',
            slug='sneakers',
            gender='women',
            shoe_type='sneakers',
            parent=women_shoes,
            is_active=True,
            sort_order=1
        )
        
        # Создаем товары обуви
        shoe_products = [
            {
                'name': 'Кроссовки Nike Air Max',
                'category': sneakers,
                'brand': brands['Nike'],
                'price': 8999.00,
                'size': '38',
                'color': 'Белый',
                'material': 'Текстиль',
                'heel_height': 'Плоская подошва',
                'sole_type': 'Резина',
                'description': 'Удобные кроссовки для спорта'
            },
            {
                'name': 'Туфли Zara',
                'category': women_shoes,
                'brand': brands['Zara'],
                'price': 3999.00,
                'size': '37',
                'color': 'Черный',
                'material': 'Кожа',
                'heel_height': '5 см',
                'sole_type': 'Резина',
                'description': 'Элегантные туфли на каблуке'
            }
        ]
        
        for product_data in shoe_products:
            product, created = ShoeProduct.objects.get_or_create(
                name=product_data['name'],
                defaults={
                    'slug': slugify(product_data['name']),
                    'category': product_data['category'],
                    'brand': product_data['brand'],
                    'price': product_data['price'],
                    'currency': 'RUB',
                    'size': product_data['size'],
                    'color': product_data['color'],
                    'material': product_data['material'],
                    'heel_height': product_data['heel_height'],
                    'sole_type': product_data['sole_type'],
                    'description': product_data['description'],
                    'is_active': True,
                    'is_available': True
                }
            )
            if created:
                self.stdout.write(f'Создан товар обуви: {product.name}')

    def _create_electronics_data(self, brands):
        """Создает данные для электроники."""
        # Создаем категории электроники
        phones = ElectronicsCategory.objects.create(
            name='Смартфоны',
            slug='smartphones',
            device_type='phones',
            is_active=True,
            sort_order=1
        )
        
        laptops = ElectronicsCategory.objects.create(
            name='Ноутбуки',
            slug='laptops',
            device_type='laptops',
            is_active=True,
            sort_order=2
        )
        
        # Создаем товары электроники
        electronics_products = [
            {
                'name': 'iPhone 15 Pro',
                'category': phones,
                'brand': brands['Apple'],
                'price': 99999.00,
                'model': 'iPhone 15 Pro',
                'specifications': {
                    'screen': '6.1"',
                    'storage': '256GB',
                    'color': 'Титан'
                },
                'warranty': '1 год',
                'power_consumption': 'Низкое',
                'description': 'Новейший iPhone с чипом A17 Pro'
            },
            {
                'name': 'Samsung Galaxy S24',
                'category': phones,
                'brand': brands['Samsung'],
                'price': 79999.00,
                'model': 'Galaxy S24',
                'specifications': {
                    'screen': '6.2"',
                    'storage': '128GB',
                    'color': 'Черный'
                },
                'warranty': '2 года',
                'power_consumption': 'Низкое',
                'description': 'Флагманский смартфон Samsung'
            },
            {
                'name': 'MacBook Air M2',
                'category': laptops,
                'brand': brands['Apple'],
                'price': 129999.00,
                'model': 'MacBook Air M2',
                'specifications': {
                    'screen': '13.6"',
                    'storage': '512GB',
                    'ram': '8GB'
                },
                'warranty': '1 год',
                'power_consumption': 'Очень низкое',
                'description': 'Ультратонкий ноутбук с чипом M2'
            }
        ]
        
        for product_data in electronics_products:
            product, created = ElectronicsProduct.objects.get_or_create(
                name=product_data['name'],
                defaults={
                    'slug': slugify(product_data['name']),
                    'category': product_data['category'],
                    'brand': product_data['brand'],
                    'price': product_data['price'],
                    'currency': 'RUB',
                    'model': product_data['model'],
                    'specifications': product_data['specifications'],
                    'warranty': product_data['warranty'],
                    'power_consumption': product_data['power_consumption'],
                    'description': product_data['description'],
                    'is_active': True,
                    'is_available': True
                }
            )
            if created:
                self.stdout.write(f'Создан товар электроники: {product.name}')
