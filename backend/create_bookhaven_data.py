import os

import django


def create_test_data():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    from apps.bookhaven.models import Category, Author, Book

    # Создаем категории
    fiction = Category.objects.create(
        name='Художественная литература',
        slug='fiction',
        description='Художественные произведения различных жанров',
        icon='Book'
    )

    science = Category.objects.create(
        name='Научная литература',
        slug='science',
        description='Научно-популярные книги и научные труды',
        icon='Microscope'
    )

    business = Category.objects.create(
        name='Бизнес и карьера',
        slug='business',
        description='Книги по бизнесу, маркетингу и саморазвитию',
        icon='Briefcase'
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

    # Создаем книги
    it_image = (
        "https://via.placeholder.com/300x400/4F46E5/FFFFFF"
        "?text=It"
    )
    Book.objects.create(
        title='Оно',
        slug='it',
        description='Роман о группе друзей, сражающихся с древним злом',
        price=899.99,
        old_price=1099.99,
        image=it_image,
        category=fiction,
        rating=4.5,
        reviews_count=1250,
        in_stock=True,
        stock_quantity=15,
        is_bestseller=True,
        is_new=False
    ).authors.add(author1)

    sapiens_image = (
        "https://via.placeholder.com/300x400/10B981/FFFFFF"
        "?text=Sapiens"
    )
    Book.objects.create(
        title='Sapiens: Краткая история человечества',
        slug='sapiens',
        description=(
            'История человечества от появления Homo sapiens '
            'до современности'
        ),
        price=799.99,
        old_price=999.99,
        image=sapiens_image,
        category=science,
        rating=4.8,
        reviews_count=3420,
        in_stock=True,
        stock_quantity=23,
        is_bestseller=True,
        is_new=False
    ).authors.add(author2)

    business_image = (
        "https://via.placeholder.com/300x400/F59E0B/FFFFFF"
        "?text=Business+Model"
    )
    Book.objects.create(
        title='Бизнес-модель нового поколения',
        slug='business-model-generation',
        description=(
            'Практическое руководство по разработке и тестированию '
            'бизнес-моделей'
        ),
        price=1299.99,
        image=business_image,
        category=business,
        rating=4.6,
        reviews_count=890,
        in_stock=True,
        stock_quantity=8,
        is_bestseller=False,
        is_new=True
    ).authors.add(author3)

    shining_image = (
        "https://via.placeholder.com/300x400/EF4444/FFFFFF"
        "?text=The+Shining"
    )
    Book.objects.create(
        title='Сияние',
        slug='the-shining',
        description=(
            'История писателя и его семьи, зимующих в отеле с призраками'
        ),
        price=699.99,
        old_price=899.99,
        image=shining_image,
        category=fiction,
        rating=4.4,
        reviews_count=980,
        in_stock=True,
        stock_quantity=12,
        is_bestseller=True,
        is_new=False
    ).authors.add(author1)

    deus_image = (
        "https://via.placeholder.com/300x400/8B5CF6/FFFFFF"
        "?text=Homo+Deus"
    )
    Book.objects.create(
        title='Homo Deus: Краткая история будущего',
        slug='homo-deus',
        description='Прогноз развития человечества в XXI веке',
        price=899.99,
        old_price=1199.99,
        image=deus_image,
        category=science,
        rating=4.7,
        reviews_count=2150,
        in_stock=True,
        stock_quantity=18,
        is_bestseller=True,
        is_new=False
    ).authors.add(author2)

    # Обновляем счетчики категорий
    fiction.update_book_count()
    science.update_book_count()
    business.update_book_count()

    print("Тестовые данные BookHaven успешно созданы!")
    print(f"Категорий: {Category.objects.count()}")
    print(f"Авторов: {Author.objects.count()}")
    print(f"Книг: {Book.objects.count()}")


if __name__ == '__main__':
    create_test_data()
