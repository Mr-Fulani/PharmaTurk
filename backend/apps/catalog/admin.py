from django import forms
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .forms import ProductForm, ProductImageInlineFormSet, VariantImageInlineFormSet
from .models import (
    CategoryType, Category, CategoryTranslation, CategoryMedicines, CategorySupplements, CategoryMedicalEquipment,
    CategoryTableware, CategoryFurniture, CategoryAccessories, CategoryJewelry,
    CategoryUnderwear, CategoryHeadwear, MarketingCategory, MarketingRootCategory,
    CategoryClothing, CategoryShoes, CategoryElectronics,
    Brand, BrandTranslation, MarketingBrand, Product, ProductTranslation, ProductImage, ProductAttribute, PriceHistory, Favorite,
    ProductMedicines, ProductSupplements, ProductMedicalEquipment,
    ProductTableware, ProductFurniture, ProductAccessories, ProductJewelry,
    ProductUnderwear, ProductHeadwear,
    ClothingProduct, ClothingProductTranslation, ClothingProductImage, ClothingVariant, ClothingVariantImage, ClothingVariantSize,
    ShoeProduct, ShoeProductTranslation, ShoeProductImage, ShoeVariant, ShoeVariantImage, ShoeVariantSize,
    ElectronicsProduct, ElectronicsProductTranslation, ElectronicsProductImage,
    FurnitureProduct, FurnitureProductTranslation, FurnitureVariant, FurnitureVariantImage,
    Service, ServiceTranslation,
    Banner, BannerMedia, MarketingBanner, MarketingBannerMedia
)


class TopLevelCategoryFilter(SimpleListFilter):
    """Фильтр по иерархии категорий (корневые/дочерние)."""
    title = _("Уровень категории")
    parameter_name = "level"

    def lookups(self, request, model_admin):
        return (
            ("root", _("Корневые")),
            ("child", _("Дочерние")),
        )

    def queryset(self, request, queryset):
        if self.value() == "root":
            return queryset.filter(parent__isnull=True)
        if self.value() == "child":
            return queryset.filter(parent__isnull=False)
        return queryset


