"""
Management command: download_banner_media

Одноразовый (и идемпотентный) прогон авто-скачивания медиафайлов баннеров
из внешних URL (Pinterest и др.) на R2-хранилище через pre_save-сигнал.

Использование:
    docker compose exec backend poetry run python manage.py download_banner_media
    docker compose exec backend poetry run python manage.py download_banner_media --dry-run
    docker compose exec backend poetry run python manage.py download_banner_media --banner-id 5
"""
import logging

from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Скачивает медиафайлы баннеров из внешних URL на R2"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать что будет скачано, не скачивая",
        )
        parser.add_argument(
            "--banner-id",
            type=int,
            default=None,
            help="Обработать только конкретный Banner.id",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Принудительно перезакачать даже если файл уже есть в R2",
        )

    def handle(self, *args, **options):
        from apps.catalog.models import BannerMedia
        from apps.catalog.signals import is_internal_storage_url, _download_url_to_file, _save_downloaded_file_to_storage

        dry_run = options["dry_run"]
        banner_id = options["banner_id"]
        force = options["force"]

        qs = BannerMedia.objects.select_related("banner")
        if banner_id:
            qs = qs.filter(banner_id=banner_id)

        total = qs.count()
        self.stdout.write(f"Найдено медиа-файлов баннеров: {total}")

        downloaded = 0
        skipped = 0
        errors = 0

        for media in qs.iterator():
            label = f"BannerMedia pk={media.pk} (banner #{media.banner_id}, тип={media.content_type})"

            # ── image ──────────────────────────────────────────────────────
            if media.content_type in ("image", "gif") and media.image_url:
                has_file = media.image and media.image.name
                if has_file and not force:
                    self.stdout.write(f"  ⏭  {label}: файл уже есть ({media.image.name}), пропускаем")
                    skipped += 1
                elif is_internal_storage_url(media.image_url):
                    self.stdout.write(f"  ⏭  {label}: URL уже внутренний ({media.image_url})")
                    skipped += 1
                else:
                    self.stdout.write(f"  ⬇  {label}: скачиваем {media.image_url} ...")
                    if not dry_run:
                        try:
                            if force and has_file:
                                # Очищаем старый файл перед перезакачкой
                                from apps.catalog.signals import delete_file_from_storage
                                delete_file_from_storage(media.image)
                                media.image = None

                            file_obj = _download_url_to_file(media.image_url)
                            if file_obj:
                                _save_downloaded_file_to_storage(media, "image", file_obj)
                                media.save(update_fields=["image"])
                                self.stdout.write(self.style.SUCCESS(f"  ✅  {label}: сохранено как {media.image.name}"))
                                downloaded += 1
                            else:
                                self.stdout.write(self.style.WARNING(f"  ❌  {label}: не смогли скачать"))
                                errors += 1
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"  ❌  {label}: ошибка — {e}"))
                            errors += 1
                    else:
                        self.stdout.write(f"     [dry-run] скачали бы {media.image_url}")
                        downloaded += 1

            # ── video ──────────────────────────────────────────────────────
            elif media.content_type == "video" and media.video_url:
                has_file = media.video_file and media.video_file.name
                if has_file and not force:
                    self.stdout.write(f"  ⏭  {label}: файл уже есть ({media.video_file.name}), пропускаем")
                    skipped += 1
                elif is_internal_storage_url(media.video_url):
                    self.stdout.write(f"  ⏭  {label}: URL уже внутренний ({media.video_url})")
                    skipped += 1
                else:
                    # Видео из YouTube/Vimeo не скачиваем — только прямые ссылки на файл
                    youtube_domains = ("youtube.com", "youtu.be", "vimeo.com")
                    if any(d in media.video_url for d in youtube_domains):
                        self.stdout.write(f"  ⏭  {label}: YouTube/Vimeo — пропускаем (embed)")
                        skipped += 1
                    else:
                        self.stdout.write(f"  ⬇  {label}: скачиваем видео {media.video_url} ...")
                        if not dry_run:
                            try:
                                file_obj = _download_url_to_file(media.video_url)
                                if file_obj:
                                    _save_downloaded_file_to_storage(media, "video_file", file_obj)
                                    media.save(update_fields=["video_file"])
                                    self.stdout.write(self.style.SUCCESS(f"  ✅  {label}: сохранено как {media.video_file.name}"))
                                    downloaded += 1
                                else:
                                    self.stdout.write(self.style.WARNING(f"  ❌  {label}: не смогли скачать"))
                                    errors += 1
                            except Exception as e:
                                self.stdout.write(self.style.ERROR(f"  ❌  {label}: ошибка — {e}"))
                                errors += 1
                        else:
                            self.stdout.write(f"     [dry-run] скачали бы {media.video_url}")
                            downloaded += 1

            # ── gif ────────────────────────────────────────────────────────
            elif media.gif_url:
                has_file = media.gif_file and media.gif_file.name
                if has_file and not force:
                    self.stdout.write(f"  ⏭  {label}: gif-файл уже есть ({media.gif_file.name}), пропускаем")
                    skipped += 1
                elif is_internal_storage_url(media.gif_url):
                    self.stdout.write(f"  ⏭  {label}: GIF URL уже внутренний")
                    skipped += 1
                else:
                    self.stdout.write(f"  ⬇  {label}: скачиваем GIF {media.gif_url} ...")
                    if not dry_run:
                        try:
                            file_obj = _download_url_to_file(media.gif_url)
                            if file_obj:
                                _save_downloaded_file_to_storage(media, "gif_file", file_obj)
                                media.save(update_fields=["gif_file"])
                                self.stdout.write(self.style.SUCCESS(f"  ✅  {label}: GIF сохранён"))
                                downloaded += 1
                            else:
                                self.stdout.write(self.style.WARNING(f"  ❌  {label}: не смогли скачать GIF"))
                                errors += 1
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"  ❌  {label}: ошибка — {e}"))
                            errors += 1
                    else:
                        self.stdout.write(f"     [dry-run] скачали бы GIF {media.gif_url}")
                        downloaded += 1

        # Итог
        self.stdout.write("")
        mode = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"{mode}Готово: скачано={downloaded}, пропущено={skipped}, ошибок={errors}"
        ))
        if dry_run:
            self.stdout.write("Для реального скачивания запустите без --dry-run")
