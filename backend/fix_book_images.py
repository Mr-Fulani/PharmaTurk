import os
import urllib.parse

import django


def fix_book_images():
    """Добавление placeholder изображений для книг без картинок"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    from apps.catalog.models import Product

    books_without_images = Product.objects.filter(
        product_type='books',
        main_image__isnull=True
    )

    print(f"Найдено книг без изображений: {books_without_images.count()}")

    updated_count = 0
    for book in books_without_images:
        # Создаем URL для placeholder изображения
        # Используем первые 20 символов названия книги
        book_name_short = book.name[:20].replace(' ', '+')
        encoded_name = urllib.parse.quote(book_name_short)

        # Используем placehold.co для генерации изображений
        placeholder_url = (
            "https://placehold.co/300x400/10B981/FFFFFF/png?text="
            f"{encoded_name}"
        )

        book.main_image = placeholder_url
        book.save(update_fields=['main_image'])

        updated_count += 1
        print(f"Обновлено изображение для: {book.name}")

    print(f"\n✅ Обновлено изображений: {updated_count}")

    # Проверяем результат
    books_with_images = Product.objects.filter(
        product_type='books',
        main_image__isnull=False
    ).count()

    total_books = Product.objects.filter(product_type='books').count()

    print(f"✅ Книг с изображениями: {books_with_images}/{total_books}")


if __name__ == '__main__':
    fix_book_images()