class ActiveRootFilter(SimpleListFilter):
    """Быстрый фильтр по активности и уровню (активные/активные корневые/неактивные)."""
    title = _("Активность")
    parameter_name = "active_state"

    def lookups(self, request, model_admin):
        return (
            ("active_root", _("Активные корневые")),
            ("active", _("Активные (все)")),
            ("inactive", _("Неактивные")),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "active_root":
            return queryset.filter(is_active=True, parent__isnull=True)
        if value == "active":
            return queryset.filter(is_active=True)
        if value == "inactive":
            return queryset.filter(is_active=False)
        return queryset


@admin.register(CategoryType)
class CategoryTypeAdmin(admin.ModelAdmin):
    """Админка для типов категорий."""
    list_display = ('name', 'slug', 'is_active', 'sort_order', 'categories_count', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('sort_order', 'name')
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Настройки'), {'fields': ('is_active', 'sort_order')}),
    )
    
    def categories_count(self, obj):
        """Количество категорий этого типа."""
        if obj.pk:
            return obj.categories.count()
        return 0
    categories_count.short_description = _("Количество категорий")


class CategoryTranslationInline(admin.TabularInline):
    """Inline для редактирования переводов категорий."""
    model = CategoryTranslation
    extra = 1
    fields = ('locale', 'name', 'description')
    verbose_name = _("Перевод")
    verbose_name_plural = _("Переводы")


class BrandTranslationInline(admin.TabularInline):
    """Inline для редактирования переводов брендов."""
    model = BrandTranslation
    extra = 1
    fields = ('locale', 'name', 'description')


class ProductTranslationInline(admin.TabularInline):
    """Inline для редактирования переводов товаров."""
    model = ProductTranslation
    extra = 1
    fields = ('locale', 'description')
    verbose_name = _("Перевод")
    verbose_name_plural = _("Переводы")


class ClothingProductTranslationInline(admin.TabularInline):
    """Inline для редактирования переводов товаров одежды."""
    model = ClothingProductTranslation
    extra = 1
    fields = ('locale', 'description')
    verbose_name = _("Перевод")
    verbose_name_plural = _("Переводы")


class ShoeProductTranslationInline(admin.TabularInline):
    """Inline для редактирования переводов товаров обуви."""
    model = ShoeProductTranslation
    extra = 1
    fields = ('locale', 'description')
    verbose_name = _("Перевод")
    verbose_name_plural = _("Переводы")


class ElectronicsProductTranslationInline(admin.TabularInline):
    """Inline для редактирования переводов товаров электроники."""
    model = ElectronicsProductTranslation
    extra = 1
    fields = ('locale', 'description')
    verbose_name = _("Перевод")
    verbose_name_plural = _("Переводы")


class FurnitureProductTranslationInline(admin.TabularInline):
    """Inline для редактирования переводов товаров мебели."""
    model = FurnitureProductTranslation
    extra = 1
    fields = ('locale', 'description')
    verbose_name = _("Перевод")
    verbose_name_plural = _("Переводы")


class FurnitureVariantInline(admin.TabularInline):
    """Инлайн для вариантов мебели (основные поля)."""
    model = FurnitureVariant
    extra = 0
    fields = (
        'name', 'slug',
        'color',
        'price', 'currency',
        'main_image',
        'is_active', 'sort_order',
    )
    readonly_fields = ('slug',)
    show_change_link = True


class FurnitureVariantImageInline(admin.TabularInline):
    """Инлайн изображений варианта мебели."""
    model = FurnitureVariantImage
    extra = 1
    fields = ('image_url', 'alt_text', 'sort_order', 'is_main', 'image_preview')
    readonly_fields = ('image_preview',)
    
    def image_preview(self, obj):
        """Превью изображения."""
        if obj and obj.image_url:
            return format_html(
                '<img src="{}" style="max-width: 120px; max-height: 60px;" />',
                obj.image_url
            )
        return "-"
    image_preview.short_description = _("Превью")


class ServiceTranslationInline(admin.TabularInline):
    """Inline для редактирования переводов услуг."""
    model = ServiceTranslation
    extra = 1
    fields = ('locale', 'description')
    verbose_name = _("Перевод")
    verbose_name_plural = _("Переводы")


class BaseCategoryAdmin(admin.ModelAdmin):
    """Базовый админ для прокси категорий с фильтром по типу."""
    required_category_type_slug: str | None = None
    list_display = ('name', 'slug', 'category_type', 'parent', 'is_active', 'sort_order', 'created_at')
    list_filter = (ActiveRootFilter, 'is_active', TopLevelCategoryFilter, 'category_type', 'parent', 'gender', 'clothing_type', 'shoe_type', 'device_type', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('sort_order', 'name')
    prepopulated_fields = {'slug': ('name',)}
    autocomplete_fields = ('category_type',)
    inlines = [CategoryTranslationInline]
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Тип категории'), {
            'fields': ('category_type',),
            'description': _('Выберите тип категории. Если нужного типа нет, создайте его в разделе "Типы категорий".'),
        }),
        (_('Hierarchy'), {'fields': ('parent',)}),
        (_('Медиа карточки'), {
            'fields': ('card_media', 'card_media_external_url'),
            'description': _('Можно указать файл или внешнюю ссылку (CDN/S3). Внешняя ссылка приоритетнее.'),
        }),
        (_('Settings'), {'fields': ('is_active', 'sort_order')}),
        (_('External'), {'fields': ('external_id', 'external_data')}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self.required_category_type_slug:
            qs = qs.filter(category_type__slug=self.required_category_type_slug)
        return qs

    def save_model(self, request, obj, form, change):
        # НЕ перезаписываем тип категории, если он уже выбран в форме
        # Автоматическая установка типа только если он не был выбран пользователем
        if self.required_category_type_slug and not change and not obj.category_type_id:
            try:
                category_type = CategoryType.objects.get(slug=self.required_category_type_slug)
                obj.category_type = category_type
            except CategoryType.DoesNotExist:
                pass
        super().save_model(request, obj, form, change)


@admin.register(CategoryMedicines)
class CategoryMedicinesAdmin(BaseCategoryAdmin):
    required_category_type_slug = "medicines"
    fieldsets = BaseCategoryAdmin.fieldsets + (
        (_('Подсказка'), {'fields': (), 'description': _("Категории для товаров медицины: антибиотики, обезболивающие и т.д.")}),
    )


@admin.register(CategorySupplements)
class CategorySupplementsAdmin(BaseCategoryAdmin):
    required_category_type_slug = "supplements"
    fieldsets = BaseCategoryAdmin.fieldsets + (
        (_('Подсказка'), {'fields': (), 'description': _("Категории БАДов: витамины, минералы, протеин, омега и т.д.")}),
    )


@admin.register(CategoryMedicalEquipment)
class CategoryMedicalEquipmentAdmin(BaseCategoryAdmin):
    required_category_type_slug = "medical-equipment"
    fieldsets = BaseCategoryAdmin.fieldsets + (
        (_('Подсказка'), {'fields': (), 'description': _("Медтехника: тонометры, глюкометры, небулайзеры, ортезы, расходники.")}),
    )


@admin.register(CategoryTableware)
class CategoryTablewareAdmin(BaseCategoryAdmin):
    required_category_type_slug = "tableware"
    fieldsets = BaseCategoryAdmin.fieldsets + (
        (_('Подсказка'), {'fields': (), 'description': _("Посуда: кухонная, сервировка, хранение, медь, фарфор, стекло/керамика.")}),
    )


@admin.register(CategoryFurniture)
class CategoryFurnitureAdmin(BaseCategoryAdmin):
    required_category_type_slug = "furniture"
    fieldsets = BaseCategoryAdmin.fieldsets + (
        (_('Подсказка'), {'fields': (), 'description': _("Мебель: гостиная, спальня, офис, кухня/столовая.")}),
    )


@admin.register(CategoryAccessories)
class CategoryAccessoriesAdmin(BaseCategoryAdmin):
    required_category_type_slug = "accessories"
    fieldsets = BaseCategoryAdmin.fieldsets + (
        (_('Подсказка'), {'fields': (), 'description': _("Аксессуары общего назначения (ремни, брелоки и т.п.), подкатегории добавляются вручную.")}),
    )


@admin.register(CategoryJewelry)
class CategoryJewelryAdmin(BaseCategoryAdmin):
    required_category_type_slug = "jewelry"
    fieldsets = BaseCategoryAdmin.fieldsets + (
        (_('Подсказка'), {'fields': (), 'description': _("Украшения: кольца, цепочки, браслеты, серьги, подвески; есть женские/мужские.")}),
    )


@admin.register(CategoryUnderwear)
class CategoryUnderwearAdmin(BaseCategoryAdmin):
    required_category_type_slug = "underwear"
    fieldsets = BaseCategoryAdmin.fieldsets + (
        (_('Подсказка'), {'fields': (), 'description': _("Нижнее бельё: базовые и вариативные модели, подкатегории добавляются вручную.")}),
    )


@admin.register(CategoryHeadwear)
class CategoryHeadwearAdmin(BaseCategoryAdmin):
    required_category_type_slug = "headwear"
    fieldsets = BaseCategoryAdmin.fieldsets + (
        (_('Подсказка'), {'fields': (), 'description': _("Головные уборы: кепки, шапки, панамы и т.д.; подкатегории вручную.")}),
    )


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    """Админка для брендов."""
    list_display = ('name', 'slug', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    inlines = [BrandTranslationInline]
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Media'), {
            'fields': ('logo', 'card_media', 'card_media_external_url', 'website'),
            'description': _('Файл или внешняя ссылка (CDN/S3) для карточки бренда; ссылка приоритетнее файла.'),
        }),
        (_('Settings'), {'fields': ('is_active',)}),
        (_('Категория'), {'fields': ('primary_category_slug',)}),
        (_('External'), {'fields': ('external_id', 'external_data')}),
    )


