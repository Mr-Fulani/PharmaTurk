"""Админ-интерфейс для управления статическими страницами.

Здесь определяется, какие поля отображаются в списках и форме, какие поля доступны только для чтения,
и как автоматически заполняется `slug`.
"""

from django.contrib import admin
from .models import Page


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    """Настройки отображения модели Page в Django admin.

    list_display: колонки в списке объектов.
    prepopulated_fields: автогенерация slug из русского заголовка.
    fieldsets: отдельные секции формы для разных языков и метаданных.
    """
    list_display = ("slug", "get_title", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("slug", "title_en", "title_ru", "content_en", "content_ru")
    # Генерируем slug на основе поля title_ru при вводе
    prepopulated_fields = {"slug": ("title_ru",)}
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("slug", "is_active")} ),
        ("English", {"fields": ("title_en", "content_en")} ),
        ("Русский", {"fields": ("title_ru", "content_ru")} ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
