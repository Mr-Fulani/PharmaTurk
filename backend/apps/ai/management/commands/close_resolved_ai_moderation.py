"""Закрыть записи AI-модерации, у которых не осталось причин для проверки.

Нужна после исправлений валидатора: например, лог ушёл в модерацию только из-за
запрещённого атрибута, а теперь такой атрибут просто не применяется. Закрытие
идёт тем же путём, что и ручное «Проверено — применить к товару»
(ContentGenerator.apply_log_to_product): применяются разрешённые поля, лог
становится approved, запись очереди получает resolved_at.

    manage.py close_resolved_ai_moderation --dry-run
    manage.py close_resolved_ai_moderation --product-type supplements --limit 50
"""

from django.core.management.base import BaseCommand

from apps.ai.models import AIModerationQueue, AIProcessingStatus
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.quality_checker import get_moderation_reasons


class Command(BaseCommand):
    help = "Закрыть записи AI-модерации без оставшихся причин (тем же путём, что ручное одобрение)"

    def add_arguments(self, parser):
        parser.add_argument("--product-type", action="append", default=[])
        parser.add_argument("--limit", type=int, default=0, help="Максимум записей (0 — без ограничения)")
        parser.add_argument("--dry-run", action="store_true", help="Только показать, что будет закрыто")

    def handle(self, *args, **options):
        queue = (
            AIModerationQueue.objects.filter(
                resolved_at__isnull=True,
                log_entry__status=AIProcessingStatus.MODERATION,
            )
            .select_related("log_entry__product")
            .order_by("id")
        )
        if options["product_type"]:
            queue = queue.filter(log_entry__product__product_type__in=options["product_type"])

        generator = None if options["dry_run"] else ContentGenerator()
        closed = kept = failed = 0
        for task in queue.iterator():
            if options["limit"] and closed >= options["limit"]:
                break
            log = task.log_entry
            reasons = get_moderation_reasons(log)
            if reasons:
                kept += 1
                continue
            if options["dry_run"]:
                closed += 1
                self.stdout.write(f"закрыть: лог {log.id}, товар {log.product_id}, причина в очереди «{task.reason}»")
                continue
            try:
                generator.apply_log_to_product(log)
            except ValueError as exc:
                failed += 1
                self.stdout.write(self.style.WARNING(f"лог {log.id}: {exc}"))
                continue
            log.refresh_from_db()
            if log.status == AIProcessingStatus.APPROVED:
                closed += 1
                self.stdout.write(f"закрыт: лог {log.id}, товар {log.product_id}")
            else:
                kept += 1
        verb = "будет закрыто" if options["dry_run"] else "закрыто"
        self.stdout.write(self.style.SUCCESS(
            f"Итого: {verb} {closed}, осталось на модерации {kept}, ошибок {failed}"
        ))
