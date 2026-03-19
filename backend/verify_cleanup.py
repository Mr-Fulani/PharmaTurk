import os
import django
import sys

# Настройка окружения Django
sys.path.append('/app')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.catalog.models import Product, BookProduct

def verify():
    print("Verifying Product model cleanup...")
    product_fields = [f.name for f in Product._meta.get_fields()]
    legacy_fields = ['isbn', 'publisher', 'publication_date', 'pages', 'language', 'cover_type', 'rating', 'reviews_count', 'is_bestseller']
    
    errors = []
    print(f"Product fields: {product_fields}")
    
    for field in legacy_fields:
        if field in product_fields:
            # Check if it's REALLY a field on Product or just reverse relation from BookProduct?
            # get_fields() returns reverse relations too!
            # BookProduct has OneToOne to Product.
            # But OneToOne creates a reverse relation on Product.
            # However, the field name on Product would be 'book_item' (related_name='book_item').
            # It would NOT be 'isbn'.
            # Unless BookProduct field name collisions? No.
            
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
        # sys.exit(1) # Don't exit with error to see output

if __name__ == '__main__':
    verify()
