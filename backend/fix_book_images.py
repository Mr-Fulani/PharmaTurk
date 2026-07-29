import os

import django
from django.db.models import Q


def fix_book_images():
    """Удаляет внешние placeholder-URL, чтобы фронтенд показал локальный fallback."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    from apps.catalog.models import Product

    books_with_external_placeholders = Product.objects.filter(product_type='books').filter(
        Q(main_image__icontains='placehold.co')
        | Q(main_image__icontains='via.placeholder.com')
        | Q(main_image__icontains='picsum.photos')
    )

    print(
        "Найдено книг с внешними placeholder-изображениями: "
        f"{books_with_external_placeholders.count()}"
    )

    updated_count = 0
    for book in books_with_external_placeholders:
        book.main_image = ''
        book.save(update_fields=['main_image'])

        updated_count += 1
        print(f"Обновлено изображение для: {book.name}")

    print(f"\n✅ Обновлено изображений: {updated_count}")

    # Проверяем результат
    books_with_images = Product.objects.filter(product_type='books').exclude(
        Q(main_image__isnull=True) | Q(main_image='')
    ).count()

    total_books = Product.objects.filter(product_type='books').count()

    print(f"✅ Книг с изображениями: {books_with_images}/{total_books}")


if __name__ == '__main__':
    fix_book_images()