class ProductImageInline(admin.TabularInline):
    """Инлайн для изображений товара."""
    model = ProductImage
    extra = 1
    fields = ('image_url', 'alt_text', 'sort_order', 'is_main', 'image_preview')
    readonly_fields = ('image_preview',)
    formset = ProductImageInlineFormSet

    def image_preview(self, obj):
        """Превью изображения."""
        if obj and obj.image_url:
            return format_html(
                '<img src="{}" style="max-width: 120px; max-height: 60px;" />',
                obj.image_url
            )
        return "-"
    image_preview.short_description = _("Превью")


class ShoeProductImageInline(admin.TabularInline):
    """Инлайн для изображений обуви."""
    model = ShoeProductImage
    extra = 1
    fields = ('image_url', 'alt_text', 'sort_order', 'is_main', 'image_preview')
    readonly_fields = ('image_preview',)
    formset = ProductImageInlineFormSet

    def image_preview(self, obj):
        """Превью изображения."""
        if obj and obj.image_url:
            return format_html(
                '<img src="{}" style="max-width: 120px; max-height: 60px;" />',
                obj.image_url
            )
        return "-"
    image_preview.short_description = _("Превью")


class ClothingProductImageInline(admin.TabularInline):
    """Инлайн для изображений одежды."""
    model = ClothingProductImage
    extra = 1
    fields = ('image_url', 'alt_text', 'sort_order', 'is_main', 'image_preview')
    readonly_fields = ('image_preview',)
    formset = ProductImageInlineFormSet

    def image_preview(self, obj):
        """Превью изображения."""
        if obj and obj.image_url:
            return format_html(
                '<img src="{}" style="max-width: 120px; max-height: 60px;" />',
                obj.image_url
            )
        return "-"
    image_preview.short_description = _("Превью")


class ElectronicsProductImageInline(admin.TabularInline):
    """Инлайн для изображений электроники."""
    model = ElectronicsProductImage
    extra = 1
    fields = ('image_url', 'alt_text', 'sort_order', 'is_main', 'image_preview')
    readonly_fields = ('image_preview',)
    formset = ProductImageInlineFormSet

    def image_preview(self, obj):
        """Превью изображения."""
        if obj and obj.image_url:
            return format_html(
                '<img src="{}" style="max-width: 120px; max-height: 60px;" />',
                obj.image_url
            )
        return "-"
    image_preview.short_description = _("Превью")


class ClothingVariantImageInline(admin.TabularInline):
    """Инлайн для изображений варианта одежды."""
    model = ClothingVariantImage
    extra = 1
    fields = ('image_url', 'alt_text', 'sort_order', 'is_main', 'image_preview')
    readonly_fields = ('image_preview',)
    formset = VariantImageInlineFormSet

    def image_preview(self, obj):
        """Превью изображения."""
        if obj and obj.image_url:
            return format_html(
                '<img src="{}" style="max-width: 120px; max-height: 60px;" />',
                obj.image_url
            )
        return "-"
    image_preview.short_description = _("Превью")


class ShoeVariantImageInline(admin.TabularInline):
    """Инлайн для изображений варианта обуви."""
    model = ShoeVariantImage
    extra = 1
    fields = ('image_url', 'alt_text', 'sort_order', 'is_main', 'image_preview')
    readonly_fields = ('image_preview',)
    formset = VariantImageInlineFormSet

    def image_preview(self, obj):
        """Превью изображения."""
        if obj and obj.image_url:
            return format_html(
                '<img src="{}" style="max-width: 120px; max-height: 60px;" />',
                obj.image_url
            )
        return "-"
    image_preview.short_description = _("Превью")


class ProductAttributeInline(admin.TabularInline):
    """Инлайн для атрибутов товара."""
    model = ProductAttribute
    extra = 1
    fields = ('attribute_type', 'name', 'value', 'sort_order')


