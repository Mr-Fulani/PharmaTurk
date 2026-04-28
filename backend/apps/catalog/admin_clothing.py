from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    ClothingProduct, ClothingProductTranslation, 
    ClothingProductImage, ClothingProductSize
)

class ClothingProductTranslationInline(admin.StackedInline):
    model = ClothingProductTranslation
    extra = 0
    fields = ['locale', 'name', 'description']

class ClothingProductImageInline(admin.TabularInline):
    model = ClothingProductImage
    extra = 1
    fields = ['image_file', 'image_url', 'alt_text', 'sort_order', 'is_main']

class ClothingProductSizeInline(admin.TabularInline):
    model = ClothingProductSize
    extra = 1
    fields = ['size', 'stock_quantity', 'is_available', 'sort_order']

@admin.register(ClothingProduct)
class ClothingProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'category', 'color', 'size', 'material', 'price', 'is_active', 'created_at']
    list_filter = ['is_active', 'category', 'brand', 'season', 'is_new', 'is_featured']
    search_fields = ['name', 'sku', 'description']
    inlines = [ClothingProductTranslationInline, ClothingProductImageInline, ClothingProductSizeInline]
    fieldsets = (
        (_("Основная информация"), {
            "fields": ("name", "category", "brand", "sku", "barcode", "description")
        }),
        (_("Характеристики одежды"), {
            "fields": ("size", "color", "material", "season")
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
            "fields": ("main_image_file", "main_image", "video_url", "main_video_file")
        }),
        (_("Маркетинг"), {
            "fields": ("is_new", "is_featured", "slug")
        }),
    )
    prepopulated_fields = {"slug": ("name",)}
