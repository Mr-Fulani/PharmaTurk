from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    Category, Brand, Product, ProductImage, ProductAttribute, PriceHistory, Favorite,
    ClothingCategory, ClothingProduct, ShoeCategory, ShoeProduct,
    ElectronicsCategory, ElectronicsProduct, Banner, BannerMedia
)


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


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    """Админка для избранного."""
    list_display = ('user', 'get_product_name', 'content_type', 'session_key', 'created_at')
    list_filter = ('content_type', 'created_at')
    search_fields = ('user__email', 'session_key')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'get_product_name')
    raw_id_fields = ('user',)
    
    def get_product_name(self, obj):
        """Получить название товара."""
        if obj.product:
            return getattr(obj.product, 'name', 'Unknown')
        return 'N/A'
    get_product_name.short_description = _("Товар")


# ============================================================================
# АДМИНКА ДЛЯ ОДЕЖДЫ, ОБУВИ И ЭЛЕКТРОНИКИ
# ============================================================================

@admin.register(ClothingCategory)
class ClothingCategoryAdmin(admin.ModelAdmin):
    """Админка для категорий одежды."""
    list_display = ('name', 'slug', 'gender', 'clothing_type', 'parent', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'gender', 'clothing_type', 'parent', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('sort_order', 'name')
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Clothing'), {'fields': ('gender', 'clothing_type')}),
        (_('Hierarchy'), {'fields': ('parent',)}),
        (_('Settings'), {'fields': ('is_active', 'sort_order')}),
        (_('External'), {'fields': ('external_id', 'external_data')}),
    )


@admin.register(ClothingProduct)
class ClothingProductAdmin(admin.ModelAdmin):
    """Админка для товаров одежды."""
    list_display = ('name', 'slug', 'category', 'brand', 'size', 'color', 'price', 'currency', 'is_available', 'is_active', 'created_at')
    list_filter = ('is_active', 'is_available', 'is_featured', 'category', 'brand', 'size', 'color', 'season', 'currency', 'created_at')
    search_fields = ('name', 'slug', 'description', 'size', 'color', 'material')
    ordering = ('-created_at',)
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Categorization'), {'fields': ('category', 'brand')}),
        (_('Clothing'), {'fields': ('size', 'color', 'material', 'season')}),
        (_('Pricing'), {'fields': ('price', 'currency', 'old_price')}),
        (_('Availability'), {'fields': ('is_available', 'stock_quantity')}),
        (_('Media'), {'fields': ('main_image',)}),
        (_('Settings'), {'fields': ('is_active', 'is_featured')}),
        (_('External'), {'fields': ('external_id', 'external_url', 'external_data')}),
    )


@admin.register(ShoeCategory)
class ShoeCategoryAdmin(admin.ModelAdmin):
    """Админка для категорий обуви."""
    list_display = ('name', 'slug', 'gender', 'shoe_type', 'parent', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'gender', 'shoe_type', 'parent', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('sort_order', 'name')
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Shoes'), {'fields': ('gender', 'shoe_type')}),
        (_('Hierarchy'), {'fields': ('parent',)}),
        (_('Settings'), {'fields': ('is_active', 'sort_order')}),
        (_('External'), {'fields': ('external_id', 'external_data')}),
    )


@admin.register(ShoeProduct)
class ShoeProductAdmin(admin.ModelAdmin):
    """Админка для товаров обуви."""
    list_display = ('name', 'slug', 'category', 'brand', 'size', 'color', 'price', 'currency', 'is_available', 'is_active', 'created_at')
    list_filter = ('is_active', 'is_available', 'is_featured', 'category', 'brand', 'size', 'color', 'heel_height', 'currency', 'created_at')
    search_fields = ('name', 'slug', 'description', 'size', 'color', 'material')
    ordering = ('-created_at',)
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Categorization'), {'fields': ('category', 'brand')}),
        (_('Shoes'), {'fields': ('size', 'color', 'material', 'heel_height', 'sole_type')}),
        (_('Pricing'), {'fields': ('price', 'currency', 'old_price')}),
        (_('Availability'), {'fields': ('is_available', 'stock_quantity')}),
        (_('Media'), {'fields': ('main_image',)}),
        (_('Settings'), {'fields': ('is_active', 'is_featured')}),
        (_('External'), {'fields': ('external_id', 'external_url', 'external_data')}),
    )


@admin.register(ElectronicsCategory)
class ElectronicsCategoryAdmin(admin.ModelAdmin):
    """Админка для категорий электроники."""
    list_display = ('name', 'slug', 'device_type', 'parent', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'device_type', 'parent', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('sort_order', 'name')
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Electronics'), {'fields': ('device_type',)}),
        (_('Hierarchy'), {'fields': ('parent',)}),
        (_('Settings'), {'fields': ('is_active', 'sort_order')}),
        (_('External'), {'fields': ('external_id', 'external_data')}),
    )


