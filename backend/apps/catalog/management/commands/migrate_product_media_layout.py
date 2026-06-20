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

        # 1. Собираем все ссылки на R2-файлы: old_key → [(model, pk, field_name)].
        #    Один физический файл может быть в нескольких полях (после дедупа
        #    main_image_file == файл галереи) — переносим его ОДИН раз, обновляя все.
        refs: dict[str, list] = {}
        for model in apps.get_app_config("catalog").get_models():
            file_fields = [f for f in model._meta.get_fields() if isinstance(f, FileField)]
            if not file_fields:
                continue
            names = [f.name for f in file_fields]
            for row in model.objects.values("pk", *names).iterator():
                for fname in names:
                    key = row.get(fname) or ""
                    if key.startswith("products/") and any(m in ("/" + key) for m in OLD_MARKERS):
                        refs.setdefault(key, []).append((model, row["pk"], fname))

        moved = skipped = failed = 0
        for old_key, holders in refs.items():
            # роль gallery приоритетнее main (gallery — «настоящий» файл, не ссылка)
            holders_sorted = sorted(holders, key=lambda h: 0 if "main" not in h[2] else 1)
            model0, pk0, field0 = holders_sorted[0]
            obj0 = model0.objects.filter(pk=pk0).first()
            if obj0 is None:
                skipped += 1
                continue
            try:
                new_key = model0._meta.get_field(field0).upload_to(obj0, os.path.basename(old_key))
            except Exception as exc:
                failed += 1
                self.stderr.write(f"upload_to fail {model0.__name__}.{field0} #{pk0}: {exc}")
                continue
            if not new_key or new_key == old_key or any(m in ("/" + new_key) for m in OLD_MARKERS):
                skipped += 1
                continue
            if dry:
                moved += 1
                if moved <= 6:
                    self.stdout.write(f"  {old_key}\n   → {new_key}  (полей: {len(holders)})")
                continue
            try:
                client.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": old_key}, Key=new_key)
                client.head_object(Bucket=bucket, Key=new_key)
            except Exception as exc:
                failed += 1
                self.stderr.write(f"copy fail {old_key}: {exc}")
                continue
            ok = True
            for model, pk, fname in holders:
                updates = {fname: new_key}
                fnames = {fld.name for fld in model._meta.get_fields()}
                url_field = None
                if fname.endswith("_file"):
                    for cand in (fname[:-5] + "_url", fname[:-5]):
                        if cand in fnames:
                            url_field = cand
                            break
                if url_field and public:
                    obj = model.objects.filter(pk=pk).first()
                    if obj and old_key in (getattr(obj, url_field, "") or ""):
                        updates[url_field] = f"{public}/{new_key}"
                try:
                    model.objects.filter(pk=pk).update(**updates)
                except Exception as exc:
                    ok = False
                    failed += 1
                    self.stderr.write(f"db update fail {model.__name__}#{pk}.{fname}: {exc}")
            if ok:
                try:
                    client.delete_object(Bucket=bucket, Key=old_key)
                except Exception:
                    pass
                moved += 1
            if limit and moved >= limit:
                break

        verb = "будет перенесено" if dry else "перенесено"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} файлов: {moved}; пропущено: {skipped}; ошибок: {failed}"
        ))
