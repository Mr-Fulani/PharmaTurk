"""
Management command: sync_vk_photos

Синхронизирует фотографии товаров из нашей БД в ВК Маркет через VK API.

Использование:
  python manage.py sync_vk_photos --dry-run          # сухой прогон
  python manage.py sync_vk_photos                    # все товары
  python manage.py sync_vk_photos --category shoes   # только обувь
  python manage.py sync_vk_photos --offer-id 1v9     # один товар

Требует в .env:
  VK_YML_API=<ключ сообщества>       # для загрузки фото/видео
  VK_USER_TOKEN=<пользовательский токен> # для market.get (group token не работает)
  VK_GROUP_ID=<ID группы>
Ссылка для получения VK_USER_TOKEN:
  https://oauth.vk.com/authorize?client_id=APP_ID&display=page
  &redirect_uri=https://oauth.vk.com/blank.html
  &scope=market,photos,video,offline&response_type=token&v=5.131
"""
from __future__ import annotations

from typing import Optional

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import Product
from apps.catalog.services.vk_market_sync import VKMarketSync

logger = logging.getLogger(__name__)

SITE_URL = "https://mudaroba.com"


def _resolve_url(raw: str) -> str:
    if not raw:
        return ""
    return raw if raw.startswith("http") else f"{SITE_URL}{raw}"


def collect_image_urls(prod: Product, variant=None, domain_item=None) -> list[str]:
    """
    Собирает все URL изображений для товара/варианта:
    1. Фото варианта (если есть)
    2. Фото доменного товара (ShoeProduct, ClothingProduct и т.д.)
    3. Фото базового Product
    """
    urls: list[str] = []
    seen: set[str] = set()

    def add(url: str):
        url = url.strip() if url else ""
        if url and url not in seen:
            urls.append(url)
            seen.add(url)

    # --- 1. Изображения варианта ---
    if variant:
        if getattr(variant, "main_image_file", None):
            add(f"{SITE_URL}{variant.main_image_file.url}")
        elif getattr(variant, "main_image", ""):
            add(_resolve_url(variant.main_image))

        if hasattr(variant, "images"):
            for vi in variant.images.all():
                add(vi.image_url or (
                    f"{SITE_URL}{vi.image_file.url}" if vi.image_file else ""
                ))

    # --- 2. Изображения доменного товара (ShoeProduct и т.п.) ---
    domain = domain_item if (domain_item and domain_item is not prod) else None
    if domain:
        if getattr(domain, "main_image", ""):
            add(_resolve_url(domain.main_image))
        elif getattr(domain, "main_image_file", None):
            add(f"{SITE_URL}{domain.main_image_file.url}")

        if hasattr(domain, "images"):
            for pi in domain.images.all():
                add(pi.image_url or (
                    f"{SITE_URL}{pi.image_file.url}" if pi.image_file else ""
                ))

    # --- 3. Изображения базового Product ---
    if getattr(prod, "main_image", ""):
        add(_resolve_url(prod.main_image))
    elif getattr(prod, "main_image_file", None):
        add(f"{SITE_URL}{prod.main_image_file.url}")

    if hasattr(prod, "images"):
        for pi in prod.images.all():
            add(pi.image_url or (
                f"{SITE_URL}{pi.image_file.url}" if pi.image_file else ""
            ))

    return urls


def collect_video_url(prod: Product, domain_item=None) -> Optional[str]:
    """
    Возвращает первый доступный URL видео для товара.
    Проверяет галерею domain_item, затем prod.
    """
    domain = domain_item if (domain_item and domain_item is not prod) else None
    for source in ([domain, prod] if domain else [prod]):
        if source and hasattr(source, "images"):
            for pi in source.images.all():
                v_url = getattr(pi, "video_url", "") or (
                    f"{SITE_URL}{pi.video_file.url}"
                    if getattr(pi, "video_file", None) else ""
                )
                if v_url:
                    return v_url
    return None


