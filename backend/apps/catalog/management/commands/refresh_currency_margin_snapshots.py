from django.core.management.base import BaseCommand

from apps.catalog.currency_price_snapshots import refresh_currency_margin_snapshots


class Command(BaseCommand):
    help = "Пересчитывает сохранённые цены с актуальными маржами валютных пар"

    def handle(self, *args, **options):
        counts = refresh_currency_margin_snapshots()
        self.stdout.write(self.style.SUCCESS(f"Обновлено: {counts}"))
