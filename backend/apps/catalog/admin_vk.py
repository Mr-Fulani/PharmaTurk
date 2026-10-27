"""
Регистрация VKCategoryMapping в Django Admin.
Показывает готовые ссылки на YML-фид для каждой категории прямо в списке.
Позволяет пересобрать фиды и запустить синхронизацию фото в ВК Маркет (фоновые задачи).
"""
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Category
from .models_vk import VKCategoryMapping, YMLFeedSnapshot
from .services.yml_feed import prepared_feed_keys, root_category_slug

SITE_URL = "https://mudaroba.com"
FULL_FEED_URL = f"{SITE_URL}/api/catalog/export/yml/catalog.yml"
CHANGELIST = "admin:catalog_vkcategorymapping_changelist"


def feed_url(category_slug: str = "", part: int | None = None) -> str:
    params = []
    if category_slug:
        params.append(f"category={category_slug}")
    if part:
        params.append(f"part={part}")
    return f"{FULL_FEED_URL}?{'&'.join(params)}" if params else FULL_FEED_URL


def _feed_rows() -> list[dict]:
    """Строки панели фидов: по строке на каждую часть раздела — ссылка, когда собран, сколько офферов."""
    keys = prepared_feed_keys()
    names = dict(Category.objects.filter(slug__in=keys).values_list("slug", "name"))
    by_key: dict[str, list] = {}
    for snapshot in YMLFeedSnapshot.objects.filter(category_slug__in=keys).order_by("part"):
        by_key.setdefault(snapshot.category_slug, []).append(snapshot)

    rows = []
    for key in keys:
        name = names.get(key) or "Полный каталог"
        parts = by_key.get(key) or [None]
        for index, snapshot in enumerate(parts):
            multipart = len(parts) > 1
            rows.append({
                "slug": key,
                "name": f"{name} — часть {index + 1} из {len(parts)}" if multipart else name,
                "url": feed_url(key, index + 1 if multipart else None),
                "snapshot": snapshot,
                "first": index == 0,
            })
    return rows


@admin.register(VKCategoryMapping)
class VKCategoryMappingAdmin(admin.ModelAdmin):
    """
    Управление маппингом типов товаров → категории маркетплейсов.
    В колонке «Ссылка на фид» — готовая ссылка для ВК/Яндекс.Маркет.
    Кнопки пересборки фидов и синхронизации фото ставят фоновые задачи Celery.
    """
    change_list_template = "admin/catalog/vkcategorymapping/change_list.html"
    list_display = ("product_type_display", "gender", "vk_category_path", "feed_url_link", "updated_at")
    list_display_links = ("product_type_display",)
    list_filter = ("gender",)
    search_fields = ("product_type", "vk_category_path")
    ordering = ("product_type", "gender")

    # ------------------------------------------------------------------
    # Кастомные URL: пересборка фидов и синхронизация фото
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
            path(
                "generate-feeds/",
                self.admin_site.admin_view(self.generate_feeds_view),
                name="catalog_vk_generate_feeds",
            ),
        ]
        return custom + urls

    def sync_photos_view(self, request, category: str | None = None):
        """
        Ставит в очередь синхронизацию фото в ВК Маркет (задача catalog.sync_vk_photos).
        При передаче category — эта категория с подкатегориями, без — все товары.
        Итог приходит администратору в Telegram.
        """
        from django.conf import settings

        from apps.catalog.tasks import sync_vk_photos_task

        if request.method != "POST":
            return redirect(CHANGELIST)

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
            return redirect(CHANGELIST)
        if not group_id:
            messages.error(request, "❌ VK_GROUP_ID не задан в .env")
            return redirect(CHANGELIST)

        label = f"«{category}»" if category else "все категории"
        sync_vk_photos_task.delay(category)
        messages.success(
            request,
            f"✅ Синхронизация фото ({label}) запущена в фоне. Итог придёт в Telegram администратору.",
        )
        return redirect(CHANGELIST)

    def generate_feeds_view(self, request):
        """Ставит в очередь пересборку всех готовых YML-фидов."""
        from apps.catalog.tasks import generate_yml_feeds

        if request.method == "POST":
            generate_yml_feeds.delay()
            messages.success(request, "✅ Пересборка фидов запущена в фоне — обновите страницу через несколько минут.")
        return redirect(CHANGELIST)

    # ------------------------------------------------------------------
    # Контекст для шаблона (список категорий + ссылки)
    # ------------------------------------------------------------------

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["feeds"] = _feed_rows()
        return super().changelist_view(request, extra_context=extra_context)

    # ------------------------------------------------------------------
    # Отображение в таблице
    # ------------------------------------------------------------------

    def product_type_display(self, obj):
        """Отображает человекочитаемое название типа товара."""
        return obj.get_product_type_display()
    product_type_display.short_description = _("Тип товара")

    def feed_url_link(self, obj):
        """Готовая ссылка на YML-фид корневой категории этого типа товара."""
        url = feed_url(root_category_slug(obj.product_type))
        return format_html(
            '<a href="{url}" target="_blank" style="font-family: monospace; font-size: 12px;">'
            '{url}'
            '</a>',
            url=url,
        )
    feed_url_link.short_description = _("Ссылка на YML-фид")

    fieldsets = (
        (None, {
            "fields": ("product_type", "gender", "vk_category_path", "feed_url_readonly"),
            "description": _(
                "Укажите тип товара, пол и путь категории ВК. Запись «Любой пол» — для товаров "
                "без пола и унисекс. Путь задаётся через ' > ', например: 'Гардероб > Женщинам > Обувь'"
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
        url = feed_url(root_category_slug(obj.product_type))
        return format_html(
            '<a href="{url}" target="_blank" style="font-family: monospace;">{url}</a>',
            url=url,
        )
    feed_url_readonly.short_description = _("Ссылка на фид (для ВК/Яндекс)")

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ("product_type", "gender", "updated_at", "feed_url_readonly")
        return ("updated_at", "feed_url_readonly")
