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
    variant_activation_action_names = (
        "activate_perfumery_variants",
        "deactivate_perfumery_variants",
    )
    list_display = ('name', 'product', 'volume', 'price', 'currency', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'currency', 'created_at')
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
        'name', 'slug', 'category', 'brand',
        'price', 'currency', 'fragrance_type', 'gender',
        'is_available', 'is_active', 'created_at',
    )
    list_filter = (
        'is_active', 'is_available', 'is_new', 'is_featured',
        'fragrance_type', 'fragrance_family', 'gender',
        'currency', 'category', 'brand', 'created_at',
    )
    search_fields = ('name', 'slug', 'description', 'external_id')
    ordering = ('-created_at',)
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
