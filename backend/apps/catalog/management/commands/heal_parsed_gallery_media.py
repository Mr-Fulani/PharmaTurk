"""Разовый хил галереи: переносит строки, застрявшие в products/parsed/, в
читаемый image_file доменного пути.

Нужен после фикса сигнала _auto_download_image_url_to_file (раньше «облегчённые»
домены — Accessory/Headwear/Underwear/Tableware/Incense/Sports/AutoPart — не
переносили parsed→читаемый). Достаточно пере-сохранить строку: pre_save сигнал
сам перенесёт файл и перепишет image_url.

Строки, у которых parsed-файла уже нет в хранилище (битые 404), пропускаются —
их лечит повторный парсинг товара.

    docker compose -p mudaroba exec backend poetry run python manage.py heal_parsed_gallery_media --dry-run
    docker compose -p mudaroba exec backend poetry run python manage.py heal_parsed_gallery_media
"""
from urllib.parse import urlparse

from django.apps import apps as django_apps
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from apps.catalog.signals import _normalize_storage_key_for_file_field


class Command(BaseCommand):
    help = "Переносит parsed-галерею в читаемый image_file (после фикса сигнала)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Только показать, ничего не сохранять.")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        healed = missing = 0

        for model in django_apps.get_app_config("catalog").get_models():
            field_names = {f.name for f in model._meta.get_fields()}
            if not ({"image_url", "image_file"} <= field_names):
                continue

            qs = model.objects.filter(
                image_url__contains="/products/parsed/", image_file=""
            )
            for obj in qs.iterator():
                key = _normalize_storage_key_for_file_field(urlparse(obj.image_url).path)
                if not key or not default_storage.exists(key):
                    missing += 1
                    continue
                if dry:
                    healed += 1
                    continue
                obj.save()  # pre_save сигнал переносит parsed → читаемый
                healed += 1

        verb = "будет перенесено" if dry else "перенесено"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb}: {healed}; пропущено битых (parsed-файл отсутствует, нужен ре-скрейп): {missing}"
            )
        )
