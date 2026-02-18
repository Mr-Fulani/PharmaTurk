import os
import django
import sys

# Настройка окружения Django
sys.path.append('/app')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from apps.catalog.models import Product, BookProduct

def verify():
    print("Verifying Product model cleanup...")
    # Используем local_fields чтобы исключить reverse relations
    # Но мы хотим убедиться, что их нет вообще.
    # get_fields() возвращает все.
    
    # Но Product может иметь reverse relation 'book_item' -> 'isbn'? Нет.
    
    product_fields = [f.name for f in Product._meta.get_fields()]
    legacy_fields = ['isbn', 'publisher', 'publication_date', 'pages', 'language', 'cover_type', 'rating', 'reviews_count', 'is_bestseller']
    
    errors = []
    for field in legacy_fields:
        if field in product_fields:
            print(f"ERROR: Field '{field}' still exists in Product model")
            errors.append(field)
        else:
            print(f"OK: Field '{field}' removed from Product model")

    print("\nVerifying BookProduct model...")
    book_fields = [f.name for f in BookProduct._meta.get_fields()]
    for field in legacy_fields:
        if field in book_fields:
            print(f"OK: Field '{field}' exists in BookProduct model")
        else:
            print(f"ERROR: Field '{field}' missing in BookProduct model")
            errors.append(f"Missing {field} in BookProduct")

    if not errors:
        print("\nSUCCESS: Cleanup verification passed!")
    else:
        print("\nFAILURE: Cleanup verification failed.")
        sys.exit(1)

if __name__ == '__main__':
    verify()
