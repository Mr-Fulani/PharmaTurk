#!/usr/bin/env python
"""Скрипт для загрузки тестовых данных фармацевтического магазина."""

import os
import sys
import django
from decimal import Decimal

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.catalog.models import Category, Brand, Product, ProductImage
from django.utils.text import slugify


def create_categories():
    """Создает категории товаров."""
    categories_data = [
        {
            'name': 'Антибиотики',
            'description': 'Антибактериальные препараты для лечения инфекций',
            'slug': 'antibiotics'
        },
        {
            'name': 'Обезболивающие',
            'description': 'Препараты для снятия боли и воспаления',
            'slug': 'painkillers'
        },
        {
            'name': 'Витамины',
            'description': 'Витаминные комплексы и минеральные добавки',
            'slug': 'vitamins'
        },
        {
            'name': 'БАДы',
            'description': 'Биологически активные добавки',
            'slug': 'supplements'
        },
        {
            'name': 'Средства для кожи',
            'description': 'Кремы, мази и средства для ухода за кожей',
            'slug': 'skincare'
        },
        {
            'name': 'Сердечно-сосудистые',
            'description': 'Препараты для лечения сердечно-сосудистых заболеваний',
            'slug': 'cardiovascular'
        }
    ]
    
    categories = {}
    for data in categories_data:
        category, created = Category.objects.get_or_create(
            slug=data['slug'],
            defaults={
                'name': data['name'],
                'description': data['description']
            }
        )
        categories[data['slug']] = category
        if created:
            print(f"✅ Создана категория: {category.name}")
        else:
            print(f"📝 Категория уже существует: {category.name}")
    
    return categories


def create_brands():
    """Создает бренды."""
    brands_data = [
        'Bayer',
        'Pfizer', 
        'Novartis',
        'Roche',
        'Merck',
        'Sanofi',
        'AstraZeneca',
        'Johnson & Johnson',
        'GlaxoSmithKline',
        'Eli Lilly'
    ]
    
    brands = {}
    for name in brands_data:
        slug = slugify(name)
        brand, created = Brand.objects.get_or_create(
            slug=slug,
            defaults={'name': name}
        )
        brands[name] = brand
        if created:
            print(f"✅ Создан бренд: {brand.name}")
        else:
            print(f"📝 Бренд уже существует: {brand.name}")
    
    return brands


