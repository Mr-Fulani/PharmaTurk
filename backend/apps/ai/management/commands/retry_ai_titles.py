"""Перегенерировать только названия БАДов, отклонённые валидатором.

Берёт открытые записи модерации БАДов, у которых среди причин есть
title_identity_lost или title_untranslated, и для каждого лога делает один
короткий запрос только за RU/EN-названием (тот же повтор, что в обработке:
ContentGenerator._retry_supplement_title, ≈$0.0002). Название записывается в
лог, только если проходит проверки. Товар команда не меняет: после неё
закрыть модерацию и применить названия — close_resolved_ai_moderation.
То же делает кнопка в админке: AI → AI-прогоны → «Перегенерировать
отклонённые названия».

    manage.py retry_ai_titles --limit 50 --dry-run
    manage.py retry_ai_titles --limit 50
    manage.py close_resolved_ai_moderation --product-type supplements --dry-run
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ai.services.bulk_ops import retry_supplement_titles


class Command(BaseCommand):
    help = "Перегенерировать только отклонённые названия БАДов на модерации (один короткий запрос на лог)"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, required=True, help="Максимум логов с повтором за запуск")
        parser.add_argument("--dry-run", action="store_true", help="Только показать логи; OpenAI не вызывается")

    def handle(self, *args, **options):
        if options["limit"] <= 0:
            raise CommandError("--limit должен быть > 0")
        result = retry_supplement_titles(
            limit=options["limit"], dry_run=options["dry_run"], report=self._report
        )
        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(
                f"Итого: к повтору {result['selected']} логов, оценка ≈ ${result['cost_usd']:.4f}"
            ))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Итого: исправлено {result['fixed']}, не исправлено {result['failed']}, "
            f"стоимость ${result['cost_usd']:.6f}. "
            "Дальше: close_resolved_ai_moderation --product-type supplements"
        ))

    def _report(self, message, warning=False):
        self.stdout.write(self.style.WARNING(message) if warning else message)
