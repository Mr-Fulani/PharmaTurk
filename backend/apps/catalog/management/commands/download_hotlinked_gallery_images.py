"""Фото галерей, которые грузятся прямо с сайта продавца (dry-run по умолчанию).

Строка галереи с внешним image_url и пустым image_file: своей копии нет, страница
товара вставляет адрес продавца в <img>, а его CDN отвечает 403 на запросы со страниц
mudaroba.com. Команда скачивает файл в наше хранилище (image_file) — сериализаторы
отдают файл раньше image_url. Сам image_url не меняется: по нему повторный парсинг
узнаёт строку и не качает фото заново.

    manage.py download_hotlinked_gallery_images                    # отчёт CSV, без изменений
    manage.py download_hotlinked_gallery_images --host img-lcwaikiki.mncdn.com --apply
    manage.py download_hotlinked_gallery_images --host static.zara.net --zara-via-proxy --apply

Фото Zara (static.zara.net) без --zara-via-proxy не скачиваются: прокси платный,
запуск только с согласия владельца.
"""
import csv
import os
import uuid
from collections import Counter
from urllib.parse import urlparse

import requests
from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from apps.catalog.management.commands.repair_broken_media import _is_gallery_row
from apps.catalog.signals import is_internal_storage_url
from apps.catalog.utils.parser_media_handler import DEFAULT_MEDIA_USER_AGENT

PROXY_ONLY_HOSTS = ("static.zara.net",)


def gallery_models():
    for model in apps.get_app_config("catalog").get_models():
        names = {f.name for f in model._meta.concrete_fields}
        if not model._meta.proxy and {"image_url", "image_file"} <= names and _is_gallery_row(model):
            yield model


def fetch_image(url, proxies=None, verify=True):
    """(ContentFile, "") или (None, причина отказа)."""
    try:
        response = requests.get(
            url, timeout=20, headers={"User-Agent": DEFAULT_MEDIA_USER_AGENT},
            proxies=proxies, verify=verify,
        )
    except requests.RequestException as exc:
        return None, f"error:{type(exc).__name__}"
    if response.status_code != 200:
        return None, f"http_{response.status_code}"
    content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if not content_type.startswith("image/") or not response.content:
        return None, f"not_image:{content_type}"
    ext = os.path.splitext(urlparse(url).path)[1].lower() or ".jpg"
    return ContentFile(response.content, name=f"{uuid.uuid4().hex[:12]}{ext}"), ""


class Command(BaseCommand):
    help = "Фото галерей с адресом продавца без своей копии: скачать в хранилище (по умолчанию dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Скачать (иначе только отчёт).")
        parser.add_argument("--host", default="", help="Только этот хост источника, напр. img-lcwaikiki.mncdn.com.")
        parser.add_argument(
            "--zara-via-proxy", action="store_true",
            help="Качать фото static.zara.net через SCRAPER_PROXY_URL (платный прокси — с согласия владельца).",
        )
        parser.add_argument("--report", default="", help="Путь CSV-отчёта (по умолчанию /tmp/...).")

    def handle(self, *args, **options):
        apply = options["apply"]
        host_filter = options["host"].strip().lower()
        report_path = options["report"] or f"/tmp/hotlinked_gallery_{timezone.now():%Y%m%d_%H%M%S}.csv"

        proxies, verify = None, True
        if options["zara_via_proxy"]:
            proxy_url = str(getattr(settings, "SCRAPER_PROXY_URL", "") or "").strip()
            if not proxy_url:
                raise CommandError("--zara-via-proxy: SCRAPER_PROXY_URL не задан.")
            proxies = {"http": proxy_url, "https": proxy_url}
            verify = str(getattr(settings, "SCRAPER_PROXY_CA_BUNDLE", "") or "").strip() or True

        rows = []
        for model in gallery_models():
            queryset = (
                model._base_manager.filter(Q(image_file="") | Q(image_file__isnull=True))
                .exclude(image_url="")
                .values_list("pk", "image_url")
            )
            for pk, url in queryset.iterator(chunk_size=2000):
                host = urlparse(url).netloc.lower()
                if not host or is_internal_storage_url(url) or (host_filter and host != host_filter):
                    continue
                rows.append({"model": model, "pk": pk, "host": host, "image_url": url, "result": "", "image_file": ""})

        for row in rows:
            via_proxy = row["host"] in PROXY_ONLY_HOSTS
            if via_proxy and not proxies:
                row["result"] = "needs_proxy"
            elif not apply:
                row["result"] = "would_download"
            else:
                self._download(row, proxies if via_proxy else None, verify if via_proxy else True)

        counts = Counter((row["host"], row["result"]) for row in rows)
        self.stdout.write(f"{'APPLY' if apply else 'DRY-RUN'}: строк без своей копии={len(rows)}")
        for (host, result), count in sorted(counts.items()):
            self.stdout.write(f"  {host}: {result}={count}")

        with open(report_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["model", "pk", "host", "image_url", "result", "image_file"])
            for row in rows:
                writer.writerow([
                    row["model"]._meta.label, row["pk"], row["host"], row["image_url"],
                    row["result"], row["image_file"],
                ])
        self.stdout.write(f"Отчёт: {report_path}")

    def _download(self, row, proxies, verify):
        instance = row["model"]._base_manager.get(pk=row["pk"])
        file_obj, reason = fetch_image(row["image_url"], proxies=proxies, verify=verify)
        if file_obj is None:
            row["result"] = f"failed:{reason}"
            return
        instance.image_file = file_obj
        try:
            instance.save(update_fields=["image_file"])
        except Exception as exc:
            row["result"] = f"failed:save:{type(exc).__name__}"
            return
        row["result"] = "downloaded"
        row["image_file"] = instance.image_file.name
