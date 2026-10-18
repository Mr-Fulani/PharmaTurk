"""Закрыть записи AI-модерации, у которых не осталось причин для проверки.

Нужна после исправлений валидатора: например, лог ушёл в модерацию только из-за
запрещённого атрибута, а теперь такой атрибут просто не применяется. Закрытие
идёт тем же путём, что и ручное «Проверено — применить к товару»
(ContentGenerator.apply_log_to_product): применяются разрешённые поля, лог
становится approved, запись очереди получает resolved_at. То же делает кнопка
в админке: AI → AI-прогоны → «Закрыть решённые записи модерации».

    manage.py close_resolved_ai_moderation --dry-run
    manage.py close_resolved_ai_moderation --product-type supplements --limit 50
"""

from django.core.management.base import BaseCommand

from apps.ai.services.bulk_ops import close_resolved_moderation


class Command(BaseCommand):
    help = "Закрыть записи AI-модерации без оставшихся причин (тем же путём, что ручное одобрение)"

    def add_arguments(self, parser):
        parser.add_argument("--product-type", action="append", default=[])
        parser.add_argument("--limit", type=int, default=0, help="Максимум записей (0 — без ограничения)")
        parser.add_argument("--dry-run", action="store_true", help="Только показать, что будет закрыто")

    def handle(self, *args, **options):
        result = close_resolved_moderation(
            product_types=options["product_type"],
            limit=options["limit"],
            dry_run=options["dry_run"],
            report=self._report,
        )
        verb = "будет закрыто" if options["dry_run"] else "закрыто"
        self.stdout.write(self.style.SUCCESS(
            f"Итого: {verb} {result['closed']}, осталось на модерации {result['kept']}, "
            f"ошибок {result['failed']}"
        ))

    def _report(self, message, warning=False):
        self.stdout.write(self.style.WARNING(message) if warning else message)