def create_products(categories, brands):
    """Создает тестовые товары."""
    products_data = [
        # Антибиотики
        {
            'name': 'Амоксициллин 500мг',
            'description': 'Антибиотик широкого спектра действия для лечения бактериальных инфекций',
            'price': Decimal('150.00'),
            'currency': 'RUB',
            'category': categories['antibiotics'],
            'brand': brands['Bayer'],
            'sku': 'AMOX-500',
            'stock_quantity': 50,
            'is_active': True
        },
        {
            'name': 'Азитромицин 250мг',
            'description': 'Антибиотик-макролид для лечения респираторных инфекций',
            'price': Decimal('280.00'),
            'currency': 'RUB',
            'category': categories['antibiotics'],
            'brand': brands['Pfizer'],
            'sku': 'AZIT-250',
            'stock_quantity': 30,
            'is_active': True
        },
        {
            'name': 'Цефтриаксон 1г',
            'description': 'Цефалоспориновый антибиотик для инъекций',
            'price': Decimal('450.00'),
            'currency': 'RUB',
            'category': categories['antibiotics'],
            'brand': brands['Roche'],
            'sku': 'CEFT-1000',
            'stock_quantity': 20,
            'is_active': True
        },
        
        # Обезболивающие
        {
            'name': 'Ибупрофен 400мг',
            'description': 'Нестероидный противовоспалительный препарат для снятия боли и воспаления',
            'price': Decimal('120.00'),
            'currency': 'RUB',
            'category': categories['painkillers'],
            'brand': brands['Bayer'],
            'sku': 'IBUP-400',
            'stock_quantity': 100,
            'is_active': True
        },
        {
            'name': 'Парацетамол 500мг',
            'description': 'Жаропонижающее и обезболивающее средство',
            'price': Decimal('80.00'),
            'currency': 'RUB',
            'category': categories['painkillers'],
            'brand': brands['Johnson & Johnson'],
            'sku': 'PARA-500',
            'stock_quantity': 150,
            'is_active': True
        },
        {
            'name': 'Диклофенак 50мг',
            'description': 'Противовоспалительный препарат для лечения артрита и болей в суставах',
            'price': Decimal('200.00'),
            'currency': 'RUB',
            'category': categories['painkillers'],
            'brand': brands['Novartis'],
            'sku': 'DICL-50',
            'stock_quantity': 40,
            'is_active': True
        },
        
        # Витамины
        {
            'name': 'Витамин C 1000мг',
            'description': 'Аскорбиновая кислота для укрепления иммунитета',
            'price': Decimal('180.00'),
            'currency': 'RUB',
            'category': categories['vitamins'],
            'brand': brands['Merck'],
            'sku': 'VITC-1000',
            'stock_quantity': 80,
            'is_active': True
        },
        {
            'name': 'Витамин D3 2000МЕ',
            'description': 'Холекальциферол для здоровья костей и иммунитета',
            'price': Decimal('250.00'),
            'currency': 'RUB',
            'category': categories['vitamins'],
            'brand': brands['Sanofi'],
            'sku': 'VITD-2000',
            'stock_quantity': 60,
            'is_active': True
        },
        {
            'name': 'Комплекс витаминов группы B',
            'description': 'Комплекс витаминов B1, B6, B12 для нервной системы',
            'price': Decimal('320.00'),
            'currency': 'RUB',
            'category': categories['vitamins'],
            'brand': brands['AstraZeneca'],
            'sku': 'VITB-COMPLEX',
            'stock_quantity': 45,
            'is_active': True
        },
        
        # БАДы
        {
            'name': 'Омега-3 1000мг',
            'description': 'Рыбий жир с высоким содержанием омега-3 жирных кислот',
            'price': Decimal('400.00'),
            'currency': 'RUB',
            'category': categories['supplements'],
            'brand': brands['GlaxoSmithKline'],
            'sku': 'OMEGA-1000',
            'stock_quantity': 35,
            'is_active': True
        },
        {
            'name': 'Пробиотик Lactobacillus',
            'description': 'Пробиотический комплекс для здоровья кишечника',
            'price': Decimal('280.00'),
            'currency': 'RUB',
            'category': categories['supplements'],
            'brand': brands['Eli Lilly'],
            'sku': 'PROB-LACTO',
            'stock_quantity': 55,
            'is_active': True
        },
        {
            'name': 'Магний 400мг',
            'description': 'Магниевая добавка для расслабления мышц и нервной системы',
            'price': Decimal('220.00'),
            'currency': 'RUB',
            'category': categories['supplements'],
            'brand': brands['Merck'],
            'sku': 'MAGN-400',
            'stock_quantity': 70,
            'is_active': True
        },
        
        # Средства для кожи
        {
            'name': 'Крем с пантенолом 5%',
            'description': 'Успокаивающий крем для раздраженной кожи',
            'price': Decimal('350.00'),
            'currency': 'RUB',
            'category': categories['skincare'],
            'brand': brands['Bayer'],
            'sku': 'PANT-5',
            'stock_quantity': 25,
            'is_active': True
        },
        {
            'name': 'Мазь с цинком 10%',
            'description': 'Подсушивающая мазь для лечения кожных проблем',
            'price': Decimal('180.00'),
            'currency': 'RUB',
            'category': categories['skincare'],
            'brand': brands['Johnson & Johnson'],
            'sku': 'ZINC-10',
            'stock_quantity': 40,
            'is_active': True
        },
        {
            'name': 'Гель с алоэ вера',
            'description': 'Увлажняющий гель для чувствительной кожи',
            'price': Decimal('420.00'),
            'currency': 'RUB',
            'category': categories['skincare'],
            'brand': brands['Sanofi'],
            'sku': 'ALOE-GEL',
            'stock_quantity': 30,
            'is_active': True
        },
        
        # Сердечно-сосудистые
        {
            'name': 'Аспирин 100мг',
            'description': 'Ацетилсалициловая кислота для профилактики тромбозов',
            'price': Decimal('90.00'),
            'currency': 'RUB',
            'category': categories['cardiovascular'],
            'brand': brands['Bayer'],
            'sku': 'ASPR-100',
            'stock_quantity': 120,
            'is_active': True
        },
        {
            'name': 'Нитроглицерин 0.5мг',
            'description': 'Препарат для купирования приступов стенокардии',
            'price': Decimal('150.00'),
            'currency': 'RUB',
            'category': categories['cardiovascular'],
            'brand': brands['Pfizer'],
            'sku': 'NITR-05',
            'stock_quantity': 60,
            'is_active': True
        }
    ]
    
    created_count = 0
    for data in products_data:
        # Создаем качественный slug из названия
        base_slug = slugify(data['name'])
        # Добавляем уникальный суффикс для избежания конфликтов
        slug = f"{base_slug}-{data['sku'].lower()}"
        
        product, created = Product.objects.get_or_create(
            slug=slug,
            defaults=data
        )
        
        if created:
            created_count += 1
            print(f"✅ Создан товар: {product.name} - {product.price} {product.currency}")
        else:
            print(f"📝 Товар уже существует: {product.name}")
    
    print(f"\n🎉 Создано новых товаров: {created_count}")
    return created_count


def main():
    """Основная функция загрузки данных."""
    print("🚀 Начинаем загрузку тестовых данных...\n")
    
    # Создаем категории
    print("📂 Создание категорий:")
    categories = create_categories()
    print()
    
    # Создаем бренды
    print("🏷️ Создание брендов:")
    brands = create_brands()
    print()
    
    # Создаем товары
    print("💊 Создание товаров:")
    created_count = create_products(categories, brands)
    print()
    
    # Итоговая статистика
    print("📊 ИТОГОВАЯ СТАТИСТИКА:")
    print(f"Категорий: {Category.objects.count()}")
    print(f"Брендов: {Brand.objects.count()}")
    print(f"Товаров: {Product.objects.count()}")
    print(f"Новых товаров создано: {created_count}")
    
    print("\n✅ Загрузка тестовых данных завершена!")


if __name__ == '__main__':
    main()
