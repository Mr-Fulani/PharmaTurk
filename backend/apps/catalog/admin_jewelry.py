from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    JewelryProduct, JewelryProductTranslation, JewelryProductImage,
    JewelryVariant, JewelryVariantImage, JewelryVariantSize
)

class JewelryProductTranslationInline(admin.StackedInline):
    model = JewelryProductTranslation
    extra = 0
    fields = ['locale', 'name', 'description']

class JewelryProductImageInline(admin.TabularInline):
    model = JewelryProductImage
    extra = 1
    fields = ['image_file', 'image_url', 'alt_text', 'sort_order', 'is_main']
    readonly_fields = ['created_at']

class JewelryVariantSizeInline(admin.TabularInline):
    model = JewelryVariantSize
    extra = 1
    fields = ['size_display', 'size_value', 'size_unit', 'size_type', 'stock_quantity', 'is_available', 'sort_order']

class JewelryVariantImageInline(admin.TabularInline):
    model = JewelryVariantImage
    extra = 1
    fields = ['image_file', 'image_url', 'alt_text', 'sort_order', 'is_main']

class JewelryVariantInline(admin.StackedInline):
    model = JewelryVariant
    extra = 0
    fields = [
        'name', 'slug', 'color', 'material', 'gender', 'price', 'currency', 
        'old_price', 'stock_quantity', 'is_available', 'is_active', 'sort_order'
    ]
    prepopulated_fields = {"slug": ("name",)}
    show_change_link = True

@admin.register(JewelryProduct)
class JewelryProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'jewelry_type', 'material', 'gender', 'price', 'currency', 'is_active', 'created_at']
    list_filter = ['is_active', 'jewelry_type', 'gender', 'brand', 'is_featured', 'is_new']
    search_fields = ['name', 'sku', 'description']
    inlines = [JewelryProductTranslationInline, JewelryProductImageInline, JewelryVariantInline]
    fieldsets = (
        (_("Основная информация"), {
            "fields": ("name", "category", "brand", "sku", "barcode", "description")
        }),
        (_("Характеристики украшения"), {
            "fields": ("jewelry_type", "material", "metal_purity", "stone_type", "carat_weight", "gender")
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
            "fields": ("main_image_file", "video_url", "main_video_file")
        }),
        (_("Маркетинг"), {
            "fields": ("is_new", "is_featured", "slug")
        }),
    )
    prepopulated_fields = {"slug": ("name",)}

@admin.register(JewelryVariant)
class JewelryVariantAdmin(admin.ModelAdmin):
    list_display = ['product', 'name', 'color', 'material', 'price', 'stock_quantity', 'is_available']
    list_filter = ['is_available', 'product__brand']
    search_fields = ['name', 'sku', 'product__name']
    inlines = [JewelryVariantSizeInline, JewelryVariantImageInline]
    fieldsets = (
        (_("Вариант"), {
            "fields": ("product", "name", "slug", "color", "material", "gender")
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
