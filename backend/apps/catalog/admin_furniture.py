from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    FurnitureProduct, FurnitureProductTranslation, FurnitureProductImage,
    FurnitureVariant, FurnitureVariantImage
)

class FurnitureProductTranslationInline(admin.StackedInline):
    model = FurnitureProductTranslation
    extra = 1
    fieldsets = (
        (None, {'fields': ('locale', 'name', 'description')}),
        (_('Локализованное SEO'), {
            'fields': ('meta_title', 'meta_description', 'meta_keywords', 'og_title', 'og_description'),
        }),
    )

class FurnitureProductImageInline(admin.TabularInline):
    model = FurnitureProductImage
    extra = 1
    fields = ['image_file', 'image_url', 'alt_text', 'sort_order', 'is_main']

class FurnitureVariantImageInline(admin.TabularInline):
    model = FurnitureVariantImage
    extra = 1
    fields = ['image_file', 'image_url', 'alt_text', 'sort_order', 'is_main']

class FurnitureVariantInline(admin.StackedInline):
    model = FurnitureVariant
    extra = 0
    fields = [
        'name', 'slug', 'color', 'price', 'currency', 
        'old_price', 'stock_quantity', 'is_available', 'is_active', 'sort_order'
    ]
    prepopulated_fields = {"slug": ("name",)}
    show_change_link = True

@admin.register(FurnitureProduct)
class FurnitureProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'furniture_type', 'material', 'price', 'currency', 'is_active', 'created_at']
    list_filter = ['is_active', 'furniture_type', 'brand', 'is_new', 'is_featured']
    search_fields = ['name', 'sku', 'description']
    inlines = [FurnitureProductTranslationInline, FurnitureProductImageInline, FurnitureVariantInline]
    fieldsets = (
        (_("Основная информация"), {
            "fields": ("name", "category", "brand", "sku", "barcode", "description")
        }),
        (_("Характеристики мебели"), {
            "fields": ("furniture_type", "material", "dimensions")
        }),
        (_("Цена и наличие"), {
            "fields": ("price", "currency", "old_price", "stock_quantity", "is_available", "is_active")
        }),
        (_("SEO (fallback / EN)"), {
            "fields": (
                "meta_title", "meta_description", "meta_keywords",
                "og_title", "og_description", "og_image_url"
            ),
            "description": _("Общие fallback/англоязычные SEO-поля. Локализованные SEO редактируются в переводах товара.")
        }),
        (_("Медиа"), {
            "fields": ("main_image_file", "main_image")
        }),
        (_("Маркетинг"), {
            "fields": ("is_new", "is_featured", "slug")
        }),
    )
    prepopulated_fields = {"slug": ("name",)}

@admin.register(FurnitureVariant)
class FurnitureVariantAdmin(admin.ModelAdmin):
    list_display = ['product', 'name', 'color', 'price', 'stock_quantity', 'is_available']
    list_filter = ['is_available', 'product__brand']
    search_fields = ['name', 'sku', 'product__name']
    inlines = [FurnitureVariantImageInline]
    fieldsets = (
        (_("Вариант"), {
            "fields": ("product", "name", "slug", "color")
        }),
        (_("Цены"), {
            "fields": ("price", "currency", "old_price")
        }),
        (_("Склад"), {
            "fields": ("stock_quantity", "is_available", "sku", "barcode", "gtin", "mpn")
        }),
        (_("Изображения"), {
            "fields": ("main_image_file", "main_image")
        }),
        (_("Статус"), {
            "fields": ("is_active", "sort_order")
        }),
    )
    prepopulated_fields = {"slug": ("name",)}