class BaseProductAdmin(admin.ModelAdmin):
    """Базовый админ для товаров (используется прокси)."""
    form = ProductForm
    list_display = (
        'name', 'slug', 'product_type', 'category', 'brand', 'price', 'currency',
        'availability_status', 'country_of_origin', 'is_active', 'created_at'
    )
    list_filter = (
        'product_type', 'availability_status', 'country_of_origin',
        'is_active', 'is_featured', 'is_available', 'category', 'brand', 'currency', 'created_at'
    )
    search_fields = (
        'name', 'name_en', 'slug', 'description', 'description_en',
        'sku', 'barcode', 'gtin', 'mpn', 'meta_title'
    )
    ordering = ('-created_at',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('last_synced_at', 'slug_preview')
    autocomplete_fields = ('category', 'brand')
    
    fieldsets = (
        (_('Основное'), {
            'fields': (
                'name', 'name_en', 'slug', 'slug_preview',
                'description', 'description_en'
            )
        }),
        (_('Категоризация'), {'fields': ('product_type', 'category', 'brand')}),
        (_('Цены и наличие'), {
            'fields': (
                'price', 'currency', 'old_price', 'margin_percent_applied',
                'availability_status', 'is_available', 'stock_quantity',
                'min_order_quantity', 'pack_quantity'
            )
        }),
        (_('Логистика'), {
            'fields': (
                'gtin', 'mpn', 'weight_value', 'weight_unit', 'length',
                'width', 'height', 'dimensions_unit', 'country_of_origin'
            )
        }),
        (_('SEO (EN)'), {
            'fields': (
                'meta_title', 'meta_description', 'meta_keywords',
                'og_title', 'og_description', 'og_image_url'
            ),
            'description': _(
                "Англоязычные SEO-поля и OpenGraph используются на сайте и в соцсетях."
            )
        }),
        (_('Медиа'), {'fields': ('main_image',)}),
        (_('Мета'), {'fields': ('sku', 'barcode')}),
        (_('Внешние данные'), {'fields': ('external_id', 'external_url', 'external_data')}),
        (_('Синхронизация'), {'fields': ('last_synced_at',)}),
    )
    
    inlines = [ProductTranslationInline, ProductImageInline, ProductAttributeInline]

    def slug_preview(self, obj):
        """Предпросмотр slug."""
        if obj:
            return format_html('<code>{}</code>', obj.slug)
        return "-"
    slug_preview.short_description = _("Slug (предпросмотр)")


class BaseProductProxyAdmin(BaseProductAdmin):
    """Фильтрует по фиксированному product_type и скрывает поле типа."""
    required_product_type: str | None = None
    exclude = ('product_type',)
    autocomplete_fields = ('brand',)  # убираем category из autocomplete, чтобы избежать admin.E039
    inlines = [ProductTranslationInline, ProductImageInline, ProductAttributeInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self.required_product_type:
            qs = qs.filter(product_type=self.required_product_type)
        return qs

    def save_model(self, request, obj, form, change):
        if self.required_product_type:
            obj.product_type = self.required_product_type
        super().save_model(request, obj, form, change)

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        new_fieldsets = []
        for title, opts in fieldsets:
            fields = list(opts.get('fields', ()))
            if 'product_type' in fields:
                fields = [f for f in fields if f != 'product_type']
            new_fieldsets.append((title, {**opts, 'fields': tuple(fields)}))
        return new_fieldsets


@admin.register(ProductMedicines)
class ProductMedicinesAdmin(BaseProductProxyAdmin):
    required_product_type = "medicines"
    fieldsets = BaseProductAdmin.fieldsets


@admin.register(ProductSupplements)
class ProductSupplementsAdmin(BaseProductProxyAdmin):
    required_product_type = "supplements"
    fieldsets = BaseProductAdmin.fieldsets


@admin.register(ProductMedicalEquipment)
class ProductMedicalEquipmentAdmin(BaseProductProxyAdmin):
    required_product_type = "medical_equipment"
    fieldsets = BaseProductAdmin.fieldsets


@admin.register(ProductTableware)
class ProductTablewareAdmin(BaseProductProxyAdmin):
    required_product_type = "tableware"
    fieldsets = BaseProductAdmin.fieldsets


@admin.register(ProductFurniture)
class ProductFurnitureAdmin(BaseProductProxyAdmin):
    required_product_type = "furniture"
    fieldsets = BaseProductAdmin.fieldsets


@admin.register(ProductAccessories)
class ProductAccessoriesAdmin(BaseProductProxyAdmin):
    required_product_type = "accessories"
    fieldsets = BaseProductAdmin.fieldsets


@admin.register(ProductJewelry)
class ProductJewelryAdmin(BaseProductProxyAdmin):
    required_product_type = "jewelry"
    fieldsets = BaseProductAdmin.fieldsets


@admin.register(ProductUnderwear)
class ProductUnderwearAdmin(BaseProductProxyAdmin):
    required_product_type = "underwear"
    fieldsets = BaseProductAdmin.fieldsets


@admin.register(ProductHeadwear)
class ProductHeadwearAdmin(BaseProductProxyAdmin):
    required_product_type = "headwear"
    fieldsets = BaseProductAdmin.fieldsets


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    """Админка для изображений товаров."""
    list_display = ('product', 'image_url', 'alt_text', 'sort_order', 'is_main', 'image_preview', 'created_at')
    list_filter = ('is_main', 'sort_order', 'created_at')
    search_fields = ('product__name', 'alt_text')
    ordering = ('product', 'sort_order')
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        """Превью изображения."""
        if obj and obj.image_url:
            return format_html(
                '<img src="{}" style="max-width: 120px; max-height: 60px;" />',
                obj.image_url
            )
        return "-"
    image_preview.short_description = _("Превью")


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

@admin.register(CategoryClothing)
class ClothingCategoryAdmin(admin.ModelAdmin):
    """Админка для категорий одежды."""
    list_display = ('name', 'slug', 'gender', 'clothing_type', 'parent', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'gender', 'clothing_type', 'parent', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('sort_order', 'name')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [CategoryTranslationInline]
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Clothing'), {'fields': ('gender', 'clothing_type')}),
        (_('Hierarchy'), {'fields': ('parent',)}),
        (_('Settings'), {'fields': ('is_active', 'sort_order')}),
        (_('External'), {'fields': ('external_id', 'external_data')}),
    )
    
    def get_queryset(self, request):
        """Фильтруем только корневые категории одежды (где clothing_type не пустое)."""
        return super().get_queryset(request).filter(clothing_type__isnull=False).exclude(clothing_type='').filter(parent__isnull=True)


class ClothingVariantInline(admin.TabularInline):
    """Инлайн для вариантов одежды (основные поля)."""
    model = ClothingVariant
    extra = 0
    fields = ('name', 'slug', 'color', 'price', 'currency', 'is_active', 'sort_order')
    readonly_fields = ('slug',)
    show_change_link = True


class ClothingVariantSizeInline(admin.TabularInline):
    """Инлайн размеров варианта одежды."""
    model = ClothingVariantSize
    extra = 0
    fields = ('size', 'is_available', 'stock_quantity', 'sort_order')
    ordering = ('sort_order', 'size')


@admin.register(ClothingVariant)
class ClothingVariantAdmin(admin.ModelAdmin):
    """Отдельная админка варианта одежды (для картинок)."""
    list_display = ('name', 'product', 'color', 'price', 'currency', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'color', 'currency', 'created_at')
    search_fields = ('name', 'product__name', 'slug', 'color', 'sku', 'barcode', 'gtin', 'mpn')
    ordering = ('product', 'sort_order', '-created_at')
    readonly_fields = ('slug',)
    fieldsets = (
        (None, {'fields': ('product', 'name', 'slug')}),
        (_('Характеристики'), {
            'fields': ('color',),
            'description': _("Размеры задайте в таблице размеров ниже.")
        }),
        (_('Цены и наличие'), {'fields': ('price', 'currency', 'old_price')}),
        (_('Медиа'), {'fields': ('main_image',)}),
        (_('Идентификаторы'), {'fields': ('sku', 'barcode', 'gtin', 'mpn')}),
        (_('Внешние данные'), {'fields': ('external_id', 'external_url', 'external_data')}),
        (_('Статус'), {'fields': ('is_active', 'sort_order')}),
    )
    inlines = [ClothingVariantSizeInline, ClothingVariantImageInline]


@admin.register(ClothingProduct)
class ClothingProductAdmin(admin.ModelAdmin):
    """Админка для товаров одежды."""
    list_display = ('name', 'slug', 'category', 'brand', 'price', 'currency', 'is_active', 'created_at')
    list_filter = ('is_active', 'is_featured', 'category', 'brand', 'season', 'currency', 'created_at')
    search_fields = ('name', 'slug', 'description', 'material')
    ordering = ('-created_at',)
    prepopulated_fields = {'slug': ('name',)}
    exclude = ('size', 'color', 'stock_quantity', 'is_available')
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Categorization'), {'fields': ('category', 'brand')}),
        (_('Clothing'), {'fields': ('material', 'season')}),
        (_('Pricing'), {'fields': ('price', 'currency', 'old_price')}),
        (_('Availability'), {'fields': ()}),
        (_('Media'), {'fields': ('main_image',)}),
        (_('Settings'), {'fields': ('is_active', 'is_featured')}),
        (_('External'), {'fields': ('external_id', 'external_url', 'external_data')}),
    )
    inlines = [ClothingProductTranslationInline, ClothingVariantInline, ClothingProductImageInline]


@admin.register(CategoryShoes)
class ShoeCategoryAdmin(admin.ModelAdmin):
    """Админка для категорий обуви."""
    list_display = ('name', 'slug', 'gender', 'shoe_type', 'parent', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'gender', 'shoe_type', 'parent', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('sort_order', 'name')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [CategoryTranslationInline]
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Shoes'), {'fields': ('gender', 'shoe_type')}),
        (_('Hierarchy'), {'fields': ('parent',)}),
        (_('Settings'), {'fields': ('is_active', 'sort_order')}),
        (_('External'), {'fields': ('external_id', 'external_data')}),
        (_('Подсказка'), {
            'fields': (),
            'description': _(
                "Древо обуви предзаполнено: верхний уровень — Женская/Мужская/Унисекс/Детская обувь; "
                "под ними — Кроссовки, Ботинки, Сандалии, Туфли, Домашняя обувь. "
                "При необходимости добавляйте новые типы или меняйте сортировку."
            )
        }),
    )
    
    def get_queryset(self, request):
        """Фильтруем только корневые категории обуви (где shoe_type не пустое)."""
        return super().get_queryset(request).filter(shoe_type__isnull=False).exclude(shoe_type='').filter(parent__isnull=True)


class ShoeVariantInline(admin.TabularInline):
    """Инлайн для вариантов обуви (основные поля)."""
    model = ShoeVariant
    extra = 0
    fields = (
        'name', 'slug',
        'color',
        'price', 'currency',
        'main_image',
        'is_active', 'sort_order',
    )
    readonly_fields = ('slug',)
    show_change_link = True


class ShoeVariantSizeInline(admin.TabularInline):
    """Инлайн размеров варианта обуви."""
    model = ShoeVariantSize
    extra = 0
    fields = ('size', 'is_available', 'stock_quantity', 'sort_order')
    ordering = ('sort_order', 'size')


@admin.register(ShoeVariant)
class ShoeVariantAdmin(admin.ModelAdmin):
    """Отдельная админка варианта обуви (для картинок)."""
    list_display = ('name', 'product', 'color', 'price', 'currency', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'color', 'currency', 'created_at')
    search_fields = ('name', 'product__name', 'slug', 'color', 'sku', 'barcode', 'gtin', 'mpn')
    ordering = ('product', 'sort_order', '-created_at')
    readonly_fields = ('slug',)
    fieldsets = (
        (None, {'fields': ('product', 'name', 'slug')}),
        (_('Характеристики'), {
            'fields': ('color',),
            'description': _("Размеры задайте в таблице размеров ниже.")
        }),
        (_('Цены и наличие'), {'fields': ('price', 'currency', 'old_price')}),
        (_('Медиа'), {'fields': ('main_image',)}),
        (_('Идентификаторы'), {'fields': ('sku', 'barcode', 'gtin', 'mpn')}),
        (_('Внешние данные'), {'fields': ('external_id', 'external_url', 'external_data')}),
        (_('Статус'), {'fields': ('is_active', 'sort_order')}),
    )
    inlines = [ShoeVariantSizeInline, ShoeVariantImageInline]


@admin.register(ShoeProduct)
class ShoeProductAdmin(admin.ModelAdmin):
    """Админка для товаров обуви."""
    list_display = ('name', 'slug', 'category', 'brand', 'price', 'currency', 'is_active', 'created_at')
    list_filter = ('is_active', 'is_featured', 'category', 'brand', 'heel_height', 'currency', 'created_at')
    search_fields = ('name', 'slug', 'description', 'material')
    ordering = ('-created_at',)
    prepopulated_fields = {'slug': ('name',)}
    exclude = ('size', 'color', 'stock_quantity', 'is_available')
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Categorization'), {'fields': ('category', 'brand')}),
        (_('Shoes'), {'fields': ('material', 'heel_height', 'sole_type')}),
        (_('Pricing'), {'fields': ('price', 'currency', 'old_price')}),
        (_('Availability'), {'fields': ()}),
        (_('Media'), {'fields': ('main_image',)}),
        (_('Settings'), {'fields': ('is_active', 'is_featured')}),
        (_('External'), {'fields': ('external_id', 'external_url', 'external_data')}),
    )
    # Галерея для обуви теперь задается на уровне варианта (цвета), поэтому инлайн изображений товара убран
    inlines = [ShoeProductTranslationInline, ShoeVariantInline]


