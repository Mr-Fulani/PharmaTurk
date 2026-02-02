import os
from decimal import Decimal

import django


def create_islamic_books():
    """Создание исламских категорий книг и книг в этих категориях"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    from apps.catalog.models import Category, Product

    # Получаем главную категорию "Книги"
    books_category = Category.objects.get(slug='books')

    # Создаем исламские категории
    categories_data = [
        {
            'name': 'Исламский фикх',
            'slug': 'islamic-fiqh',
            'description': 'Книги по исламскому праву и юриспруденции'
        },
        {
            'name': 'Тафсир',
            'slug': 'tafsir',
            'description': 'Толкования Корана'
        },
        {
            'name': 'Адаб',
            'slug': 'adab',
            'description': 'Исламская этика и нравственность'
        },
        {
            'name': 'Хадис',
            'slug': 'hadith',
            'description': 'Сборники хадисов и их толкования'
        },
        {
            'name': 'История',
            'slug': 'history',
            'description': 'Исламская история и биографии'
        }
    ]

    created_categories = {}
    for cat_data in categories_data:
        category, created = Category.objects.get_or_create(
            slug=cat_data['slug'],
            defaults={
                'name': cat_data['name'],
                'description': cat_data['description'],
                'parent': books_category,
                'is_active': True
            }
        )
        created_categories[cat_data['slug']] = category
        status = 'Создана' if created else 'Найдена'
        print(f"{status} категория: {category.name}")

    # Создаем книги для каждой категории
    books_data = [
        # Исламский фикх
        {
            'name': 'Фикх ас-Сунна',
            'slug': 'fiqh-as-sunna',
            'description': (
                'Классический труд по исламскому праву на основе Сунны'
            ),
            'category': 'islamic-fiqh',
            'price': '1299.99',
            'old_price': '1599.99',
            'isbn': '978-5-699-12345-1',
            'publisher': 'Умма',
            'pages': 856,
            'language': 'Русский',
            'cover_type': 'Твердая',
            'rating': '4.90',
            'reviews_count': 245,
            'is_bestseller': True,
            'stock_quantity': 15
        },
        {
            'name': 'Бидаят аль-Муджтахид',
            'slug': 'bidayat-al-mujtahid',
            'description': 'Сравнительное исламское право',
            'category': 'islamic-fiqh',
            'price': '1499.99',
            'old_price': '1899.99',
            'isbn': '978-5-699-12346-2',
            'publisher': 'Диля',
            'pages': 1024,
            'language': 'Русский',
            'cover_type': 'Твердая',
            'rating': '4.85',
            'reviews_count': 189,
            'is_bestseller': True,
            'stock_quantity': 12
        },

        # Тафсир
        {
            'name': 'Тафсир Ибн Касира',
            'slug': 'tafsir-ibn-kathir',
            'description': 'Классическое толкование Корана',
            'category': 'tafsir',
            'price': '2499.99',
            'old_price': '2999.99',
            'isbn': '978-5-699-12347-3',
            'publisher': 'Умма',
            'pages': 1456,
            'language': 'Русский',
            'cover_type': 'Твердая',
            'rating': '4.95',
            'reviews_count': 312,
            'is_bestseller': True,
            'stock_quantity': 8
        },
        {
            'name': 'Тафсир ас-Саади',
            'slug': 'tafsir-as-saadi',
            'description': 'Современное толкование Корана',
            'category': 'tafsir',
            'price': '1899.99',
            'old_price': '2299.99',
            'isbn': '978-5-699-12348-4',
            'publisher': 'Диля',
            'pages': 1128,
            'language': 'Русский',
            'cover_type': 'Твердая',
            'rating': '4.88',
            'reviews_count': 267,
            'is_bestseller': True,
            'stock_quantity': 10
        },

        # Адаб
        {
            'name': 'Рияд ас-Салихин',
            'slug': 'riyad-as-salihin',
            'description': 'Сады праведных - сборник хадисов о нравственности',
            'category': 'adab',
            'price': '899.99',
            'old_price': '1199.99',
            'isbn': '978-5-699-12349-5',
            'publisher': 'Умма',
            'pages': 624,
            'language': 'Русский',
            'cover_type': 'Твердая',
            'rating': '4.92',
            'reviews_count': 456,
            'is_bestseller': True,
            'stock_quantity': 25
        },
        {
            'name': 'Ихья улюм ад-дин',
            'slug': 'ihya-ulum-ad-din',
            'description': 'Возрождение религиозных наук',
            'category': 'adab',
            'price': '1699.99',
            'old_price': '2099.99',
            'isbn': '978-5-699-12350-1',
            'publisher': 'Диля',
            'pages': 968,
            'language': 'Русский',
            'cover_type': 'Твердая',
            'rating': '4.87',
            'reviews_count': 198,
            'is_bestseller': False,
            'stock_quantity': 14
        },

        # Хадис
        {
            'name': 'Сахих аль-Бухари',
            'slug': 'sahih-al-bukhari',
            'description': 'Самый достоверный сборник хадисов',
            'category': 'hadith',
            'price': '2999.99',
            'old_price': '3499.99',
            'isbn': '978-5-699-12351-2',
            'publisher': 'Умма',
            'pages': 1856,
            'language': 'Русский',
            'cover_type': 'Твердая',
            'rating': '4.98',
            'reviews_count': 523,
            'is_bestseller': True,
            'stock_quantity': 6
        },
        {
            'name': 'Сахих Муслим',
            'slug': 'sahih-muslim',
            'description': 'Второй по достоверности сборник хадисов',
            'category': 'hadith',
            'price': '2799.99',
            'old_price': '3299.99',
            'isbn': '978-5-699-12352-3',
            'publisher': 'Умма',
            'pages': 1724,
            'language': 'Русский',
            'cover_type': 'Твердая',
            'rating': '4.96',
            'reviews_count': 487,
            'is_bestseller': True,
            'stock_quantity': 7
        },

        # История
        {
            'name': 'Ас-Сира ан-Набавийя',
            'slug': 'as-sira-an-nabawiyya',
            'description': 'Жизнеописание Пророка Мухаммада',
            'category': 'history',
            'price': '1399.99',
            'old_price': '1799.99',
            'isbn': '978-5-699-12353-4',
            'publisher': 'Умма',
            'pages': 892,
            'language': 'Русский',
            'cover_type': 'Твердая',
            'rating': '4.93',
            'reviews_count': 378,
            'is_bestseller': True,
            'stock_quantity': 18
        },
        {
            'name': 'История халифата',
            'slug': 'history-of-caliphate',
            'description': 'История исламской цивилизации',
            'category': 'history',
            'price': '1599.99',
            'old_price': '1999.99',
            'isbn': '978-5-699-12354-5',
            'publisher': 'Диля',
            'pages': 1056,
            'language': 'Русский',
            'cover_type': 'Твердая',
            'rating': '4.84',
            'reviews_count': 234,
            'is_bestseller': False,
            'stock_quantity': 11
        }
    ]

    created_count = 0
    for book_data in books_data:
        category = created_categories[book_data['category']]

        # Проверяем, существует ли книга
        if Product.objects.filter(slug=book_data['slug']).exists():
            print(f"Книга уже существует: {book_data['name']}")
            continue

        book = Product.objects.create(
            name=book_data['name'],
            slug=book_data['slug'],
            description=book_data['description'],
            category=category,
            product_type='books',
            price=Decimal(book_data['price']),
            old_price=Decimal(book_data['old_price']),
            currency='RUB',
            is_available=True,
            stock_quantity=book_data['stock_quantity'],
            isbn=book_data['isbn'],
            publisher=book_data['publisher'],
            pages=book_data['pages'],
            language=book_data['language'],
            cover_type=book_data['cover_type'],
            rating=Decimal(book_data['rating']),
            reviews_count=book_data['reviews_count'],
            is_bestseller=book_data['is_bestseller'],
            is_featured=book_data['is_bestseller']
        )
        created_count += 1
        print(f"Создана книга: {book.name} в категории {category.name}")

    print(f"\n✅ Создано категорий: {len(created_categories)}")
    print(f"✅ Создано книг: {created_count}")
    total_books = Product.objects.filter(product_type='books').count()
    print(f"✅ Всего книг в базе: {total_books}")


if __name__ == '__main__':
    create_islamic_books()
