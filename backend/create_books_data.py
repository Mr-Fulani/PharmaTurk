import os
import django
from django.contrib.auth import get_user_model

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.catalog.models import Category, Product, Author, ProductAuthor

def create_book_data():
    # Получаем или создаем категорию для книг
    books_category, created = Category.objects.get_or_create(
        slug='books',
        defaults={
            'name': 'Книги',
            'description': 'Художественная и научная литература',
            'is_active': True
        }
    )
    
    # Подкатегории
    fiction = Category.objects.create(
        name='Художественная литература',
        slug='fiction',
        description='Художественные произведения различных жанров',
        parent=books_category,
        is_active=True
    )
    
    science = Category.objects.create(
        name='Научная литература',
        slug='science',
        description='Научно-популярные книги и научные труды',
        parent=books_category,
        is_active=True
    )
    
    business = Category.objects.create(
        name='Бизнес и карьера',
        slug='business',
        description='Книги по бизнесу, маркетингу и саморазвитию',
        parent=books_category,
        is_active=True
    )
    
    # Создаем авторов
    author1 = Author.objects.create(
        first_name='Стивен',
        last_name='Кинг',
        bio='Американский писатель, мастер современного хоррора',
        birth_date='1947-09-21'
    )
    
    author2 = Author.objects.create(
        first_name='Юваль',
        last_name='Ной Харари',
        bio='Израильский историк и писатель',
        birth_date='1976-02-24'
    )
    
    author3 = Author.objects.create(
        first_name='Эрик',
        last_name='Рис',
        bio='Американский предприниматель и писатель',
        birth_date='1978-01-01'
    )
    
    # Создаем книги через Product
    book1 = Product.objects.create(
        name='Оно',
        slug='it',
        description='Роман о группе друзей, сражающихся с древним злом',
        product_type='books',
        category=fiction,
        price=899.99,
        old_price=1099.99,
        main_image='https://via.placeholder.com/300x400/4F46E5/FFFFFF?text=It',
        rating=4.5,
        reviews_count=1250,
        is_available=True,
        stock_quantity=15,
        is_featured=True,
        is_active=True,
        # Поля специфичные для книг
        isbn='978-5-17-070489-6',
        publisher='АСТ',
        publication_date='1986-09-15',
        pages=1138,
        language='Русский',
        cover_type='Твердая',
        is_bestseller=True,
        is_new=False
    )
    
    book2 = Product.objects.create(
        name='Sapiens: Краткая история человечества',
        slug='sapiens',
        description='История человечества от появления Homo sapiens до современности',
        product_type='books',
        category=science,
        price=799.99,
        old_price=999.99,
        main_image='https://via.placeholder.com/300x400/10B981/FFFFFF?text=Sapiens',
        rating=4.8,
        reviews_count=3420,
        is_available=True,
        stock_quantity=23,
        is_featured=True,
        is_active=True,
        # Поля специфичные для книг
        isbn='978-5-00117-045-5',
        publisher='Alpina Non-Fiction',
        publication_date='2014-09-04',
        pages=468,
        language='Русский',
        cover_type='Твердая',
        is_bestseller=True,
        is_new=False
    )
    
    book3 = Product.objects.create(
        name='Бизнес-модель нового поколения',
        slug='business-model-generation',
        description='Практическое руководство по разработке и тестированию бизнес-моделей',
        product_type='books',
        category=business,
        price=1299.99,
        main_image='https://via.placeholder.com/300x400/F59E0B/FFFFFF?text=Business+Model',
        rating=4.6,
        reviews_count=890,
        is_available=True,
        stock_quantity=8,
        is_featured=False,
        is_active=True,
        # Поля специфичные для книг
        isbn='978-1-118-09633-9',
        publisher='Mann, Ivanov & Ferber',
        publication_date='2010-08-20',
        pages=288,
        language='Русский',
        cover_type='Мягкая',
        is_bestseller=False,
        is_new=True
    )
    
    # Связываем книги с авторами
    ProductAuthor.objects.create(product=book1, author=author1)
    ProductAuthor.objects.create(product=book2, author=author2)
    ProductAuthor.objects.create(product=book3, author=author3)
    
    print("Книги успешно добавлены в существующую систему PharmaTurk!")
    print(f"Категорий: {Category.objects.filter(slug__in=['books', 'fiction', 'science', 'business']).count()}")
    print(f"Авторов: {Author.objects.count()}")
    print(f"Книг: {Product.objects.filter(product_type='books').count()}")

if __name__ == '__main__':
    create_book_data()
