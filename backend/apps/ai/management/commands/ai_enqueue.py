"""Безопасная массовая постановка товаров в AI-очередь.

Примеры:
    manage.py ai_enqueue --product-type medicines --limit 10 --dry-run
    manage.py ai_enqueue --product-type supplements --limit 200 --batch-size 20 \\
        --wait --max-failures 3 --no-index-vectors
"""

import time
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Avg, Exists, OuterRef, Q

from apps.ai.models import AIProcessingLog, AIProcessingStatus
from apps.ai.services.ownership import SOURCE_CHANGED_KEY
from apps.ai.tasks import ACTIVE_AI_LOG_STATUSES, enqueue_or_apply_product_ai
from apps.catalog.models import Category, Product

# Оценка стоимости, если по типу товара ещё нет завершённых логов (USD, p90 аудита).
_FALLBACK_COST_USD = {"medicines": Decimal("0.008")}
_DEFAULT_COST_USD = Decimal("0.002")
_DONE_STATUSES = (
    AIProcessingStatus.COMPLETED,
    AIProcessingStatus.APPROVED,
    AIProcessingStatus.MODERATION,
    *ACTIVE_AI_LOG_STATUSES,
)


class Command(BaseCommand):
    help = "Поставить товары в AI-очередь батчами: фильтры, лимит, --dry-run, остановка по ошибкам"

    def add_arguments(self, parser):
        parser.add_argument("--product-type", action="append", default=[], help="Тип товара (можно несколько раз)")
        parser.add_argument("--category", help="Slug категории (включая подкатегории)")
        parser.add_argument("--ids", help="Явный список id товаров через запятую")
        parser.add_argument("--limit", type=int, required=True, help="Максимум товаров за запуск")
        parser.add_argument("--batch-size", type=int, default=20)
        parser.add_argument("--batch-delay", type=float, default=0, help="Пауза между батчами, сек")
        parser.add_argument(
            "--wait",
            action="store_true",
            help="Ждать завершения батча перед следующим и проверять ошибки",
        )
        parser.add_argument("--wait-timeout", type=int, default=1800, help="Таймаут ожидания батча, сек")
        parser.add_argument(
            "--max-failures",
            type=int,
            default=3,
            help="С --wait: остановиться, если в батче упало больше N",
        )
        parser.add_argument("--missing-description", action="store_true", help="Только товары без описания")
        parser.add_argument(
            "--source-changed",
            action="store_true",
            help="Только AI-товары, у которых после обработки изменился исходник (нужен --force)",
        )
        parser.add_argument(
            "--include-processed",
            action="store_true",
            help="Не пропускать товары с готовым/активным AI-логом",
        )
        parser.add_argument("--processing-type", default="full", choices=["full", "description_only"])
        parser.add_argument("--auto-apply", action="store_true", help="Сразу применять результат (осознанно!)")
        parser.add_argument("--force", action="store_true", help="Перегенерировать даже обработанные")
        parser.add_argument("--no-index-vectors", action="store_true", help="Не переиндексировать рекомендации")
        parser.add_argument("--dry-run", action="store_true", help="Только показать выборку и оценку стоимости")

    def handle(self, *args, **options):
        if options["limit"] <= 0 or options["batch_size"] <= 0:
            raise CommandError("--limit и --batch-size должны быть > 0")
        product_ids = list(self._queryset(options).values_list("id", flat=True)[: options["limit"]])
        estimate = self._estimate_cost(product_ids)
        self.stdout.write(
            f"Выбрано товаров: {len(product_ids)}; оценка стоимости ≈ ${estimate:.2f}; "
            f"auto_apply={options['auto_apply']}, force={options['force']}"
        )
        self.stdout.write(f"Первые id: {product_ids[:20]}")
        if options["dry_run"] or not product_ids:
            self.stdout.write("Dry run — ничего не поставлено." if options["dry_run"] else "Нечего ставить.")
            return

        totals = {"queued": 0, "apply_queued": 0, "skipped": 0, "failed": 0}
        batch_size = options["batch_size"]
        for start in range(0, len(product_ids), batch_size):
            batch = product_ids[start:start + batch_size]
            log_ids = []
            for product_id in batch:
                log, action = enqueue_or_apply_product_ai(
                    product_id=product_id,
                    auto_apply=options["auto_apply"],
                    force=options["force"],
                    index_vectors=not options["no_index_vectors"],
                    processing_type=options["processing_type"],
                )
                totals[action] += 1
                if action == "queued":
                    log_ids.append(log.id)
            self.stdout.write(
                f"Батч {start // batch_size + 1}: поставлено {len(log_ids)} из {len(batch)}"
            )
            if options["wait"] and log_ids:
                failed = self._wait_for_batch(log_ids, options["wait_timeout"])
                totals["failed"] += failed
                if failed > options["max_failures"]:
                    self.stdout.write(self.style.ERROR(
                        f"Остановка: в батче упало {failed} (> {options['max_failures']}). "
                        "Разберите error_message в AI → Логи перед продолжением."
                    ))
                    break
            if options["batch_delay"] and start + batch_size < len(product_ids):
                time.sleep(options["batch_delay"])
        self.stdout.write(self.style.SUCCESS(f"Итого: {totals}"))

    def _queryset(self, options):
        qs = Product.objects.all()
        if options["ids"]:
            ids = [int(value) for value in options["ids"].split(",") if value.strip()]
            qs = qs.filter(id__in=ids)
        if options["product_type"]:
            qs = qs.filter(product_type__in=options["product_type"])
        if options["category"]:
            category = Category.objects.filter(slug=options["category"]).first()
            if category is None:
                raise CommandError(f"Категория {options['category']} не найдена")
            qs = qs.filter(category_id__in=self._category_tree_ids(category))
        if options["missing_description"]:
            qs = qs.filter(Q(description__isnull=True) | Q(description=""))
        if options["source_changed"]:
            qs = qs.filter(external_data__has_key=SOURCE_CHANGED_KEY)
        if not (options["include_processed"] or options["force"]):
            done = AIProcessingLog.objects.filter(
                product_id=OuterRef("pk"),
                processing_type=options["processing_type"],
                status__in=_DONE_STATUSES,
            )
            qs = qs.exclude(Exists(done))
        return qs.order_by("id")

    @staticmethod
    def _category_tree_ids(category):
        ids, frontier = {category.id}, [category.id]
        while frontier:
            frontier = list(
                Category.objects.filter(parent_id__in=frontier).exclude(id__in=ids).values_list("id", flat=True)
            )
            ids.update(frontier)
        return ids

    @staticmethod
    def _estimate_cost(product_ids):
        total = Decimal("0")
        types = Product.objects.filter(id__in=product_ids).values_list("product_type", flat=True)
        averages = {}
        for product_type in types:
            if product_type not in averages:
                avg = AIProcessingLog.objects.filter(
                    product__product_type=product_type, cost_usd__gt=0
                ).aggregate(value=Avg("cost_usd"))["value"]
                averages[product_type] = (
                    Decimal(str(avg)) if avg else _FALLBACK_COST_USD.get(product_type, _DEFAULT_COST_USD)
                )
            total += averages[product_type]
        return total

    def _wait_for_batch(self, log_ids, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not AIProcessingLog.objects.filter(id__in=log_ids, status__in=ACTIVE_AI_LOG_STATUSES).exists():
                break
            time.sleep(10)
        else:
            self.stdout.write(self.style.WARNING("Таймаут ожидания батча; незавершённые логи считаются ошибками."))
        return AIProcessingLog.objects.filter(
            id__in=log_ids,
            status__in=[AIProcessingStatus.FAILED, *ACTIVE_AI_LOG_STATUSES],
        ).count()