@admin.register(CategoryElectronics)
class ElectronicsCategoryAdmin(admin.ModelAdmin):
    """Админка для категорий электроники."""
    list_display = ('name', 'slug', 'device_type', 'parent', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'device_type', 'parent', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('sort_order', 'name')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [CategoryTranslationInline]
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Electronics'), {'fields': ('device_type',)}),
        (_('Hierarchy'), {'fields': ('parent',)}),
        (_('Settings'), {'fields': ('is_active', 'sort_order')}),
        (_('External'), {'fields': ('external_id', 'external_data')}),
    )
    
    def get_queryset(self, request):
        """Фильтруем только корневые категории электроники (где device_type не пустое)."""
        return super().get_queryset(request).filter(device_type__isnull=False).exclude(device_type='').filter(parent__isnull=True)


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
    inlines = [ElectronicsProductTranslationInline, ElectronicsProductImageInline]


@admin.register(FurnitureVariant)
class FurnitureVariantAdmin(admin.ModelAdmin):
    """Отдельная админка варианта мебели (для картинок)."""
    list_display = ('name', 'product', 'color', 'price', 'currency', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'color', 'currency', 'created_at')
    search_fields = ('name', 'product__name', 'slug', 'color', 'sku', 'barcode', 'gtin', 'mpn')
    ordering = ('product', 'sort_order', '-created_at')
    readonly_fields = ('slug',)
    fieldsets = (
        (None, {'fields': ('product', 'name', 'slug')}),
        (_('Характеристики'), {
            'fields': ('color',),
        }),
        (_('Цены и наличие'), {'fields': ('price', 'currency', 'old_price')}),
        (_('Медиа'), {'fields': ('main_image',)}),
        (_('Идентификаторы'), {'fields': ('sku', 'barcode', 'gtin', 'mpn')}),
        (_('Внешние данные'), {'fields': ('external_id', 'external_url', 'external_data')}),
        (_('Статус'), {'fields': ('is_active', 'sort_order')}),
    )
    inlines = [FurnitureVariantImageInline]


