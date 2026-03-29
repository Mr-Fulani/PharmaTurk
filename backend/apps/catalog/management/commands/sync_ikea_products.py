from django.core.management.base import BaseCommand, CommandError
from apps.catalog.services import IkeaService

class Command(BaseCommand):
    help = 'Синхронизация товаров IKEA по артикулам или поисковому запросу'

    def add_arguments(self, parser):
        parser.add_argument('--item-codes', nargs='+', type=str, help='Список артикулов IKEA')
        parser.add_argument('--search', type=str, help='Поисковый запрос для IKEA')
        parser.add_argument('--limit', type=int, default=10, help='Лимит результатов при поиске')

    def handle(self, *args, **options):
        service = IkeaService()
        item_codes = options.get('item_codes')
        search_query = options.get('search')
        limit = options.get('limit')

        if not item_codes and not search_query:
            raise CommandError('Необходимо указать --item-codes или --search')

        if item_codes:
            self.stdout.write(f"Fetching {len(item_codes)} items from IKEA...")
            items = service.fetch_items(item_codes)
            if not items:
                self.stdout.write(self.style.WARNING("No items found or error occurred."))
            else:
                self._process_items(service, items)

        if search_query:
            self.stdout.write(f"Searching IKEA for '{search_query}' (limit {limit})...")
            search_results = service.search_items(search_query, limit=limit)
            if isinstance(search_results, list):
                self._process_items(service, search_results)
            elif isinstance(search_results, dict) and "items" in search_results:
                # В некоторых версиях может быть обертка
                self._process_items(service, search_results["items"])
            else:
                self.stdout.write(self.style.WARNING(f"Unexpected search result: {search_results}"))

    def _process_items(self, service, items):
        count = 0
        for item in items:
            try:
                product = service.upsert_furniture_product(item)
                if product:
                    self.stdout.write(self.style.SUCCESS(f"Successfully synced: {product.name} ({product.external_id})"))
                    count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error syncing item: {str(e)}"))
        
        self.stdout.write(self.style.SUCCESS(f"Total processed: {count}"))
