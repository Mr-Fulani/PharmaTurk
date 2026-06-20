"""Переносит медиа товаров в новую раскладку: одна папка на товар
products/{категория}/{slug-товара}/{парсер}-{бренд}-{цвет}-{роль}-{hash}.ext

Старая раскладка раскидывала файлы по products/{type}/main|gallery|variants/...
Безопасный порядок на запись: copy_object(old→new) → проверка head → UPDATE
поля в БД (минуя сигналы) → delete старого. Прерывание не ломает сайт: БД всегда
указывает на существующий объект. Идемпотентно (уже новые — пропускаются).

    python manage.py migrate_product_media_layout --dry-run
    python manage.py migrate_product_media_layout --limit 50
    python manage.py migrate_product_media_layout
"""
import os
from urllib.parse import urlparse

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import FileField

from apps.catalog.utils.r2_utils import get_r2_client

# Старые «роль-папки», по которым опознаём ещё не перенесённый файл.
OLD_MARKERS = ("/main/", "/gallery/", "/variants/")


class Command(BaseCommand):
    help = "Перенос медиа товаров в одну папку на товар products/{категория}/{slug}/."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        limit = opts["limit"]
        client = get_r2_client()
        bucket = settings.R2_BUCKET_NAME
        public = (getattr(settings, "R2_PUBLIC_URL", "") or "").rstrip("/")

        moved = skipped = failed = 0

        for model in apps.get_app_config("catalog").get_models():
            file_fields = [
                f for f in model._meta.get_fields()
                if isinstance(f, FileField)
            ]
            if not file_fields:
                continue
            for obj in model.objects.iterator():
                for f in file_fields:
                    fieldfile = getattr(obj, f.name, None)
                    old_key = getattr(fieldfile, "name", "") or ""
                    if not old_key or not old_key.startswith("products/"):
                        continue
                    if not any(m in ("/" + old_key) for m in OLD_MARKERS):
                        continue  # уже новая раскладка
                    # новый ключ через upload_to модели (со свежим hash)
                    try:
                        new_key = f.upload_to(obj, os.path.basename(old_key))
                    except Exception as exc:
                        failed += 1
                        self.stderr.write(f"upload_to fail {model.__name__}.{f.name} #{obj.pk}: {exc}")
                        continue
                    if not new_key or new_key == old_key or any(m in ("/" + new_key) for m in OLD_MARKERS):
                        skipped += 1
                        continue
                    if dry:
                        moved += 1
                        if moved <= 5:
                            self.stdout.write(f"  {old_key}\n   → {new_key}")
                        continue
                    try:
                        client.copy_object(
                            Bucket=bucket,
                            CopySource={"Bucket": bucket, "Key": old_key},
                            Key=new_key,
                        )
                        client.head_object(Bucket=bucket, Key=new_key)
                    except Exception as exc:
                        failed += 1
                        self.stderr.write(f"copy fail {old_key}: {exc}")
                        continue
                    # обновляем БД минуя сигналы: file-поле + парный url-поле
                    updates = {f.name: new_key}
                    field_names = {fld.name for fld in model._meta.get_fields()}
                    url_field = None
                    if f.name.endswith("_file"):
                        for cand in (f.name[:-5] + "_url", f.name[:-5]):  # image_url / main_image
                            if cand in field_names:
                                url_field = cand
                                break
                    # url переписываем только если он указывал на ПЕРЕМЕЩАЕМЫЙ R2-файл
                    # (внешние source-ссылки, напр. floimages, не трогаем).
                    if url_field and public:
                        cur_url = getattr(obj, url_field, "") or ""
                        if old_key in cur_url:
                            updates[url_field] = f"{public}/{new_key}"
                    try:
                        model.objects.filter(pk=obj.pk).update(**updates)
                        client.delete_object(Bucket=bucket, Key=old_key)
                        moved += 1
                    except Exception as exc:
                        failed += 1
                        self.stderr.write(f"db/delete fail {old_key}: {exc}")
                        continue
                if limit and moved >= limit and not dry:
                    break
            if limit and moved >= limit and not dry:
                break

        verb = "будет перенесено" if dry else "перенесено"
        self.stdout.write(self.style.SUCCESS(
            f"{verb}: {moved}; пропущено (уже новые): {skipped}; ошибок: {failed}"
        ))
