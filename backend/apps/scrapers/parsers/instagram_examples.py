"""Примеры использования Instagram парсера в коде."""

from apps.scrapers.parsers.instagram import InstagramParser
from apps.catalog.models import Product, Category, ProductImage
from django.utils.text import slugify
from django.utils import timezone


def example_parse_profile():
    """Пример парсинга профиля Instagram."""
    
    # Создаем экземпляр парсера
    parser = InstagramParser()
    
    # Парсим профиль
    products = parser.parse_product_list(
        category_url='https://www.instagram.com/bookstore_istanbul/',
        max_pages=30
    )
    
    print(f"Спарсено товаров: {len(products)}")
    
    # Выводим информацию о первом товаре
    if products:
        product = products[0]
        print(f"\nПример товара:")
        print(f"Название: {product.name}")
        print(f"Описание: {product.description[:100]}...")
        print(f"Изображений: {len(product.images)}")
        print(f"URL: {product.url}")
        print(f"Лайков: {product.attributes.get('likes')}")
        print(f"Хештеги: {product.attributes.get('hashtags')}")


def example_parse_hashtag():
    """Пример парсинга по хештегу."""
    
    parser = InstagramParser()
    
    # Парсим по хештегу
    products = parser.parse_product_list(
        category_url='https://www.instagram.com/explore/tags/turkishbooks/',
        max_pages=20
    )
    
    print(f"Найдено товаров по хештегу #turkishbooks: {len(products)}")


def example_parse_single_post():
    """Пример парсинга одного поста."""
    
    parser = InstagramParser()
    
    # Парсим конкретный пост
    product = parser.parse_product_detail(
        product_url='https://www.instagram.com/p/ABC123xyz/'
    )
    
    if product:
        print(f"Спарсен пост: {product.name}")
        print(f"Изображений: {len(product.images)}")
    else:
        print("Не удалось спарсить пост")


def example_with_authentication():
    """Пример использования с аутентификацией."""
    
    # Создаем парсер с аутентификацией
    parser = InstagramParser(
        username='your_instagram_login',
        password='your_instagram_password'
    )
    
    # Теперь можем парсить приватные профили
    products = parser.parse_product_list(
        category_url='https://www.instagram.com/private_bookstore/',
        max_pages=10
    )
    
    print(f"Спарсено из приватного профиля: {len(products)}")


def example_save_to_database():
    """Пример сохранения спарсенных товаров в базу данных."""
    
    parser = InstagramParser()
    
    # Парсим товары
    products = parser.parse_product_list(
        category_url='https://www.instagram.com/bookstore/',
        max_pages=20
    )
    
    # Получаем категорию
    try:
        category = Category.objects.get(slug='books')
    except Category.DoesNotExist:
        print("Категория 'books' не найдена. Создайте её сначала.")
        return
    
    created_count = 0
    updated_count = 0
    
    for product_data in products:
        # Создаем или обновляем товар
        product, created = Product.objects.update_or_create(
            external_id=product_data.external_id,
            defaults={
                'name': product_data.name,
                'slug': slugify(product_data.name)[:500],
                'description': product_data.description,
                'product_type': 'books',
                'category': category,
                'external_url': product_data.url,
                'external_data': product_data.attributes,
                'is_available': False,  # Недоступен пока не установлена цена
                'main_image': product_data.images[0] if product_data.images else '',
                'last_synced_at': timezone.now(),
            }
        )
        
        # Сохраняем изображения
        if created and product_data.images:
            for idx, image_url in enumerate(product_data.images):
                ProductImage.objects.create(
                    product=product,
                    image_url=image_url,
                    sort_order=idx,
                    is_primary=(idx == 0),
                )
        
        if created:
            created_count += 1
        else:
            updated_count += 1
    
    print(f"Создано: {created_count}, Обновлено: {updated_count}")


def example_filter_by_hashtags():
    """Пример фильтрации товаров по хештегам."""
    
    parser = InstagramParser()
    
    # Парсим профиль
    products = parser.parse_product_list(
        category_url='https://www.instagram.com/bookstore/',
        max_pages=50
    )
    
    # Фильтруем только посты с определенными хештегами
    filtered_products = []
    required_hashtags = ['books', 'reading', 'bookstagram']
    
    for product in products:
        hashtags = product.attributes.get('hashtags', [])
        if any(tag in hashtags for tag in required_hashtags):
            filtered_products.append(product)
    
    print(f"Всего товаров: {len(products)}")
    print(f"С нужными хештегами: {len(filtered_products)}")


def example_custom_category_mapping():
    """Пример кастомного маппинга категорий по хештегам."""
    
    parser = InstagramParser()
    
    # Маппинг хештегов на категории
    hashtag_to_category = {
        'fiction': 'books-fiction',
        'nonfiction': 'books-nonfiction',
        'children': 'books-children',
        'textbook': 'books-educational',
    }
    
    products = parser.parse_product_list(
        category_url='https://www.instagram.com/bookstore/',
        max_pages=30
    )
    
    # Определяем категорию для каждого товара
    for product in products:
        hashtags = product.attributes.get('hashtags', [])
        
        # Ищем совпадение с маппингом
        for hashtag, category_slug in hashtag_to_category.items():
            if hashtag in hashtags:
                product.category = category_slug
                break
        else:
            # По умолчанию
            product.category = 'books'
        
        print(f"{product.name} -> {product.category}")


# Использование в Django shell:
# 
# from apps.scrapers.parsers.instagram_examples import *
# example_parse_profile()
# example_save_to_database()