class Command(BaseCommand):
    help = "Синхронизирует фото товаров из БД в ВК Маркет через VK API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--offer-id",
            type=str,
            default=None,
            metavar="OFFER_ID",
            help=(
                "Синхронизировать только один оффер по ID из YML-фида "
                "(например: '42' или '42v7'). "
                "По умолчанию — все товары."
            ),
        )
        parser.add_argument(
            "--category",
            type=str,
            default=None,
            metavar="SLUG",
            help="Синхронизировать только товары определенной категории (по slug).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать что будет загружено, без реальных запросов к VK API.",
        )
        parser.add_argument(
            "--max-photos",
            type=int,
            default=5,
            metavar="N",
            help="Максимальное число фото на один товар (по умолчанию: 5).",
        )
        parser.add_argument(
            "--skip-video",
            action="store_true",
            help="Не синхронизировать видео.",
        )

    def handle(self, *args, **options):
        token: str = getattr(settings, "VK_API_TOKEN", "")
        group_id: int = getattr(settings, "VK_GROUP_ID", 0)
        user_token: str = getattr(settings, "VK_USER_TOKEN", "")

        if not token:
            raise CommandError("VK_YML_API не задан в .env")
        if not group_id:
            raise CommandError(
                "VK_GROUP_ID не задан в .env\n"
                "Найти ID: откройте группу ВК → в URL: vk.com/clubXXXXX → XXXXX и есть ID"
            )
        if not user_token:
            raise CommandError(
                "VK_USER_TOKEN не задан. Он нужен для market.get (group token не подходит).\n"
                "Получите: https://oauth.vk.com/authorize"
                f"?client_id={getattr(settings, 'VK_APP_ID', 'APP_ID')}"
                "&display=page&redirect_uri=https://oauth.vk.com/blank.html"
                "&scope=market,photos,video,offline&response_type=token&v=5.131"
            )

        dry_run: bool = options["dry_run"]
        max_photos: int = options["max_photos"]
        target_offer: str | None = options["offer_id"]
        target_category: str | None = options["category"]

        if dry_run:
            self.stdout.write(self.style.WARNING("⚡ DRY-RUN режим — реальной загрузки не будет"))

        sync = VKMarketSync(group_token=token, group_id=group_id, user_token=user_token)

        # ---------------------------------------------------------------
        # 1. Загружаем список всех товаров из ВК
        # ---------------------------------------------------------------
        self.stdout.write(f"Загружаем товары из ВК (группа {group_id})...")
        try:
            vk_items = sync.get_all_market_items()
        except Exception as e:
            raise CommandError(f"Ошибка VK API при загрузке товаров: {e}")

        self.stdout.write(f"Найдено {len(vk_items)} товаров в ВК")

        # Фильтр по конкретному offer-id
        if target_offer:
            vk_items = [i for i in vk_items if str(i.get("external_id", "")) == target_offer]
            self.stdout.write(
                f"После фильтра по offer-id={target_offer!r}: {len(vk_items)} товаров"
            )
            if not vk_items:
                self.stdout.write(
                    self.style.WARNING(
                        "Товар не найден в ВК. Проверьте что:\n"
                        "  1. YML-фид загружен в ВК и обработан\n"
                        "  2. external_id в ВК совпадает с offer id в фиде\n"
                        f"  3. Указанный offer-id '{target_offer}' существует в фиде"
                    )
                )
                return

        # ---------------------------------------------------------------
        # 2. Для каждого VK-товара с external_id — синхронизируем фото
        # ---------------------------------------------------------------
        total_offers = 0
        total_uploaded = 0
        total_failed = 0
        skipped = 0

        for vk_item in vk_items:
            external_id: str = str(vk_item.get("external_id") or "")
            vk_item_id: int = vk_item["id"]
            title: str = vk_item.get("title", "?")

            if not external_id:
                skipped += 1
                continue

            # Парсим external_id: "1v9" → prod_id=1, variant_id=9; "42" → prod_id=42
            try:
                if "v" in external_id:
                    raw_prod, raw_var = external_id.split("v", 1)
                    prod_id, variant_id = int(raw_prod), int(raw_var)
                else:
                    prod_id, variant_id = int(external_id), None
            except ValueError:
                self.stdout.write(f"  Пропуск: неизвестный формат external_id={external_id!r}")
                skipped += 1
                continue

            # Загружаем товар из БД
            try:
                prod_query = Product.objects.select_related("brand", "category", "category__parent")
                if target_category:
                    # Фильтр по категории (включая дочерние)
                    prod = prod_query.get(id=prod_id, category__slug=target_category)
                else:
                    prod = prod_query.get(id=prod_id)
            except Product.DoesNotExist:
                if not target_category:
                    self.stdout.write(
                        self.style.WARNING(f"  [{external_id}] Product id={prod_id} не найден в БД, пропуск")
                    )
                skipped += 1
                continue

            domain_item = prod.domain_item
            variant = None

            if variant_id and domain_item and hasattr(domain_item, "variants"):
                try:
                    variant = (
                        domain_item.variants
                        .prefetch_related("images")
                        .get(id=variant_id)
                    )
                except Exception:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [{external_id}] Variant id={variant_id} не найден, синхронизируем без варианта"
                        )
                    )

            # Собираем все URL изображений
            image_urls = collect_image_urls(prod, variant=variant, domain_item=domain_item)
            image_urls = [u for u in image_urls if u][:max_photos]

            # Видео (1 URL из галереи товара)
            video_url: Optional[str] = None
            if not options["skip_video"]:
                video_url = collect_video_url(prod, domain_item=domain_item)

            total_offers += 1

            self.stdout.write(
                f"  [{external_id}] VK item={vk_item_id} | {title[:40]} | "
                f"{len(image_urls)} фото{'  + видео' if video_url else ''}"
            )

            if dry_run:
                for url in image_urls:
                    self.stdout.write(f"    → {url[:90]}")
                if video_url:
                    self.stdout.write(f"    🎥 {video_url[:90]}")
                continue

            if not image_urls:
                self.stdout.write(self.style.WARNING("    Нет изображений — пропуск"))
                continue

            # Реальная загрузка
            try:
                result = sync.sync_item_photos(vk_item_id, image_urls, video_url=video_url)
                total_uploaded += result["uploaded"]
                total_failed += result["failed"]
                status = "✓" if result["failed"] == 0 else "⚠"
                video_status = " 🎥✓" if result.get("video") else (" 🎥✗" if video_url else "")
                self.stdout.write(
                    f"    {status} загружено={result['uploaded']} ошибок={result['failed']}{video_status}"
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    ✗ Ошибка: {e}"))
                total_failed += len(image_urls)

        # ---------------------------------------------------------------
        # 3. Итог
        # ---------------------------------------------------------------
        summary = (
            f"\n{'[DRY-RUN] ' if dry_run else ''}Готово: "
            f"обработано={total_offers}, "
            f"загружено={total_uploaded}, "
            f"ошибок={total_failed}, "
            f"пропущено={skipped}"
        )
        self.stdout.write(self.style.SUCCESS(summary))
