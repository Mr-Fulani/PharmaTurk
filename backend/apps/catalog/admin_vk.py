"""
Регистрация VKCategoryMapping в Django Admin.
Отдельный файл чтобы не трогать огромный admin.py.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models_vk import VKCategoryMapping


@admin.register(VKCategoryMapping)
class VKCategoryMappingAdmin(admin.ModelAdmin):
    """
    Управление маппингом типов товаров → категории ВК Маркета.

    Добавите новый тип товара на сайт — просто зайдите сюда и
    добавьте одну строку: тип товара + путь категории ВК.
    Код менять не нужно.
    """
    list_display = ("product_type", "vk_category_path", "updated_at")
    list_display_links = ("product_type",)
    search_fields = ("product_type", "vk_category_path")
    ordering = ("product_type",)

    fieldsets = (
        (None, {
            "fields": ("product_type", "vk_category_path"),
            "description": _(
                "Укажите тип товара (product_type) и соответствующий путь категории ВК Маркета. "
                "Путь задаётся через ' > ', например: "
                "'Одежда, обувь и аксессуары > Мужская одежда > Головные уборы > Кепки и бейсболки'"
            ),
        }),
        (_("Примечания"), {
            "fields": ("notes",),
            "classes": ("collapse",),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        # product_type нельзя менять после создания (уникальный ключ маппинга)
        if obj:
            return ("product_type", "updated_at")
        return ("updated_at",)