@admin.register(ElectronicsProduct)
class ElectronicsProductAdmin(admin.ModelAdmin):
    """Админка для товаров электроники."""
    list_display = ('name', 'slug', 'category', 'brand', 'model', 'price', 'currency', 'is_available', 'is_active', 'created_at')
    list_filter = ('is_active', 'is_available', 'is_featured', 'category', 'brand', 'currency', 'created_at')
    search_fields = ('name', 'slug', 'description', 'model')
    ordering = ('-created_at',)
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Categorization'), {'fields': ('category', 'brand')}),
        (_('Electronics'), {'fields': ('model', 'specifications', 'warranty', 'power_consumption')}),
        (_('Pricing'), {'fields': ('price', 'currency', 'old_price')}),
        (_('Availability'), {'fields': ('is_available', 'stock_quantity')}),
        (_('Media'), {'fields': ('main_image',)}),
        (_('Settings'), {'fields': ('is_active', 'is_featured')}),
        (_('External'), {'fields': ('external_id', 'external_url', 'external_data')}),
    )


class BannerMediaInline(admin.TabularInline):
    """Inline для медиа-файлов баннера."""
    model = BannerMedia
    extra = 1
    fields = (
        'content_type', 'image', 'video_file', 'gif_file', 'link_url', 'sort_order'
    )
    verbose_name = _("Медиа-файл")
    verbose_name_plural = _("Медиа-файлы")


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    """Админка для баннеров."""
    list_display = ('title', 'position', 'get_media_count', 'is_active', 'sort_order', 'created_at')
    list_filter = ('position', 'is_active', 'created_at')
    search_fields = ('title',)
    ordering = ('position', 'sort_order', '-created_at')
    inlines = [BannerMediaInline]
    
    fieldsets = (
        (None, {'fields': ('title', 'position', 'is_active', 'sort_order')}),
        (_('Ссылка'), {'fields': ('link_url', 'link_text')}),
    )
    
    def get_media_count(self, obj):
        """Количество медиа-файлов в баннере."""
        if obj.pk:
            return obj.media_files.count()
        return 0
    get_media_count.short_description = _("Количество медиа")


@admin.register(BannerMedia)
class BannerMediaAdmin(admin.ModelAdmin):
    """Админка для медиа-файлов баннеров (для прямого доступа)."""
    list_display = ('banner', 'content_type', 'get_content_preview', 'sort_order', 'created_at')
    list_filter = ('content_type', 'banner__position', 'created_at')
    search_fields = ('banner__title',)
    ordering = ('banner', 'sort_order', '-created_at')
    
    fieldsets = (
        (None, {'fields': ('banner', 'content_type', 'sort_order')}),
        (_('Изображение'), {
            'fields': ('image', 'image_url'),
            'description': _('Загрузите изображение локально или укажите внешний URL')
        }),
        (_('Видео'), {
            'fields': ('video_file', 'video_url'),
            'description': _('Загрузите видеофайл локально или укажите внешний URL')
        }),
        (_('GIF'), {
            'fields': ('gif_file', 'gif_url'),
            'description': _('Загрузите GIF файл локально или укажите внешний URL')
        }),
        (_('Ссылка'), {
            'fields': ('link_url',),
            'description': _('Ссылка, на которую должен вести клик по текущему медиа')
        }),
    )
    
    def get_fieldsets(self, request, obj=None):
        """Динамически показываем только нужные поля в зависимости от типа контента."""
        if obj:
            if obj.content_type == 'image':
                return [
                    (None, {'fields': ('banner', 'content_type', 'sort_order')}),
                    (_('Изображение'), {'fields': ('image', 'image_url')}),
                    (_('Ссылка'), {'fields': ('link_url',)}),
                ]
            elif obj.content_type == 'video':
                return [
                    (None, {'fields': ('banner', 'content_type', 'sort_order')}),
                    (_('Видео'), {'fields': ('video_file', 'video_url')}),
                    (_('Ссылка'), {'fields': ('link_url',)}),
                ]
            elif obj.content_type == 'gif':
                return [
                    (None, {'fields': ('banner', 'content_type', 'sort_order')}),
                    (_('GIF'), {'fields': ('gif_file', 'gif_url')}),
                    (_('Ссылка'), {'fields': ('link_url',)}),
                ]
        return super().get_fieldsets(request, obj)
    
    def get_content_preview(self, obj):
        """Превью контента."""
        url = obj.get_content_url()
        if url:
            if obj.content_type == 'image' or obj.content_type == 'gif':
                return f'<img src="{url}" style="max-width: 100px; max-height: 50px;" />'
            return url[:50] + '...' if len(url) > 50 else url
        return _("Нет контента")
    get_content_preview.short_description = _("Превью")
    get_content_preview.allow_tags = True