@admin.register(FurnitureProduct)
class FurnitureProductAdmin(admin.ModelAdmin):
    """Админка для товаров мебели."""
    list_display = ('name', 'slug', 'category', 'brand', 'price', 'currency', 'is_active', 'created_at')
    list_filter = ('is_active', 'is_featured', 'category', 'brand', 'furniture_type', 'currency', 'created_at')
    search_fields = ('name', 'slug', 'description', 'material', 'furniture_type')
    ordering = ('-created_at',)
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Categorization'), {'fields': ('category', 'brand')}),
        (_('Furniture'), {'fields': ('material', 'furniture_type', 'dimensions')}),
        (_('Pricing'), {'fields': ('price', 'currency', 'old_price')}),
        (_('Availability'), {'fields': ('is_available', 'stock_quantity')}),
        (_('Media'), {'fields': ('main_image',)}),
        (_('Settings'), {'fields': ('is_active', 'is_featured')}),
        (_('External'), {'fields': ('external_id', 'external_url', 'external_data')}),
    )
    inlines = [FurnitureProductTranslationInline, FurnitureVariantInline]


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """Админка для услуг."""
    list_display = ('name', 'slug', 'category', 'service_type', 'price', 'currency', 'duration', 'is_active', 'created_at')
    list_filter = ('is_active', 'is_featured', 'category', 'service_type', 'currency', 'created_at')
    search_fields = ('name', 'slug', 'description', 'service_type')
    ordering = ('-created_at',)
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Categorization'), {'fields': ('category',)}),
        (_('Service'), {'fields': ('service_type', 'duration')}),
        (_('Pricing'), {'fields': ('price', 'currency')}),
        (_('Media'), {'fields': ('main_image',)}),
        (_('Settings'), {'fields': ('is_active', 'is_featured')}),
        (_('External'), {'fields': ('external_id', 'external_url', 'external_data')}),
    )
    inlines = [ServiceTranslationInline]


class BannerMediaInline(admin.StackedInline):
    """Inline для медиа-файлов баннера."""
    model = BannerMedia
    extra = 1
    fieldsets = (
        (None, {'fields': ('content_type', 'sort_order')}),
        (_('Изображение'), {'fields': ('image', 'image_url')}),
        (_('Видео'), {'fields': ('video_file', 'video_url')}),
        (_('GIF'), {'fields': ('gif_file', 'gif_url')}),
        (_('Текст и ссылка'), {
            'fields': ('title', 'description', 'link_text', 'link_url'),
            'description': _('Текст и ссылка для этого медиа-элемента. Если пусто, используются данные баннера.')
        }),
    )
    verbose_name = _("Медиа-файл")
    verbose_name_plural = _("Медиа-файлы")


