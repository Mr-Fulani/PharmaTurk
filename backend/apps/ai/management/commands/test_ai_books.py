from django.core.management.base import BaseCommand
from apps.catalog.models import Product, Category
from apps.ai.tasks import process_product_ai_task as process_product_ai
from apps.ai.models import AIProcessingLog
import time
import sys

class Command(BaseCommand):
    help = 'Test AI processing on book products'

    def handle(self, *args, **options):
        self.stdout.write('Creating test book products...')
        
        # Create a category if needed
        category, _ = Category.objects.get_or_create(
            slug='books-test',
            defaults={'name': 'Books Test'}
        )

        test_books = [
            {
                'title': 'The Great Gatsby',
                'description': 'A novel by F. Scott Fitzgerald.',
                'image_url': 'https://covers.openlibrary.org/b/id/8432028-L.jpg'
            },
            {
                'title': '1984',
                'description': 'A dystopian social science fiction novel by George Orwell.',
                'image_url': 'https://covers.openlibrary.org/b/id/7222246-L.jpg'
            },
            {
                'title': 'The Hobbit',
                'description': 'A children\'s fantasy novel by J. R. R. Tolkien.',
                'image_url': 'https://covers.openlibrary.org/b/id/6979861-L.jpg'
            },
            {
                'title': 'Harry Potter and the Sorcerer\'s Stone',
                'description': 'A fantasy novel written by British author J. K. Rowling.',
                'image_url': 'https://covers.openlibrary.org/b/id/10523474-L.jpg'
            },
            {
                'title': 'To Kill a Mockingbird',
                'description': 'A novel by Harper Lee published in 1960.',
                'image_url': 'https://covers.openlibrary.org/b/id/8225261-L.jpg'
            }
        ]

        created_products = []
        for book in test_books:
            # Use update_or_create to ensure fresh data and trigger signals if needed
            product, created = Product.objects.update_or_create(
                slug=book['title'].lower().replace(' ', '-').replace("'", ""),
                defaults={
                    'name': book['title'],
                    'description': book['description'],
                    'category': category,
                    'external_id': f"test-{book['title'][:5]}",
                    'main_image': book['image_url']
                }
            )
            created_products.append(product)
            status = "Created" if created else "Updated"
            self.stdout.write(f"{status} product: {product.name}")

        self.stdout.write(f"\nTriggering AI processing for {len(created_products)} products...")
        
        # Import here to avoid early loading issues
        from apps.ai.services.content_generator import ContentGenerator
        
        for product in created_products:
            self.stdout.write(f"Processing {product.name} (ID: {product.id})...")
            
            try:
                generator = ContentGenerator()
                # Corrected call signature based on ContentGenerator.process_product definition
                log = generator.process_product(
                    product_id=product.id,
                    processing_type='full',
                    auto_apply=True
                )
                
                self.stdout.write(self.style.SUCCESS(f"Done! Log ID: {log.id}"))
                
                # Refresh log to get latest updates if any async stuff happened (though process_product seems sync mostly)
                log.refresh_from_db()
                
                if log.generated_title:
                    self.stdout.write(f"Generated Title: {log.generated_title}")
                if log.suggested_category:
                    self.stdout.write(f"Category: {log.suggested_category}")
                if log.category_confidence:
                    self.stdout.write(f"Confidence: {log.category_confidence}")
                
                if log.image_analysis:
                     self.stdout.write(f"Image Analysis: {str(log.image_analysis)[:100]}...")
                     
                self.stdout.write("-" * 30)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing {product.name}: {e}"))
                # Print full traceback for debugging
                import traceback
                traceback.print_exc()

