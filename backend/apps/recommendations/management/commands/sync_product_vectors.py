"""Синхронизация векторов товаров в Qdrant для рекомендаций «похожих»."""
from django.core.management.base import BaseCommand

from apps.recommendations.tasks import index_product_vectors, sync_all_products_to_qdrant


class Command(BaseCommand):
    help = (
        "Индексировать векторы товаров в Qdrant. "
        "По умолчанию — один батч (100 товаров) в foreground. "
        "С --full запускает полную синхронизацию через Celery в фоне."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--full",
            action="store_true",
            help="Запустить полную синхронизацию в фоне (Celery)",
        )
        parser.add_argument(
            "--batch",
            type=int,
            default=100,
            help="Размер батча при индексации в foreground (по умолчанию 100)",
        )

    def handle(self, *args, **options):
        if options["full"]:
            sync_all_products_to_qdrant.delay()
            self.stdout.write(
                self.style.SUCCESS(
                    "Полная синхронизация отправлена в Celery. "
                    "Прогресс смотрите в логах celeryworker."
                )
            )
            return

        self.stdout.write("Индексация одного батча в Qdrant...")
        result = index_product_vectors(product_ids=None, batch_size=options["batch"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Проиндексировано: {result['indexed']}, "
                f"ошибок: {len(result['errors'])}, "
                f"осталось в очереди: {result['remaining']}"
            )
        )
        if result["errors"]:
            for err in result["errors"][:5]:
                self.stdout.write(self.style.WARNING(f"  product_id={err['product_id']}: {err['error']}"))
            if len(result["errors"]) > 5:
                self.stdout.write(self.style.WARNING(f"  ... и ещё {len(result['errors']) - 5} ошибок."))
        if result["remaining"] > 0:
            self.stdout.write(
                f"Для индексации всех товаров запустите: python manage.py sync_product_vectors --full"
            )