@admin.register(MarketingBanner)
class BannerAdmin(admin.ModelAdmin):
    """Админка для баннеров."""
    list_display = ('title', 'position', 'get_media_count', 'is_active', 'sort_order', 'created_at')
    list_filter = ('position', 'is_active', 'created_at')
    search_fields = ('title',)
    ordering = ('position', 'sort_order', '-created_at')
    inlines = [BannerMediaInline]
    
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'position', 'is_active', 'sort_order'),
            'description': _('Заголовок и описание баннера используются как значения по умолчанию для всех медиа-файлов, если у них не указаны свои значения.')
        }),
        (_('Ссылка'), {
            'fields': ('link_url', 'link_text'),
            'description': _('Ссылка и текст кнопки баннера используются как значения по умолчанию для всех медиа-файлов, если у них не указаны свои значения.')
        }),
    )
    
    def get_media_count(self, obj):
        """Количество медиа-файлов в баннере."""
        if obj.pk:
            return obj.media_files.count()
        return 0
    get_media_count.short_description = _("Количество медиа")


@admin.register(MarketingBannerMedia)
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
        (_('Текст и ссылка'), {
            'fields': ('title', 'description', 'link_text', 'link_url'),
            'description': _('Текст и ссылка для этого медиа-элемента. Если пусто, используются данные баннера.')
        }),
    )
    
    def get_fieldsets(self, request, obj=None):
        """Динамически показываем только нужные поля в зависимости от типа контента."""
        # Базовые поля, которые всегда показываются
        base_fields = (None, {'fields': ('banner', 'content_type', 'sort_order')})
        text_fields = (_('Текст и ссылка'), {
            'fields': ('title', 'description', 'link_text', 'link_url'),
            'description': _('Текст и ссылка для этого медиа-элемента. Если пусто, используются данные баннера.')
        })
        
        if obj:
            # Для существующего объекта показываем поля в зависимости от типа контента
            if obj.content_type == 'image':
                return [
                    base_fields,
                    (_('Изображение'), {
                        'fields': ('image', 'image_url'),
                        'description': _('Загрузите изображение локально или укажите внешний URL')
                    }),
                    text_fields,
                ]
            elif obj.content_type == 'video':
                return [
                    base_fields,
                    (_('Видео'), {
                        'fields': ('video_file', 'video_url'),
                        'description': _('Загрузите видеофайл локально или укажите внешний URL')
                    }),
                    text_fields,
                ]
            elif obj.content_type == 'gif':
                return [
                    base_fields,
                    (_('GIF'), {
                        'fields': ('gif_file', 'gif_url'),
                        'description': _('Загрузите GIF файл локально или укажите внешний URL')
                    }),
                    text_fields,
                ]
        
        # Для нового объекта показываем все поля
        return [
            base_fields,
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
            text_fields,
        ]
    
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


