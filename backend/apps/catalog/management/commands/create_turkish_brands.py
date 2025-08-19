"""Команда для создания турецких брендов и товаров."""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from decimal import Decimal
from apps.catalog.models import Brand, ClothingCategory, ClothingProduct


class Command(BaseCommand):
    help = 'Создает турецкие бренды и товары'

    def handle(self, *args, **options):
        self.stdout.write('Создание турецких брендов и товаров...')
        
        # Создаем турецкие бренды
        brands = self._create_turkish_brands()
        
        # Получаем категории одежды
        categories = self._get_clothing_categories()
        
        # Создаем товары для каждого бренда
        self._create_brand_products(brands, categories)
        
        self.stdout.write(
            self.style.SUCCESS('Турецкие бренды и товары успешно созданы!')
        )

    def _create_turkish_brands(self):
        """Создает турецкие бренды."""
        brands_data = [
            {
                'name': 'Zara',
                'description': 'Испанский бренд модной одежды, популярный в Турции',
                'website': 'https://www.zara.com/tr/',
                'logo': 'https://logos-world.net/wp-content/uploads/2020/04/Zara-Logo.png'
            },
            {
                'name': 'LC Waikiki',
                'description': 'Турецкий бренд доступной модной одежды для всей семьи',
                'website': 'https://www.lcw.com/',
                'logo': 'https://upload.wikimedia.org/wikipedia/commons/8/8e/LC_Waikiki_logo.png'
            },
            {
                'name': 'Koton',
                'description': 'Турецкий fashion-ритейлер с современной одеждой',
                'website': 'https://www.koton.com/',
                'logo': 'https://logos-download.com/wp-content/uploads/2021/01/Koton_Logo.png'
            },
            {
                'name': 'DeFacto',
                'description': 'Турецкий бренд стильной и доступной одежды',
                'website': 'https://www.defacto.com.tr/',
                'logo': 'https://www.defacto.com.tr/favicon.ico'
            },
            {
                'name': 'Mavi',
                'description': 'Турецкий премиальный джинсовый бренд',
                'website': 'https://www.mavi.com/',
                'logo': 'https://upload.wikimedia.org/wikipedia/commons/2/2c/Mavi_Jeans_logo.png'
            },
            {
                'name': 'Boyner',
                'description': 'Турецкий универмаг премиальной одежды и аксессуаров',
                'website': 'https://www.boyner.com.tr/',
                'logo': 'https://www.boyner.com.tr/favicon.ico'
            }
        ]
        
        brands = {}
        for brand_data in brands_data:
            brand, created = Brand.objects.get_or_create(
                name=brand_data['name'],
                defaults={
                    'slug': slugify(brand_data['name']),
                    'description': brand_data['description'],
                    'website': brand_data['website'],
                    'logo': brand_data['logo'],
                    'is_active': True
                }
            )
            brands[brand_data['name']] = brand
            if created:
                self.stdout.write(f'Создан бренд: {brand.name}')
            else:
                self.stdout.write(f'Бренд уже существует: {brand.name}')
        
        return brands

    def _get_clothing_categories(self):
        """Получает категории одежды."""
        categories = {}
        
        # Получаем или создаем основные категории
        women_clothing, _ = ClothingCategory.objects.get_or_create(
            slug='women-clothing',
            defaults={
                'name': 'Женская одежда',
                'gender': 'women',
                'clothing_type': 'general',
                'is_active': True
            }
        )
        categories['women'] = women_clothing
        
        men_clothing, _ = ClothingCategory.objects.get_or_create(
            slug='men-clothing',
            defaults={
                'name': 'Мужская одежда',
                'gender': 'men',
                'clothing_type': 'general',
                'is_active': True
            }
        )
        categories['men'] = men_clothing
        
        return categories

    def _create_brand_products(self, brands, categories):
        """Создает товары для каждого бренда."""
        
        # LC Waikiki товары
        lcw_products = [
            {
                'name': 'Базовая футболка LC Waikiki',
                'description': 'Удобная хлопковая футболка для повседневной носки',
                'price': Decimal('299.00'),
                'size': 'M',
                'color': 'Белый',
                'material': 'Хлопок',
                'season': 'Лето',
                'category': categories['women']
            },
            {
                'name': 'Джинсы прямого кроя LC Waikiki',
                'description': 'Классические джинсы прямого кроя',
                'price': Decimal('899.00'),
                'size': 'L',
                'color': 'Синий',
                'material': 'Деним',
                'season': 'Демисезон',
                'category': categories['men']
            }
        ]
        
        # Koton товары
        koton_products = [
            {
                'name': 'Стильное платье Koton',
                'description': 'Элегантное платье для особых случаев',
                'price': Decimal('1299.00'),
                'size': 'S',
                'color': 'Черный',
                'material': 'Полиэстер',
                'season': 'Демисезон',
                'category': categories['women']
            },
            {
                'name': 'Рубашка Koton',
                'description': 'Стильная мужская рубашка',
                'price': Decimal('799.00'),
                'size': 'L',
                'color': 'Голубой',
                'material': 'Хлопок',
                'season': 'Демисезон',
                'category': categories['men']
            }
        ]
        
        # DeFacto товары
        defacto_products = [
            {
                'name': 'Кардиган DeFacto',
                'description': 'Теплый вязаный кардиган',
                'price': Decimal('1599.00'),
                'size': 'M',
                'color': 'Серый',
                'material': 'Акрил',
                'season': 'Зима',
                'category': categories['women']
            },
            {
                'name': 'Спортивные штаны DeFacto',
                'description': 'Удобные спортивные штаны',
                'price': Decimal('699.00'),
                'size': 'XL',
                'color': 'Черный',
                'material': 'Полиэстер',
                'season': 'Демисезон',
                'category': categories['men']
            }
        ]
        
        # Mavi товары
        mavi_products = [
            {
                'name': 'Джинсы скинни Mavi',
                'description': 'Премиальные джинсы скинни',
                'price': Decimal('2299.00'),
                'size': 'S',
                'color': 'Темно-синий',
                'material': 'Деним',
                'season': 'Демисезон',
                'category': categories['women']
            },
            {
                'name': 'Джинсовая куртка Mavi',
                'description': 'Стильная джинсовая куртка',
                'price': Decimal('2799.00'),
                'size': 'L',
                'color': 'Синий',
                'material': 'Деним',
                'season': 'Демисезон',
                'category': categories['men']
            }
        ]
        
        # Boyner товары
        boyner_products = [
            {
                'name': 'Премиальное пальто Boyner',
                'description': 'Элегантное шерстяное пальто',
                'price': Decimal('4999.00'),
                'size': 'M',
                'color': 'Бежевый',
                'material': 'Шерсть',
                'season': 'Зима',
                'category': categories['women']
            },
            {
                'name': 'Деловой костюм Boyner',
                'description': 'Классический мужской костюм',
                'price': Decimal('6999.00'),
                'size': 'L',
                'color': 'Темно-синий',
                'material': 'Шерсть',
                'season': 'Демисезон',
                'category': categories['men']
            }
        ]
        
        # Создаем товары для каждого бренда
        brand_products = [
            (brands['LC Waikiki'], lcw_products),
            (brands['Koton'], koton_products),
            (brands['DeFacto'], defacto_products),
            (brands['Mavi'], mavi_products),
            (brands['Boyner'], boyner_products),
        ]
        
        created_count = 0
        for brand, products in brand_products:
            for product_data in products:
                slug = slugify(f"{product_data['name']}-{brand.name}")
                
                product, created = ClothingProduct.objects.get_or_create(
                    slug=slug,
                    defaults={
                        'name': product_data['name'],
                        'description': product_data['description'],
                        'brand': brand,
                        'category': product_data['category'],
                        'price': product_data['price'],
                        'currency': 'TRY',
                        'size': product_data['size'],
                        'color': product_data['color'],
                        'material': product_data['material'],
                        'season': product_data['season'],
                        'is_active': True,
                        'is_available': True,
                        'is_featured': True  # Делаем рекомендуемыми
                    }
                )
                
                if created:
                    created_count += 1
                    self.stdout.write(f'Создан товар: {product.name} - {product.price} {product.currency}')
        
        self.stdout.write(f'Создано новых товаров: {created_count}')
