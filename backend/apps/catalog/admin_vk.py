"""
Регистрация VKCategoryMapping в Django Admin.
Показывает готовые ссылки на YML-фид для каждой категории прямо в списке.
Позволяет запускать синхронизацию фото в ВК Маркет прямо из интерфейса.
"""
import logging

from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models_vk import VKCategoryMapping

logger = logging.getLogger(__name__)

SITE_URL = "https://mudaroba.com"
FULL_FEED_URL = f"{SITE_URL}/api/catalog/export/yml/catalog.yml"


@admin.register(VKCategoryMapping)
class VKCategoryMappingAdmin(admin.ModelAdmin):
    """
    Управление маппингом типов товаров → категории маркетплейсов.
    В колонке «Ссылка на фид» — готовая ссылка для ВК/Яндекс.Маркет.
    Кнопки синхронизации фото запускают VK API прямо из Admin.
    """
    change_list_template = "admin/catalog/vkcategorymapping/change_list.html"
    list_display = ("product_type_display", "vk_category_path", "feed_url_link", "updated_at")
    list_display_links = ("product_type_display",)
    search_fields = ("product_type", "vk_category_path")
    ordering = ("product_type",)

    # ------------------------------------------------------------------
    # Кастомные URL для синхронизации
    # ------------------------------------------------------------------

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "sync-photos/",
                self.admin_site.admin_view(self.sync_photos_view),
                name="catalog_vk_sync_all",
            ),
            path(
                "sync-photos/<str:category>/",
                self.admin_site.admin_view(self.sync_photos_view),
                name="catalog_vk_sync_category",
            ),
        ]
        return custom + urls

    def sync_photos_view(self, request, category: str | None = None):
        """
        Запускает синхронизацию фото в ВК Маркет.
        При передаче category — только для этой категории.
        Без category — для всех товаров.
        """
        from django.conf import settings

        from apps.catalog.management.commands.sync_vk_photos import (
            collect_image_urls,
            collect_video_url,
        )
        from apps.catalog.models import Product
        from apps.catalog.services.vk_market_sync import VKAPIError, VKMarketSync

        token: str = getattr(settings, "VK_USER_TOKEN", "")
        group_id: int = getattr(settings, "VK_GROUP_ID", 0)

        if not token:
            messages.error(
                request,
                "❌ VK_USER_TOKEN не задан в .env. "
                "Получите: https://oauth.vk.com/authorize"
                f"?client_id={getattr(settings, 'VK_APP_ID', 'APP_ID')}"
                "&display=page&redirect_uri=https://oauth.vk.com/blank.html"
                "&scope=market,photos,video,offline&response_type=token&v=5.131"
            )
            return redirect("..")
        if not group_id:
            messages.error(request, "❌ VK_GROUP_ID не задан в .env")
            return redirect("..")

        label = f"«{category}»" if category else "все категории"

        try:
            sync = VKMarketSync(token=token, group_id=group_id)
            vk_items = sync.get_all_market_items()
        except Exception as e:
            messages.error(request, f"❌ Ошибка VK API: {e}")
            return redirect("..")

        total_uploaded = 0
        total_failed = 0
        processed = 0
        SITE = SITE_URL

        for vk_item in vk_items:
            external_id: str = str(vk_item.get("external_id") or "")
            vk_item_id: int = vk_item["id"]

            if not external_id:
                continue

            # Парсим external_id → prod_id [, variant_id]
            try:
                if "v" in external_id:
                    raw_p, raw_v = external_id.split("v", 1)
                    prod_id, variant_id = int(raw_p), int(raw_v)
                else:
                    prod_id, variant_id = int(external_id), None
            except ValueError:
                continue

            # Загружаем Product, опционально фильтруем по категории
            try:
                qs = Product.objects.select_related("category").prefetch_related("images")
                if category:
                    prod = qs.get(id=prod_id, category__slug=category)
                else:
                    prod = qs.get(id=prod_id)
            except Product.DoesNotExist:
                continue  # не в этой категории — пропускаем тихо

            domain_item = prod.domain_item
            variant = None
            if variant_id and domain_item and hasattr(domain_item, "variants"):
                try:
                    variant = domain_item.variants.prefetch_related("images").get(id=variant_id)
                except Exception:
                    pass

            image_urls = [
                u for u in collect_image_urls(prod, variant=variant, domain_item=domain_item) if u
            ][:5]
            video_url = collect_video_url(prod, domain_item=domain_item)

            if not image_urls:
                continue

            try:
                result = sync.sync_item_photos(vk_item_id, image_urls, video_url=video_url)
                total_uploaded += result.get("uploaded", 0)
                total_failed += result.get("failed", 0)
                processed += 1
            except VKAPIError as e:
                logger.warning(f"VK API error for item {vk_item_id}: {e}")
                total_failed += len(image_urls)
            except Exception as e:
                logger.error(f"Unexpected error for item {vk_item_id}: {e}")
                total_failed += 1

        msg = (
            f"✅ Синхронизация {label} завершена: "
            f"товаров обработано — {processed}, "
            f"фото загружено — {total_uploaded}, "
            f"ошибок — {total_failed}."
        )
        level = messages.SUCCESS if total_failed == 0 else messages.WARNING
        messages.add_message(request, level, msg)
        return redirect("..")

    # ------------------------------------------------------------------
    # Контекст для шаблона (список категорий + ссылки)
    # ------------------------------------------------------------------

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["full_feed_url"] = FULL_FEED_URL

        # Передаём все маппинги чтобы шаблон мог построить кнопки
        extra_context["vk_mappings"] = list(VKCategoryMapping.objects.order_by("product_type"))
        return super().changelist_view(request, extra_context=extra_context)

    # ------------------------------------------------------------------
    # Отображение в таблице
    # ------------------------------------------------------------------

    def product_type_display(self, obj):
        """Отображает человекочитаемое название типа товара."""
        return obj.get_product_type_display()
    product_type_display.short_description = _("Тип товара")

    def feed_url_link(self, obj):
        """Готовая ссылка на YML-фид для данного типа товара."""
        url = f"{FULL_FEED_URL}?category={obj.product_type}"
        return format_html(
            '<a href="{url}" target="_blank" style="font-family: monospace; font-size: 12px;">'
            '{url}'
            '</a>',
            url=url,
        )
    feed_url_link.short_description = _("Ссылка на YML-фид")

    fieldsets = (
        (None, {
            "fields": ("product_type", "vk_category_path", "feed_url_readonly"),
            "description": _(
                "Укажите тип товара и соответствующий путь категории маркетплейса. "
                "Путь задаётся через ' > ', например: "
                "'Одежда, обувь и аксессуары > Мужская одежда > Головные уборы > Кепки и бейсболки'"
            ),
        }),
        (_("Примечания"), {
            "fields": ("notes",),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("updated_at", "feed_url_readonly")

    def feed_url_readonly(self, obj):
        """Ссылка на фид в карточке редактирования."""
        if not obj.pk:
            return "—"
        url = f"{FULL_FEED_URL}?category={obj.product_type}"
        return format_html(
            '<a href="{url}" target="_blank" style="font-family: monospace;">{url}</a>',
            url=url,
        )
    feed_url_readonly.short_description = _("Ссылка на фид (для ВК/Яндекс)")

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ("product_type", "updated_at", "feed_url_readonly")
        return ("updated_at", "feed_url_readonly")
