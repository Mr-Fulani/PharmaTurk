"""Админка ночной сверки наличия и неактуальных товаров (docs/NIGHTLY_STOCK_CHECK.md)."""
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models_stock import SOURCE_TITLES, StaleProductCandidate, StockCheckSourceState


def source_title(parser_key: str) -> str:
    return SOURCE_TITLES.get(parser_key, parser_key)


@admin.register(StockCheckSourceState)
class StockCheckSourceStateAdmin(admin.ModelAdmin):
    """Где остановилась сверка каждого источника, итог ночи и пауза предохранителя."""

    list_display = ("source", "night", "checked", "catalog_size", "last_full_cycle_at", "pause")
    readonly_fields = (
        "parser_key", "cursor_pk", "night", "stats", "catalog_size", "last_full_cycle_at",
        "paused_at", "reported_night", "updated_at",
    )
    fields = readonly_fields[:6] + ("paused_reason",) + readonly_fields[6:]

    @admin.display(description="Источник", ordering="parser_key")
    def source(self, obj):
        return source_title(obj.parser_key)

    @admin.display(description="Проверено за ночь")
    def checked(self, obj):
        return (obj.stats or {}).get("checked", 0)

    @admin.display(description="Пауза")
    def pause(self, obj):
        return obj.paused_reason or "—"

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if not obj.paused_reason:
            obj.paused_at = None
        super().save_model(request, obj, form, change)


@admin.register(StaleProductCandidate)
class StaleProductCandidateAdmin(admin.ModelAdmin):
    """Товары, которых больше нет у продавца. Ничего не удаляется автоматически."""

    list_display = ("product_link", "source", "status", "first_seen_at", "gone_checks", "source_link")
    list_filter = ("status", "parser_key")
    search_fields = ("product__name", "source_url")
    list_select_related = ("product",)
    readonly_fields = (
        "product", "parser_key", "source_url", "reason", "status", "first_seen_at",
        "last_gone_at", "gone_checks", "hidden_at", "status_changed_by", "updated_at",
    )

    @admin.display(description="Товар", ordering="product__name")
    def product_link(self, obj):
        url = reverse("admin:catalog_product_change", args=[obj.product_id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)

    @admin.display(description="Источник", ordering="parser_key")
    def source(self, obj):
        return source_title(obj.parser_key)

    @admin.display(description="У продавца")
    def source_link(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">открыть</a>', obj.source_url)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
