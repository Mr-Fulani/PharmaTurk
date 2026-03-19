"""Очистка кэша похожих товаров после переиндексации."""
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Очищает кэш rec:similar:* (похожие товары). Запускать после sync_product_vectors."

    def handle(self, *args, **options):
        import redis
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
        client = redis.from_url(redis_url)
        pattern = "*rec:similar*"
        deleted = 0
        for key in client.scan_iter(match=pattern, count=100):
            client.delete(key)
            deleted += 1
        self.stdout.write(self.style.SUCCESS(f"Очищено ключей кэша: {deleted} (паттерн: {pattern})"))
