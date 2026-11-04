"""Админка дублей у разных продавцов (docs/CROSS_SOURCE_DUPLICATES.md): пары «показан / скрыт / почему»."""
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models_duplicates import CrossSourceDuplicate


def _product_link(product):
    if product is None:
        return "—"
    url = reverse("admin:catalog_product_change", args=[product.pk])
    return format_html('<a href="{}">{}</a>', url, product.name)


@admin.register(CrossSourceDuplicate)
class CrossSourceDuplicateAdmin(admin.ModelAdmin):
    """Только просмотр: решения принимает пересчёт (resolve_cross_source_duplicates)."""

    list_display = (
        "hidden", "hidden_price", "shown", "shown_price", "currency", "match", "reason", "product_hidden", "confirmed_at", "updated_at",
    )
    list_filter = ("product_type", "match", "reason", "product_hidden")
    search_fields = ("hidden_product__name", "shown_product__name", "hidden_product__slug", "shown_product__slug")
    list_select_related = ("hidden_product", "shown_product")
    readonly_fields = [f.name for f in CrossSourceDuplicate._meta.fields]

    @admin.display(description="Скрыт", ordering="hidden_product__name")
    def hidden(self, obj):
        return _product_link(obj.hidden_product)

    @admin.display(description="Показан вместо него", ordering="shown_product__name")
    def shown(self, obj):
        return _product_link(obj.shown_product)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Удаление строки вернуло бы цвет на сайт не тем путём: откат — команда --unhide-all.
        return False
