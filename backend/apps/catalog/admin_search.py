"""Админка учёта поисковых запросов (docs/PRODUCT_SEARCH.md, «Учёт запросов»)."""
from django.contrib import admin
from django.utils.html import format_html

from .models_search import SearchQueryStat


class FoundFilter(admin.SimpleListFilter):
    title = "что нашлось"
    parameter_name = "found"

    def lookups(self, request, model_admin):
        return [("none", "Ничего не нашлось"), ("few", "Мало (1–5)"), ("fixed", "Запрос исправлен поиском")]

    def queryset(self, request, queryset):
        if self.value() == "none":
            return queryset.filter(results=0)
        if self.value() == "few":
            return queryset.filter(results__range=(1, 5))
        if self.value() == "fixed":
            return queryset.exclude(corrected_query="")
        return queryset


@admin.register(SearchQueryStat)
class SearchQueryStatAdmin(admin.ModelAdmin):
    """Что ищут на сайте: самые частые запросы и те, по которым ничего не нашлось. Только чтение."""

    list_display = ("query", "searches", "results", "understood", "locale", "last_at", "open_search")
    list_filter = (FoundFilter, "locale", "last_at")
    search_fields = ("query",)
    ordering = ("-searches", "-last_at")
    list_per_page = 100

    @admin.display(description="Как понят запрос", ordering="mode")
    def understood(self, obj):
        title = SearchQueryStat.MODE_TITLES.get(obj.mode, obj.mode)
        return f"{title} → «{obj.corrected_query}»" if obj.corrected_query else title

    @admin.display(description="Проверить")
    def open_search(self, obj):
        prefix = "" if obj.locale == "ru" else f"/{obj.locale}"
        return format_html(
            '<a href="{}/search?query={}" target="_blank" rel="noopener">открыть поиск</a>', prefix, obj.query
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
