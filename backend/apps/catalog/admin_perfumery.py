"""Админки для моделей парфюмерии."""

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.db import models as django_models
from .admin_variant_ai import VariantAIAdminMixin
from .models import (
    PerfumeryProduct,
    PerfumeryProductTranslation, PerfumeryProductImage,
    PerfumeryVariant, PerfumeryVariantImage,
    Category,
    FRAGRANCE_TYPE_CHOICES, FRAGRANCE_FAMILY_CHOICES,
)
from .admin_base import RunAIActionMixin, ShadowProductCleanupAdminMixin


class PerfumeryCategoryFilter(admin.SimpleListFilter):
    """Иерархический фильтр только по категориям парфюмерии."""

    title = _("Категория парфюмерии")
    parameter_name = "perfumery_category"

    def __init__(self, request, params, model, model_admin):
        self.category_filter_path = getattr(
            model_admin, "perfumery_category_filter_path", "category_id"
        )
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        categories = Category.objects.filter(
            category_type__slug="perfumery",
            is_active=True,
        ).select_related("parent", "parent__parent", "parent__parent__parent")
        return sorted(
            ((str(category.pk), category.get_breadcrumb_path()) for category in categories),
            key=lambda item: item[1].casefold(),
        )

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        return queryset.filter(**{self.category_filter_path: self.value()})


@admin.action(description=_("Сделать активными"))
def activate_perfumery_variants(modeladmin, request, queryset):
    queryset.update(is_active=True)


@admin.action(description=_("Сделать неактивными"))
def deactivate_perfumery_variants(modeladmin, request, queryset):
    queryset.update(is_active=False)


class PerfumeryVariantImageInline(admin.TabularInline):
    """Inline для изображений вариантов парфюмерии."""
    model = PerfumeryVariantImage
    extra = 1
    fields = ('image_file', 'image_url', 'alt_text', 'is_main', 'sort_order')


@admin.register(PerfumeryVariant)
class PerfumeryVariantAdmin(VariantAIAdminMixin, admin.ModelAdmin):
    """Админка для вариантов парфюмерии."""
    perfumery_category_filter_path = "product__category_id"
    variant_activation_action_names = (
        "activate_perfumery_variants",
        "deactivate_perfumery_variants",
    )
    list_display = ('name', 'product', 'volume', 'price', 'currency', 'is_active', 'sort_order', 'created_at')
    list_filter = (PerfumeryCategoryFilter, 'is_active', 'currency', 'created_at')
    search_fields = ('name', 'product__name', 'slug', 'volume', 'sku', 'barcode')
    ordering = ('product', 'sort_order', '-created_at')
    readonly_fields = ('slug',)
    actions = [activate_perfumery_variants, deactivate_perfumery_variants]
    fieldsets = (
        (None, {'fields': ('product', 'name', 'name_en', 'slug')}),
        (_('Объём'), {'fields': ('volume',)}),
        (_('Цена'), {'fields': ('price', 'old_price', 'currency')}),
        (_('Наличие'), {'fields': ('is_available', 'stock_quantity')}),
        (_('Медиа'), {'fields': ('main_image', 'main_image_file')}),
        (_('Идентификаторы'), {'fields': ('sku', 'barcode', 'external_id', 'external_url', 'external_data')}),
        (_('Настройки'), {'fields': ('is_active', 'sort_order')}),
    )
    inlines = [PerfumeryVariantImageInline]


# ─── Inlines для PerfumeryProduct ─────────────────────────────

class PerfumeryProductTranslationInline(admin.StackedInline):
    """Inline для переводов товаров парфюмерии."""
    model = PerfumeryProductTranslation
    extra = 1
    fieldsets = (
        (None, {'fields': ('locale', 'name', 'description')}),
        (_('Локализованное SEO'), {
            'fields': ('meta_title', 'meta_description', 'meta_keywords', 'og_title', 'og_description'),
            'description': _('SEO-поля для конкретного языка перевода (например ru или en).'),
        }),
    )


class PerfumeryProductImageInline(admin.TabularInline):
    """Inline для изображений товаров парфюмерии."""
    model = PerfumeryProductImage
    extra = 1
    fields = ('image_file', 'image_url', 'alt_text', 'is_main', 'sort_order')


class PerfumeryVariantInline(admin.TabularInline):
    """Inline для вариантов парфюмерии."""
    model = PerfumeryVariant
    extra = 0
    fields = ('name', 'slug', 'volume', 'price', 'old_price', 'currency', 'is_active', 'sort_order')
    readonly_fields = ('slug',)
    show_change_link = True


@admin.register(PerfumeryProduct)
class PerfumeryProductAdmin(RunAIActionMixin, ShadowProductCleanupAdminMixin, admin.ModelAdmin):
    """Админка для товаров парфюмерии."""
    list_display = (
        'name', 'slug', 'category_path', 'brand',
        'price', 'currency', 'fragrance_type', 'gender',
        'is_available', 'is_active', 'created_at',
    )
    list_filter = (
        'is_active', 'is_available', 'is_new', 'is_featured',
        'fragrance_type', 'fragrance_family', 'gender',
        'currency', PerfumeryCategoryFilter, 'brand', 'created_at',
    )
    search_fields = ('name', 'slug', 'description', 'external_id')
    ordering = ('-created_at',)
    list_select_related = ('category', 'category__parent', 'category__parent__parent', 'brand')
    readonly_fields = ('slug', 'base_product', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'
    list_per_page = 25
    autocomplete_fields = ['category', 'brand']

    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'description', 'category', 'brand'),
        }),
        (_('Парфюмерные характеристики'), {
            'fields': (
                'volume', 'fragrance_type', 'fragrance_family', 'gender',
                'top_notes', 'heart_notes', 'base_notes',
            ),
        }),
        (_('Цена'), {
            'fields': ('price', 'old_price', 'currency'),
        }),
        (_('Наличие'), {
            'fields': ('is_available', 'stock_quantity'),
        }),
        (_("SEO (fallback / EN)"), {
            'fields': (
                'meta_title', 'meta_description', 'meta_keywords',
                'og_title', 'og_description', 'og_image_url'
            ),
            'description': _("Общие fallback/англоязычные SEO-поля. Локализованные SEO редактируются в переводах товара.")
        }),
        (_('Медиа'), {
            'fields': ('main_image', 'main_image_file'),
        }),
        (_('Флаги'), {
            'fields': ('is_active', 'is_new', 'is_featured'),
        }),
        (_('Идентификаторы'), {
            'fields': ('external_id', 'external_url', 'external_data'),
            'classes': ('collapse',),
        }),
        (_('Shadow-синхронизация'), {
            'fields': ('base_product',),
            'classes': ('collapse',),
        }),
        (_('Даты'), {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    inlines = [
        PerfumeryProductTranslationInline,
        PerfumeryProductImageInline,
        PerfumeryVariantInline,
    ]

    @admin.display(description=_("Категория"), ordering="category__name")
    def category_path(self, obj):
        return obj.category.get_breadcrumb_path() if obj.category else "—"
