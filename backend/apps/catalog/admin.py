from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Category, Brand, Product, ProductImage, ProductAttribute, PriceHistory


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Админка для категорий."""
    list_display = ('name', 'slug', 'parent', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'parent', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('sort_order', 'name')
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Hierarchy'), {'fields': ('parent',)}),
        (_('Settings'), {'fields': ('is_active', 'sort_order')}),
        (_('External'), {'fields': ('external_id', 'external_data')}),
    )


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    """Админка для брендов."""
    list_display = ('name', 'slug', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Media'), {'fields': ('logo', 'website')}),
        (_('Settings'), {'fields': ('is_active',)}),
        (_('External'), {'fields': ('external_id', 'external_data')}),
    )


class ProductImageInline(admin.TabularInline):
    """Инлайн для изображений товара."""
    model = ProductImage
    extra = 1
    fields = ('image_url', 'alt_text', 'sort_order', 'is_main')


class ProductAttributeInline(admin.TabularInline):
    """Инлайн для атрибутов товара."""
    model = ProductAttribute
    extra = 1
    fields = ('attribute_type', 'name', 'value', 'sort_order')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Админка для товаров."""
    list_display = ('name', 'slug', 'category', 'brand', 'price', 'currency', 'is_available', 'is_active', 'created_at')
    list_filter = ('is_active', 'is_available', 'is_featured', 'category', 'brand', 'currency', 'created_at')
    search_fields = ('name', 'slug', 'description', 'sku', 'barcode')
    ordering = ('-created_at',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('last_synced_at',)
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Categorization'), {'fields': ('category', 'brand')}),
        (_('Pricing'), {'fields': ('price', 'currency', 'old_price')}),
        (_('Availability'), {'fields': ('is_available', 'stock_quantity')}),
        (_('Media'), {'fields': ('main_image',)}),
        (_('Settings'), {'fields': ('is_active', 'is_featured')}),
        (_('Metadata'), {'fields': ('sku', 'barcode')}),
        (_('External'), {'fields': ('external_id', 'external_url', 'external_data')}),
        (_('Sync'), {'fields': ('last_synced_at',)}),
    )
    
    inlines = [ProductImageInline, ProductAttributeInline]


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    """Админка для изображений товаров."""
    list_display = ('product', 'image_url', 'alt_text', 'sort_order', 'is_main', 'created_at')
    list_filter = ('is_main', 'sort_order', 'created_at')
    search_fields = ('product__name', 'alt_text')
    ordering = ('product', 'sort_order')


@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    """Админка для атрибутов товаров."""
    list_display = ('product', 'attribute_type', 'name', 'value', 'sort_order')
    list_filter = ('attribute_type', 'sort_order', 'created_at')
    search_fields = ('product__name', 'name', 'value')
    ordering = ('product', 'sort_order', 'name')


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    """Админка для истории цен."""
    list_display = ('product', 'price', 'currency', 'source', 'recorded_at')
    list_filter = ('currency', 'source', 'recorded_at')
    search_fields = ('product__name',)
    ordering = ('-recorded_at',)
    readonly_fields = ('recorded_at',)
