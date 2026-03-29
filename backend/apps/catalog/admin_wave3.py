from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    SportsProduct, SportsProductTranslation, SportsProductImage, SportsVariant,
    AutoPartProduct, AutoPartProductTranslation, AutoPartProductImage, AutoPartVariant,
)
from .admin_wave2 import _SimpleDomainAdmin, _make_translation_inline, _make_image_inline
from .admin_base import AIStatusFilter


@admin.register(SportsProduct)
class SportsProductAdmin(_SimpleDomainAdmin):
    _category_type_slug = "sports"
    _domain_fieldset = (_('Характеристики спорттовара'), {
        'fields': ('sport_type', 'equipment_type', 'material'),
    })
    list_display = [
        'name', 'get_ai_status', 'category', 'sport_type', 'equipment_type',
        'price', 'old_price', 'is_available', 'created_at',
    ]
    list_filter = [
        AIStatusFilter, 'category', 'is_available', 'sport_type', 'equipment_type', 'created_at'
    ]
    
    class SportsVariantInline(admin.TabularInline):
        model = SportsVariant
        extra = 0
        fields = ('color', 'size', 'sku', 'price', 'stock_quantity', 'is_available')
        verbose_name = _("Вариант")
        verbose_name_plural = _("Варианты")

    inlines = [
        _make_translation_inline(SportsProductTranslation),
        _make_image_inline(SportsProductImage),
        SportsVariantInline,
    ]


@admin.register(AutoPartProduct)
class AutoPartProductAdmin(_SimpleDomainAdmin):
    _category_type_slug = "auto_parts"
    _domain_fieldset = (_('Характеристики запчасти'), {
        'fields': ('part_number', 'car_brand', 'car_model', 'compatibility_years'),
    })
    list_display = [
        'name', 'get_ai_status', 'category', 'part_number', 'car_brand',
        'price', 'old_price', 'is_available', 'created_at',
    ]
    list_filter = [
        AIStatusFilter, 'category', 'is_available', 'car_brand', 'created_at'
    ]
    search_fields = _SimpleDomainAdmin.search_fields + ['part_number', 'car_brand', 'car_model']
    
    class AutoPartVariantInline(admin.TabularInline):
        model = AutoPartVariant
        extra = 0
        fields = ('condition', 'manufacturer', 'sku', 'price', 'stock_quantity', 'is_available')
        verbose_name = _("Вариант")
        verbose_name_plural = _("Варианты")

    inlines = [
        _make_translation_inline(AutoPartProductTranslation),
        _make_image_inline(AutoPartProductImage),
        AutoPartVariantInline,
    ]
