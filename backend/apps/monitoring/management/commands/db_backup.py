import json

from django.core.management.base import BaseCommand, CommandError

from apps.monitoring.tasks import check_database_backup, run_database_backup


class Command(BaseCommand):
    help = (
        "Снять копию базы во внешний бакет прямо сейчас (как ночная задача). "
        "С --check — проверить последнюю копию. См. docs/DB_BACKUP.md."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Проверить последнюю копию вместо создания новой.",
        )

    def handle(self, *args, check=False, **options):
        result = check_database_backup() if check else run_database_backup()
        self.stdout.write(json.dumps(result, ensure_ascii=False, default=str))
        if result["status"] != "ok":
            raise CommandError(f"status={result['status']}")
