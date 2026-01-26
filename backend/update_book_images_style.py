import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.catalog.models import Product

def update_book_images():
    """Обновление изображений книг - устанавливаем null чтобы использовать дефолтную картинку"""
    
    books = Product.objects.filter(product_type='books')
    
    print(f"Найдено книг: {books.count()}")
    
    updated_count = 0
    for book in books:
        # Устанавливаем main_image в пустую строку
        # Фронтенд автоматически подставит /product-placeholder.svg
        
        book.main_image = ''
        book.save(update_fields=['main_image'])
        
        updated_count += 1
        print(f"Обновлено: {book.name}")
    
    print(f"\n✅ Обновлено изображений: {updated_count}")
    print(f"✅ Все книги теперь будут использовать дефолтную картинку /product-placeholder.svg")

if __name__ == '__main__':
    update_book_images()
