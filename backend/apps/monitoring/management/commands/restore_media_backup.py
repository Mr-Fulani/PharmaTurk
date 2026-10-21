from django.core.management.base import BaseCommand, CommandError

from apps.monitoring import media_backup
from apps.monitoring.db_backup import BackupError


class Command(BaseCommand):
    help = (
        "Вернуть из копии медиа (бакет бэкапов, media/) файл или все файлы под префиксом. "
        "Без --apply — только список. См. docs/DB_BACKUP.md, «Копия медиа»."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="Ключ файла или префикс в бакете медиа: marketing/banners/ или pages/og.webp")
        parser.add_argument("--apply", action="store_true", help="Записать файлы в бакет медиа.")
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Заменить и файлы, которые на месте, но другого размера (иначе — только пропавшие).",
        )

    def handle(self, *args, path, apply=False, overwrite=False, **options):
        try:
            plan = media_backup.restore_plan(path)
        except BackupError as exc:
            raise CommandError(str(exc)) from exc
        labels = {"missing": "нет в бакете медиа", "changed": "другой размер", "present": "на месте"}
        for item in plan:
            self.stdout.write(f"{labels[item['state']]}: {item['key']} ({item['size']} байт)")
        todo = [
            item for item in plan if item["state"] == "missing" or (overwrite and item["state"] == "changed")
        ]
        if not apply:
            self.stdout.write(f"Будет возвращено файлов: {len(todo)} из {len(plan)}. Запуск с --apply запишет их.")
            return
        restored = media_backup.restore(plan, overwrite=overwrite)
        self.stdout.write(self.style.SUCCESS(f"Возвращено файлов: {len(restored)}"))
