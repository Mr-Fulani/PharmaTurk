
import os
import django
import sys
import logging
from urllib.parse import urlparse

# Настройка окружения
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from apps.scrapers.services import ScraperIntegrationService, ScrapingSession
from apps.scrapers.models import ScraperConfig
from apps.catalog.models import Product, BookProduct
from apps.scrapers.parsers.ummaland import UmmalandParser
from apps.scrapers.parsers.ilacabak import IlacabakParser

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_test():
    print("--- Manual Scraper Test ---")
    
    if len(sys.argv) > 1:
        target_url = sys.argv[1]
    else:
        print("Usage: python backend/run_scraper_test.py <URL>")
        return

    print(f"Scraping URL: {target_url}")

    # 1. Определяем парсер по URL
    domain = urlparse(target_url).netloc
    parser_class = None
    config_name = "Manual Test Config"
    parser_name = ""

    if "ummaland" in domain or "umma-land" in domain:
        parser_class = UmmalandParser
        parser_name = "ummaland"
    elif "ilacabak" in domain:
        parser_class = IlacabakParser
        parser_name = "ilacabak"
    else:
        print(f"Unknown domain: {domain}")
        return

    # 2. Создаем или получаем Config и Session (фиктивные)
    try:
        config, created = ScraperConfig.objects.get_or_create(
            name=f"Test {parser_name}",
            defaults={
                "parser_class": parser_name,
                "base_url": f"https://{domain}",
                "is_enabled": True
            }
        )
    except Exception:
        # Если конфиг с таким именем уже есть, но с другими параметрами - берем первый попавшийся
        config = ScraperConfig.objects.filter(parser_class=parser_name).first()
        if not config:
            config = ScraperConfig.objects.create(
                name=f"Test {parser_name} {timezone.now().timestamp()}",
                parser_class=parser_name,
                base_url=f"https://{domain}"
            )

    session = ScrapingSession.objects.create(
        scraper_config=config,
        status="running",
        started_at=timezone.now()
    )

    service = ScraperIntegrationService()

    try:
        # 3. Запускаем парсер
        print(f"Running parser: {parser_name}...")
        with parser_class(base_url=config.base_url) as parser:
            detail_result = parser.parse_product_detail(target_url)

        if not detail_result:
            print("❌ Parser returned None. Check logs.")
            return

        scraped_product = detail_result[0] if isinstance(detail_result, list) else detail_result
        if isinstance(detail_result, list) and len(detail_result) > 1:
            print(f"ℹ️ Парсер вернул {len(detail_result)} вариантов; для теста обрабатывается первый.")

        print("\n--- Scraped Data ---")
        print(f"Name: {scraped_product.name}")
        print(f"Price: {scraped_product.price} {scraped_product.currency}")
        print(f"Images: {len(scraped_product.images)} found")
        for img in scraped_product.images:
            print(f" - {img}")
        print(f"Attributes: {scraped_product.attributes}")
        
        # 4. Сохраняем (эмулируем логику)
        print("\n--- Saving to Database ---")
        action, product = service._process_single_product(session, scraped_product)
        print(f"Action: {action}")
        print(f"Product ID: {product.id}")
        
        if product.product_type == 'books':
            print("\n--- Book Details ---")
            book = getattr(product, 'book_item', None)
            if not book:
                 # Try fetching again
                 product.refresh_from_db()
                 book = getattr(product, 'book_item', None)

            if book:
                print(f"Book ID: {book.id}")
                print(f"ISBN: {book.isbn}")
                print(f"Publisher: {book.publisher}")
                print(f"Pages: {book.pages}")
                print(f"Language: {book.language}")
                print(f"Brand (should be None): {product.brand}")
            else:
                 print("❌ BookProduct not found!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.status = "completed"
        session.save()

if __name__ == "__main__":
    run_test()
