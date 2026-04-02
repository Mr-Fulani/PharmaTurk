"""
Management command: download_all_media

Идемпотентная команда для одноразового «прогрева» R2-хранилища:
скачивает все внешние медиафайлы (pinterest, trendyol и др.) для
карточек товаров, отзывов и услуг.

Использование:
    # Сухой прогон — показывает что будет скачано, ничего не делает
    docker exec -it pharmaturk-backend-1 poetry run python manage.py download_all_media --dry-run

    # Скачать всё
    docker exec -it pharmaturk-backend-1 poetry run python manage.py download_all_media

    # Только конкретные разделы
    docker exec -it pharmaturk-backend-1 poetry run python manage.py download_all_media --only products
    docker exec -it pharmaturk-backend-1 poetry run python manage.py download_all_media --only testimonials
    docker exec -it pharmaturk-backend-1 poetry run python manage.py download_all_media --only services

    # Принудительная перезакачка (даже если файл уже есть)
    docker exec -it pharmaturk-backend-1 poetry run python manage.py download_all_media --force

Разделы (--only):
    products       — все ProductImage, доменные *ProductImage и *VariantImage
    main_images    — главные изображения Product, Clothing, Jewelry и т.д.
    testimonials   — TestimonialMedia изображения
    services       — ServiceImage
    all            — всё (по умолчанию)
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


# ── Вспомогательные функции ──────────────────────────────────────────────────

def _is_internal(url: str, r2_public: str) -> bool:
    """Проверить что URL уже из нашего CDN/R2."""
    if not url:
        return False
    if r2_public and url.startswith(r2_public):
        return True
    from urllib.parse import urlparse
    path = urlparse(url).path
    return path.startswith("/media/") or path.startswith("/products/")


def _download(url: str, timeout: int = 15):
    """Скачать по URL, вернуть ContentFile или None."""
    import os, uuid, requests
    from urllib.parse import urlparse
    from django.core.files.base import ContentFile
    try:
        resp = requests.get(url, stream=True, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (compatible; Mudaroba/1.0)"
        })
        if resp.status_code == 200:
            ext = os.path.splitext(urlparse(url).path)[1].lower() or ".jpg"
            name = f"{uuid.uuid4().hex[:12]}{ext}"
            return ContentFile(resp.content, name=name)
        logger.warning("HTTP %s fetching %s", resp.status_code, url)
    except Exception as e:
        logger.warning("Download error %s: %s", url, e)
    return None


def _set_file(instance, field_attr: str, url: str, r2_public: str, dry_run: bool, force: bool, label: str, stdout):
    """
    Общая логика: скачать url → записать в instance.<field_attr>.
    Возвращает: 'downloaded' | 'skipped' | 'error' | 'internal'
    """
    if _is_internal(url, r2_public):
        return "internal"
    field_val = getattr(instance, field_attr, None)
    has_file = field_val and getattr(field_val, "name", None)
    if has_file and not force:
        return "skipped"
    stdout.write(f"  ⬇  {label}: {url[:80]}")
    if dry_run:
        return "downloaded"
    file_obj = _download(url)
    if not file_obj:
        stdout.write(f"  ❌  {label}: не удалось скачать")
        return "error"
    if force and has_file:
        from apps.catalog.signals import delete_file_from_storage
        delete_file_from_storage(field_val)
    setattr(instance, field_attr, file_obj)
    return "downloaded"


# ── Обобщённый обработчик для любой *ProductImage-модели ────────────────────

def _process_image_qs(qs, url_attr, file_attr, r2_public, dry_run, force, sync_internal, label_tpl, stdout, stats):
    from urllib.parse import urlparse
    for obj in qs.iterator(chunk_size=200):
        url = getattr(obj, url_attr, "") or ""
        if not url:
            stats["skipped"] += 1
            continue
        pk = obj.pk
        label = label_tpl.format(pk=pk)

        # Если URL уже на нашем CDN — синхронизируем путь в file-поле (без скачивания)
        if _is_internal(url, r2_public):
            if sync_internal:
                path = urlparse(url).path.lstrip("/")
                if path:
                    if dry_run:
                        stdout.write(f"  🔗  {label}: sync {path}")
                        stats["downloaded"] += 1
                    else:
                        try:
                            setattr(obj, file_attr, path)
                            obj.save(update_fields=[file_attr])
                            stdout.write(f"  🔗  {label}: синхронизировано → {path}")
                            stats["downloaded"] += 1
                        except Exception as e:
                            stdout.write(f"  ❌  {label}: ошибка sync — {e}")
                            stats["errors"] += 1
                else:
                    stats["skipped"] += 1
            else:
                stats["skipped"] += 1
            continue

        result = _set_file(obj, file_attr, url, r2_public, dry_run, force, label, stdout)
        if result == "downloaded":
            if not dry_run:
                try:
                    obj.save(update_fields=[file_attr])
                    stdout.write(f"  ✅  {label}: сохранено")
                except Exception as e:
                    stdout.write(f"  ❌  {label}: ошибка сохранения — {e}")
                    stats["errors"] += 1
                    continue
            stats["downloaded"] += 1
        elif result == "error":
            stats["errors"] += 1
        else:
            stats["skipped"] += 1


class Command(BaseCommand):
    help = "Скачивает медиафайлы товаров/отзывов/услуг из внешних URL на R2"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Только показать, не скачивать")
        parser.add_argument("--force", action="store_true", help="Перезакачать даже если файл уже есть")
        parser.add_argument(
            "--only",
            choices=["products", "main_images", "testimonials", "services", "categories", "brands", "all"],
            default="all",
            help="Раздел для обработки (по умолчанию: all)",
        )
        parser.add_argument("--limit", type=int, default=0, help="Ограничить кол-во записей (0 = без лимита)")
        parser.add_argument(
            "--sync-internal",
            action="store_true",
            help=(
                "Для записей где URL уже на нашем CDN (cdn.mudaroba.com) но "
                "image_file пустой — проставить путь из URL в image_file без скачивания. "
                "Используется для синхронизации legacy данных."
            ),
        )

    def handle(self, *args, **options):
        from django.conf import settings

        dry_run = options["dry_run"]
        force = options["force"]
        only = options["only"]
        limit = options["limit"]
        sync_internal = options["sync_internal"]

        r2_public = (getattr(settings, "R2_CONFIG", {}).get("public_url", "") or "").rstrip("/")
        mode_label = "[DRY-RUN] " if dry_run else ""

        stats = {"downloaded": 0, "skipped": 0, "errors": 0}

        def section(name):
            return only in ("all", name)

        # ── 1. Галереи товаров (image_url → image_file) ──────────────────────
        if section("products"):
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Галереи товаров ==="))
            self._process_galleries(r2_public, dry_run, force, sync_internal, limit, stats)

        # ── 2. Главные изображения товаров (main_image → main_image_file) ───
        if section("main_images"):
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Главные изображения товаров ==="))
            self._process_main_images(r2_public, dry_run, force, sync_internal, limit, stats)

        # ── 3. Отзывы (TestimonialMedia) ─────────────────────────────────────
        if section("testimonials"):
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Медиа отзывов ==="))
            self._process_testimonials(r2_public, dry_run, force, limit, stats)

        # ── 4. Услуги (ServiceImage) ─────────────────────────────────────────
        if section("services"):
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Галерея услуг ==="))
            self._process_services(r2_public, dry_run, force, limit, stats)

        # ── 5. Категории ──────────────────────────────────────────────────────
        if section("categories"):
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Карточки категорий ==="))
            self._process_categories(r2_public, dry_run, force, limit, stats)

        # ── 6. Бренды ─────────────────────────────────────────────────────────
        if section("brands"):
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Карточки брендов ==="))
            self._process_brands(r2_public, dry_run, force, limit, stats)

        # ── Итог ─────────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"{mode_label}Готово: скачано={stats['downloaded']}, "
            f"пропущено={stats['skipped']}, ошибок={stats['errors']}"
        ))
        if dry_run:
            self.stdout.write("Для реального скачивания запустите без --dry-run")

    # ────────────────────────────────────────────────────────────────────────
    # Внутренние методы
    # ────────────────────────────────────────────────────────────────────────

    def _process_galleries(self, r2_public, dry_run, force, sync_internal, limit, stats):
        """Все *ProductImage и *VariantImage модели с image_url → image_file."""
        from apps.catalog.models import (
            ProductImage,
            ClothingProductImage, ClothingVariantImage,
            ElectronicsProductImage,
            FurnitureVariantImage,
            JewelryProductImage, JewelryVariantImage,
            ShoeProductImage, ShoeVariantImage,
            BookProductImage, BookVariantImage,
            TablewareProductImage, AccessoryProductImage,
            IncenseProductImage, SportsProductImage,
            AutoPartProductImage, HeadwearProductImage,
            UnderwearProductImage,
        )

        gallery_models = [
            (ProductImage,            "image_url", "image_file", "ProductImage#{pk}"),
            (ClothingProductImage,    "image_url", "image_file", "ClothingImg#{pk}"),
            (ClothingVariantImage,    "image_url", "image_file", "ClothingVariantImg#{pk}"),
            (ElectronicsProductImage, "image_url", "image_file", "ElectronicsImg#{pk}"),
            (FurnitureVariantImage,   "image_url", "image_file", "FurnitureVariantImg#{pk}"),
            (JewelryProductImage,     "image_url", "image_file", "JewelryImg#{pk}"),
            (JewelryVariantImage,     "image_url", "image_file", "JewelryVariantImg#{pk}"),
            (ShoeProductImage,        "image_url", "image_file", "ShoeImg#{pk}"),
            (ShoeVariantImage,        "image_url", "image_file", "ShoeVariantImg#{pk}"),
            (BookProductImage,        "image_url", "image_file", "BookImg#{pk}"),
            (BookVariantImage,        "image_url", "image_file", "BookVariantImg#{pk}"),
            (TablewareProductImage,   "image_url", "image_file", "TablewareImg#{pk}"),
            (AccessoryProductImage,   "image_url", "image_file", "AccessoryImg#{pk}"),
            (IncenseProductImage,     "image_url", "image_file", "IncenseImg#{pk}"),
            (SportsProductImage,      "image_url", "image_file", "SportsImg#{pk}"),
            (AutoPartProductImage,    "image_url", "image_file", "AutoPartImg#{pk}"),
            (HeadwearProductImage,    "image_url", "image_file", "HeadwearImg#{pk}"),
            (UnderwearProductImage,   "image_url", "image_file", "UnderwearImg#{pk}"),
        ]

        for Model, url_attr, file_attr, label_tpl in gallery_models:
            qs = Model.objects.exclude(**{url_attr: ""}).exclude(**{url_attr: None})
            if not force:
                qs = qs.filter(**{f"{file_attr}__in": ["", None]}) | qs.filter(**{f"{file_attr}__isnull": True})
            if limit:
                qs = qs[:limit]
            total = qs.count() if hasattr(qs, 'count') else "?"
            if total == 0 or total == "?":
                count_qs = Model.objects.exclude(**{url_attr: ""}).exclude(**{url_attr: None})
                if not force:
                    count_qs = count_qs.filter(**{f"{file_attr}__in": ["", None]}) | count_qs.filter(**{f"{file_attr}__isnull": True})
                real_total = count_qs.count()
                if real_total == 0:
                    self.stdout.write(f"  ✅  {Model.__name__}: все уже загружены")
                    continue
            self.stdout.write(f"  📦  {Model.__name__}: {total} записей для скачивания")
            _process_image_qs(
                qs, url_attr, file_attr, r2_public, dry_run, force,
                sync_internal, label_tpl, self.stdout, stats,
            )

    def _process_main_images(self, r2_public, dry_run, force, sync_internal, limit, stats):
        """Главные изображения товаров (main_image → main_image_file)."""
        from apps.catalog.models import Product, ClothingProduct, JewelryProduct

        main_img_models = [
            (Product,          "main_image", "main_image_file", "Product#{pk}"),
            (ClothingProduct,  "main_image", "main_image_file", "ClothingProduct#{pk}"),
            (JewelryProduct,   "main_image", "main_image_file", "JewelryProduct#{pk}"),
        ]

        for Model, url_attr, file_attr, label_tpl in main_img_models:
            qs = Model.objects.exclude(**{url_attr: ""}).exclude(**{url_attr: None})
            if not force:
                qs = qs.filter(**{f"{file_attr}__in": ["", None]}) | qs.filter(**{f"{file_attr}__isnull": True})
            if limit:
                qs = qs[:limit]
            total = qs.count() if hasattr(qs, 'count') else "?"
            self.stdout.write(f"  📦  {Model.__name__} (main_image): {total} записей")
            _process_image_qs(
                qs, url_attr, file_attr, r2_public, dry_run, force,
                sync_internal, label_tpl, self.stdout, stats,
            )

    def _process_testimonials(self, r2_public, dry_run, force, limit, stats):
        """TestimonialMedia: image (тип=image) и video_file (тип=video_file с прямой ссылкой)."""
        from apps.feedback.models import TestimonialMedia

        YOUTUBE_DOMAINS = ("youtube.com", "youtu.be", "vimeo.com")

        # Изображения в отзывах
        qs_images = TestimonialMedia.objects.filter(media_type="image")
        if not force:
            qs_images = qs_images.filter(image__in=["", None]) | qs_images.filter(image__isnull=True)
        if limit:
            qs_images = qs_images[:limit]

        self.stdout.write(f"  📦  TestimonialMedia (image): {qs_images.count()} записей")
        for obj in qs_images.iterator(chunk_size=100):
            # Изображение хранится в image-поле, URL может быть в video_url (исторически)
            url = obj.video_url or ""
            if not url or any(d in url for d in YOUTUBE_DOMAINS):
                stats["skipped"] += 1
                continue
            label = f"TestimonialMedia#{obj.pk}(image)"
            result = _set_file(obj, "image", url, r2_public, dry_run, force, label, self.stdout)
            if result == "downloaded":
                if not dry_run:
                    try:
                        obj.save(update_fields=["image"])
                        self.stdout.write(f"  ✅  {label}: сохранено")
                    except Exception as e:
                        self.stdout.write(f"  ❌  {label}: ошибка — {e}")
                        stats["errors"] += 1
                        continue
                stats["downloaded"] += 1
            elif result == "error":
                stats["errors"] += 1
            else:
                stats["skipped"] += 1

        # Файловые видео (не YouTube)
        qs_videos = TestimonialMedia.objects.filter(media_type__in=["video", "video_file"]).exclude(video_url__isnull=True).exclude(video_url="")
        if not force:
            qs_videos = qs_videos.filter(video_file__in=["", None]) | qs_videos.filter(video_file__isnull=True)
        if limit:
            qs_videos = qs_videos[:limit]

        self.stdout.write(f"  📦  TestimonialMedia (video_file): {qs_videos.count()} записей")
        for obj in qs_videos.iterator(chunk_size=100):
            url = obj.video_url or ""
            if not url or any(d in url for d in YOUTUBE_DOMAINS):
                stats["skipped"] += 1
                continue
            label = f"TestimonialMedia#{obj.pk}(video)"
            result = _set_file(obj, "video_file", url, r2_public, dry_run, force, label, self.stdout)
            if result == "downloaded":
                if not dry_run:
                    try:
                        obj.save(update_fields=["video_file"])
                        self.stdout.write(f"  ✅  {label}: сохранено")
                    except Exception as e:
                        self.stdout.write(f"  ❌  {label}: ошибка — {e}")
                        stats["errors"] += 1
                        continue
                stats["downloaded"] += 1
            elif result == "error":
                stats["errors"] += 1
            else:
                stats["skipped"] += 1

    def _process_services(self, r2_public, dry_run, force, limit, stats):
        """ServiceImage: image_url → image_file."""
        from apps.catalog.models import ServiceImage

        qs = ServiceImage.objects.exclude(image_url="").exclude(image_url=None)
        if not force:
            qs = qs.filter(image_file__in=["", None]) | qs.filter(image_file__isnull=True)
        if limit:
            qs = qs[:limit]

        self.stdout.write(f"  📦  ServiceImage: {qs.count()} записей")
        _process_image_qs(qs, "image_url", "image_file", r2_public, dry_run, force, False, "ServiceImage#{pk}", self.stdout, stats)

    def _process_categories(self, r2_public, dry_run, force, limit, stats):
        """
        Category: card_media_external_url → card_media.
        У категорий external_url имеет ПРИОРИТЕТ над файлом, поэтому после скачивания
        очищаем его, чтобы сайт переключился на R2.
        """
        from apps.catalog.models import Category
        from apps.catalog.signals import is_internal_storage_url

        qs = Category.objects.exclude(card_media_external_url="").exclude(card_media_external_url=None)
        if not force:
            # Обрабатываем те у кого файл нема или force
            qs = qs.filter(card_media__in=["", None]) | qs.filter(card_media__isnull=True)
        if limit:
            qs = qs[:limit]

        count = qs.count()
        self.stdout.write(f"  📦  Category (external_url): {count} записей")
        if count == 0:
            self.stdout.write("  ✅  Все уже загружены")
            return

        for obj in qs.iterator(chunk_size=50):
            url = obj.card_media_external_url
            if is_internal_storage_url(url):
                stats["skipped"] += 1
                continue
            label = f"Category#{obj.pk} '{obj.name[:30]}'"
            self.stdout.write(f"  ⬇  {label}: {url[:80]}")
            if dry_run:
                stats["downloaded"] += 1
                continue
            result = _set_file(obj, "card_media", url, r2_public, dry_run, force, label, self.stdout)
            if result == "downloaded":
                obj.card_media_external_url = ""  # переключаемся на R2
                try:
                    obj.save(update_fields=["card_media", "card_media_external_url"])
                    self.stdout.write(f"  ✅  {label}: сохранено, external_url очищен")
                    stats["downloaded"] += 1
                except Exception as e:
                    self.stdout.write(f"  ❌  {label}: ошибка — {e}")
                    stats["errors"] += 1
            elif result == "error":
                stats["errors"] += 1
            else:
                stats["skipped"] += 1

    def _process_brands(self, r2_public, dry_run, force, limit, stats):
        """
        Brand: card_media_external_url → card_media.
        Аналогично категориям, после скачивания очищаем external_url.
        """
        from apps.catalog.models import Brand
        from apps.catalog.signals import is_internal_storage_url

        qs = Brand.objects.exclude(card_media_external_url="").exclude(card_media_external_url=None)
        if not force:
            qs = qs.filter(card_media__in=["", None]) | qs.filter(card_media__isnull=True)
        if limit:
            qs = qs[:limit]

        count = qs.count()
        self.stdout.write(f"  📦  Brand (external_url): {count} записей")
        if count == 0:
            self.stdout.write("  ✅  Все уже загружены")
            return

        for obj in qs.iterator(chunk_size=50):
            url = obj.card_media_external_url
            if is_internal_storage_url(url):
                stats["skipped"] += 1
                continue
            label = f"Brand#{obj.pk} '{obj.name[:30]}'"
            self.stdout.write(f"  ⬇  {label}: {url[:80]}")
            if dry_run:
                stats["downloaded"] += 1
                continue
            result = _set_file(obj, "card_media", url, r2_public, dry_run, force, label, self.stdout)
            if result == "downloaded":
                obj.card_media_external_url = ""  # переключаемся на R2
                try:
                    obj.save(update_fields=["card_media", "card_media_external_url"])
                    self.stdout.write(f"  ✅  {label}: сохранено, external_url очищен")
                    stats["downloaded"] += 1
                except Exception as e:
                    self.stdout.write(f"  ❌  {label}: ошибка — {e}")
                    stats["errors"] += 1
            elif result == "error":
                stats["errors"] += 1
            else:
                stats["skipped"] += 1
