"""Синхронизация векторов товаров в Qdrant для рекомендаций «похожих»."""
from django.core.management.base import BaseCommand

from apps.recommendations.models import ProductVector
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
        parser.add_argument(
            "--product-id",
            type=int,
            action="append",
            help="Индексировать конкретный товар (можно указать несколько раз)",
        )
        parser.add_argument(
            "--until-done",
            action="store_true",
            help="Повторять батчи до нуля remaining",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Сбросить last_synced у всех ProductVector (переиндексация при рассинхроне с Qdrant)",
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

        product_ids = options.get("product_id") or []
        until_done = options.get("until_done", False)
        force = options.get("force", False)

        if force and not product_ids:
            ProductVector.objects.update(last_synced=None)
            self.stdout.write(self.style.WARNING("Сброшен last_synced у всех ProductVector."))

        if product_ids:
            self.stdout.write(f"Индексация товаров {product_ids} в Qdrant...")
            result = index_product_vectors(product_ids=product_ids)
            self._print_result(result)
            return

        batch_num = 0
        while True:
            batch_num += 1
            self.stdout.write(f"Батч {batch_num}: индексация до {options['batch']} товаров...")
            result = index_product_vectors(product_ids=None, batch_size=options["batch"])
            self._print_result(result)
            if result["remaining"] <= 0 or not until_done:
                break
        if force and result["remaining"] <= 0:
            from django.core.management import call_command
            call_command("clear_similar_cache")
        if result["remaining"] > 0 and not until_done:
            self.stdout.write(
                f"Для индексации всех: sync_product_vectors --until-done или --full"
            )

    def _print_result(self, result):
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