@admin.register(MarketingBrand)
class MarketingBrandAdmin(admin.ModelAdmin):
    """Админка для карточек популярных брендов (раздел «Маркетинг»)."""
    list_display = ('name', 'primary_category_slug', 'card_media_preview', 'is_active', 'created_at')
    list_filter = ('is_active', 'primary_category_slug', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('card_media_preview',)

    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Медиа карточки'), {
            'fields': ('card_media', 'card_media_external_url', 'card_media_preview', 'logo'),
            'description': _('Изображение, GIF или видео для карточки бренда или внешняя ссылка (CDN/S3). Внешняя ссылка приоритетнее.'),
        }),
        (_('Категория'), {'fields': ('primary_category_slug',)}),
        (_('Ссылки'), {'fields': ('website',)}),
        (_('Settings'), {'fields': ('is_active',)}),
        (_('External'), {'fields': ('external_id', 'external_data')}),
    )

    def card_media_preview(self, obj):
        """Отображает превью медиа-файла карточки бренда."""
        url = obj.get_card_media_url()
        if not url:
            return _("Нет медиа")
        lower_url = url.split('?')[0].lower()

        # YouTube превью (если ссылка не на файл с расширением)
        import re
        match = re.search(
            r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|m\.youtube\.com\/watch\?v=)([^"&?\/\s]{11})',
            url,
            re.IGNORECASE,
        ) or re.search(
            r'(?:youtube\.com\/shorts\/|m\.youtube\.com\/shorts\/)([^"&?\/\s]+)',
            url,
            re.IGNORECASE,
        )
        if match and match.group(1):
            thumb = f"https://img.youtube.com/vi/{match.group(1)}/hqdefault.jpg"
            return format_html(
                '<img src="{}" style="max-width: 180px; max-height: 100px;" />',
                thumb,
            )

        if lower_url.endswith(("mp4", "mov", "webm", "m4v")):
            return format_html(
                '<video src="{}" style="max-width: 180px; max-height: 100px;" muted loop playsinline></video>',
                url,
            )
        return format_html(
            '<img src="{}" style="max-width: 180px; max-height: 100px;" />',
            url,
        )
    card_media_preview.short_description = _("Превью медиа")


@admin.register(MarketingCategory)
class MarketingCategoryAdmin(admin.ModelAdmin):
    """Админка для карточек категорий (раздел «Маркетинг»)."""
    from .forms import CategoryForm
    form = CategoryForm
    list_display = ('name', 'slug', 'category_type', 'card_media_preview', 'is_active', 'sort_order', 'created_at')
    list_filter = (ActiveRootFilter, 'is_active', TopLevelCategoryFilter, 'category_type', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('sort_order', 'name')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('card_media_preview',)
    autocomplete_fields = ('category_type',)
    inlines = [CategoryTranslationInline]

    fieldsets = (
        (_('Основная информация'), {
            'fields': ('name', 'slug', 'description'),
            'description': _('Введите название категории. Slug будет автоматически сгенерирован из названия.'),
        }),
        (_('Тип категории (обязательно)'), {
            'fields': ('category_type',),
            'description': _(
                '⚠️ ВАЖНО: Выберите тип категории из списка. Если нужного типа нет, создайте его в разделе "Типы категорий".\n'
                'Это определяет, к какому разделу товаров относится категория.'
            ),
        }),
        (_('Иерархия'), {
            'fields': ('parent',),
            'description': _('Оставьте пустым для создания корневой категории, или выберите родительскую категорию для создания подкатегории.'),
        }),
        (_('Медиа карточки'), {
            'fields': ('card_media', 'card_media_external_url', 'card_media_preview'),
            'description': _('Изображение, GIF или видео для карточки категории или внешняя ссылка (CDN/S3). Внешняя ссылка приоритетнее.'),
        }),
        (_('Настройки'), {
            'fields': ('is_active', 'sort_order'),
            'description': _('Активируйте категорию, чтобы она отображалась на сайте. Порядок сортировки определяет последовательность отображения.'),
        }),
        (_('Внешние данные'), {
            'fields': ('external_id', 'external_data'),
            'classes': ('collapse',),
        }),
    )

    def card_media_preview(self, obj):
        """Отображает превью медиа-файла карточки категории."""
        url = obj.get_card_media_url()
        if not url:
            return _("Нет медиа")
        lower_url = url.split('?')[0].lower()

        # YouTube превью (если ссылка не на файл с расширением)
        import re
        match = re.search(
            r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|m\.youtube\.com\/watch\?v=)([^"&?\/\s]{11})',
            url,
            re.IGNORECASE,
        ) or re.search(
            r'(?:youtube\.com\/shorts\/|m\.youtube\.com\/shorts\/)([^"&?\/\s]+)',
            url,
            re.IGNORECASE,
        )
        if match and match.group(1):
            thumb = f"https://img.youtube.com/vi/{match.group(1)}/hqdefault.jpg"
            return format_html(
                '<img src="{}" style="max-width: 180px; max-height: 100px;" />',
                thumb,
            )

        if lower_url.endswith(("mp4", "mov", "webm", "m4v")):
            return format_html(
                '<video src="{}" style="max-width: 180px; max-height: 100px;" muted loop playsinline></video>',
                url,
            )
        return format_html(
            '<img src="{}" style="max-width: 180px; max-height: 100px;" />',
            url,
        )
    card_media_preview.short_description = _("Превью медиа")


@admin.register(MarketingRootCategory)
class MarketingRootCategoryAdmin(admin.ModelAdmin):
    """Отдельный раздел для корневых маркетинговых категорий."""
    from .forms import CategoryForm
    form = CategoryForm
    list_display = ('name', 'slug', 'category_type', 'card_media_preview', 'is_active', 'sort_order', 'created_at')
    list_filter = (ActiveRootFilter, 'is_active', 'category_type', 'created_at')
    search_fields = ('name', 'slug', 'description')
    ordering = ('sort_order', 'name')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('card_media_preview',)
    exclude = ('parent',)
    autocomplete_fields = ('category_type',)
    inlines = [CategoryTranslationInline]
    
    fieldsets = (
        (_('Основная информация'), {
            'fields': ('name', 'slug', 'description'),
            'description': _('Введите название новой корневой категории. Slug будет автоматически сгенерирован из названия.'),
        }),
        (_('Тип категории (обязательно)'), {
            'fields': ('category_type',),
            'description': _(
                '⚠️ ВАЖНО: Выберите тип категории из списка. Если нужного типа нет, создайте его в разделе "Типы категорий".\n'
                'Это определяет, к какому разделу товаров относится категория.'
            ),
        }),
        (_('Медиа карточки'), {
            'fields': ('card_media', 'card_media_external_url', 'card_media_preview'),
            'description': _('Изображение, GIF или видео для карточки категории или внешняя ссылка (CDN/S3). Внешняя ссылка приоритетнее.'),
        }),
        (_('Настройки'), {
            'fields': ('is_active', 'sort_order'),
            'description': _('Активируйте категорию, чтобы она отображалась на сайте. Порядок сортировки определяет последовательность отображения.'),
        }),
        (_('Внешние данные'), {
            'fields': ('external_id', 'external_data'),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(parent__isnull=True)

    def save_model(self, request, obj, form, change):
        # Всегда сохраняем как корневую категорию
        obj.parent = None
        # Проверяем, что тип категории выбран (из формы или объекта)
        category_type = form.cleaned_data.get('category_type') or obj.category_type
        if not category_type:
            raise ValidationError(_('Необходимо выбрать тип категории! Создайте тип в разделе "Типы категорий", если его нет.'))
        # Убеждаемся, что тип категории установлен (из формы)
        if form.cleaned_data.get('category_type'):
            obj.category_type = form.cleaned_data['category_type']
        super().save_model(request, obj, form, change)

    def card_media_preview(self, obj):
        """Отображает превью медиа-файла карточки категории."""
        url = obj.get_card_media_url()
        if not url:
            return _("Нет медиа")
        lower_url = url.split('?')[0].lower()

        # YouTube превью (если ссылка не на файл с расширением)
        import re
        match = re.search(
            r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|m\.youtube\.com\/watch\?v=)([^"&?\/\s]{11})',
            url,
            re.IGNORECASE,
        ) or re.search(
            r'(?:youtube\.com\/shorts\/|m\.youtube\.com\/shorts\/)([^"&?\/\s]+)',
            url,
            re.IGNORECASE,
        )
        if match and match.group(1):
            thumb = f"https://img.youtube.com/vi/{match.group(1)}/hqdefault.jpg"
            return format_html(
                '<img src="{}" style="max-width: 180px; max-height: 100px;" />',
                thumb,
            )

        if lower_url.endswith(("mp4", "mov", "webm", "m4v")):
            return format_html(
                '<video src="{}" style="max-width: 180px; max-height: 100px;" muted loop playsinline></video>',
                url,
            )
        return format_html(
            '<img src="{}" style="max-width: 180px; max-height: 100px;" />',
            url,
        )
    card_media_preview.short_description = _("Превью медиа")
