"""
Регистрация VKCategoryMapping в Django Admin.
Показывает готовые ссылки на YML-фид для каждой категории прямо в списке.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models_vk import VKCategoryMapping

SITE_URL = "https://mudaroba.com"
FULL_FEED_URL = f"{SITE_URL}/api/catalog/export/yml/catalog.yml"


@admin.register(VKCategoryMapping)
class VKCategoryMappingAdmin(admin.ModelAdmin):
    """
    Управление маппингом типов товаров → категории маркетплейсов.
    В колонке «Ссылка на фид» — готовая ссылка для ВК/Яндекс.Маркет.
    """
    change_list_template = "admin/catalog/vkcategorymapping/change_list.html"
    list_display = ("product_type_display", "vk_category_path", "feed_url_link", "updated_at")
    list_display_links = ("product_type_display",)
    search_fields = ("product_type", "vk_category_path")
    ordering = ("product_type",)

    # Шапка над списком — ссылка на полный каталог
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["full_feed_url"] = FULL_FEED_URL
        return super().changelist_view(request, extra_context=extra_context)

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

    @admin.display(description=_("Ссылка на полный каталог"))
    def full_catalog_url(self, obj):
        return format_html(
            '<a href="{url}" target="_blank">{url}</a>',
            url=FULL_FEED_URL,
        )
