"""
Management command: sync_vk_catalog

Сверяет каталог ВК с YML-фидом сайта (docs/VK_YML_FEED.md).

  python manage.py sync_vk_catalog            # только отчёт, в ВК ничего не меняется
  python manage.py sync_vk_catalog --apply    # настоящий запуск

Меняет публичную витрину ВК — --apply только с согласия владельца.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.services.vk_catalog_sync import run_catalog_sync


class Command(BaseCommand):
    help = "Сверяет каталог ВК с фидом сайта. Без --apply только показывает, что изменится."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Выполнить изменения в ВК. Без флага — только отчёт.",
        )
        parser.add_argument(
            "--max-delete-share",
            type=float,
            default=None,
            metavar="ДОЛЯ",
            help="Порог остановки на этот запуск, от 0 до 1. По умолчанию — VK_SYNC_MAX_DELETE_SHARE.",
        )

    def handle(self, *args, **options):
        share = options["max_delete_share"]
        if share is not None and not 0 <= share <= 1:
            raise CommandError("--max-delete-share — доля от 0 до 1, например 0.5")

        report = run_catalog_sync(apply=options["apply"], max_delete_share=share)
        self.stdout.write(report.text())
        if report.stop_reason:
            raise CommandError(report.stop_reason)
