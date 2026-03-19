"""Прогон AI по тестовым товарам: качество и стоимость."""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Sum, Avg, Count
from apps.catalog.models import Product
from apps.ai.models import AIProcessingLog, AIProcessingStatus
from apps.ai.services.content_generator import ContentGenerator


class Command(BaseCommand):
    help = "Запустить AI обработку на N товарах и вывести сводку (успех, уверенность, стоимость)"

    def add_arguments(self, parser):
        parser.add_argument(
            "limit",
            nargs="?",
            type=int,
            default=5,
            help="Сколько товаров обработать (по умолчанию 5)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать, какие товары будут выбраны, не запускать",
        )
        parser.add_argument(
            "--auto-apply",
            action="store_true",
            help="Применять результаты к товару при успехе",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        dry_run = options["dry_run"]
        auto_apply = options["auto_apply"]
        products = Product.objects.all()[:limit]
        product_ids = list(products.values_list("id", flat=True))
        if not product_ids:
            self.stdout.write(self.style.WARNING("Нет товаров в каталоге."))
            return
        self.stdout.write(f"Товаров к обработке: {len(product_ids)} (id: {product_ids})")
        if dry_run:
            self.stdout.write("Dry run — выход без запуска.")
            return
        generator = ContentGenerator()
        ok = 0
        err = 0
        for pid in product_ids:
            try:
                log = generator.process_product(
                    product_id=pid,
                    processing_type="full",
                    auto_apply=auto_apply,
                )
                status = getattr(log, "status", None)
                if status in (AIProcessingStatus.COMPLETED, AIProcessingStatus.APPROVED, AIProcessingStatus.MODERATION):
                    ok += 1
                    conf = getattr(log, "category_confidence", None) or 0
                    cost = getattr(log, "cost_usd", None) or Decimal("0")
                    self.stdout.write(
                        f"  product {pid}: status={status}, confidence={conf:.2f}, cost_usd={cost}"
                    )
                else:
                    err += 1
                    self.stdout.write(self.style.WARNING(f"  product {pid}: status={status}"))
            except Exception as e:
                err += 1
                self.stdout.write(self.style.ERROR(f"  product {pid}: error {e}"))
        self.stdout.write("")
        agg = AIProcessingLog.objects.filter(product_id__in=product_ids).aggregate(
            total_cost=Sum("cost_usd"),
            avg_conf=Avg("category_confidence"),
            cnt=Count("id"),
        )
        total_cost = agg["total_cost"] or Decimal("0")
        avg_conf = agg["avg_conf"] or 0
        self.stdout.write(
            self.style.SUCCESS(
                f"Итого: обработано {ok + err}, успешно {ok}, ошибок {err}. "
                f"Логов по товарам: {agg['cnt']}, сумма cost_usd={total_cost:.4f}, "
                f"avg confidence={avg_conf:.2f}"
            )
        )
