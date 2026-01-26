"""Админки для моделей книг."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.db import models as django_models
from .models import (
    Author, ProductAuthor, Product, ProductBooks, 
    Category, CategoryBooks,
    BookVariant, BookVariantSize, BookVariantImage,
    ProductTranslation, ProductImage, ProductAttribute
)


class BookVariantSizeInline(admin.TabularInline):
    """Inline для форматов вариантов книг."""
    model = BookVariantSize
    extra = 1
    fields = ('size', 'is_available', 'stock_quantity', 'sort_order')


class BookVariantImageInline(admin.TabularInline):
    """Inline для изображений вариантов книг."""
    model = BookVariantImage
    extra = 1
    fields = ('image_url', 'alt_text', 'is_main', 'sort_order')


@admin.register(BookVariant)
class BookVariantAdmin(admin.ModelAdmin):
    """Админка для вариантов книг."""
    list_display = ('name', 'product', 'cover_type', 'format_type', 'price', 'currency', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'cover_type', 'format_type', 'currency', 'created_at')
    search_fields = ('name', 'product__name', 'slug', 'cover_type', 'format_type', 'sku', 'barcode')
    ordering = ('product', 'sort_order', '-created_at')
    readonly_fields = ('slug',)
    fieldsets = (
        (None, {'fields': ('product', 'name', 'slug')}),
        (_('Характеристики'), {
            'fields': ('cover_type', 'format_type', 'isbn'),
            'description': _("Форматы задайте в таблице форматов ниже.")
        }),
        (_('Цены и наличие'), {'fields': ('price', 'currency', 'old_price', 'is_available', 'stock_quantity')}),
        (_('Медиа'), {'fields': ('main_image',)}),
        (_('Идентификаторы'), {'fields': ('sku', 'barcode')}),
        (_('Внешние данные'), {'fields': ('external_id', 'external_url', 'external_data')}),
        (_('Статус'), {'fields': ('is_active', 'sort_order')}),
    )
    inlines = [BookVariantSizeInline, BookVariantImageInline]


class ProductTranslationInline(admin.TabularInline):
    """Inline для переводов товара."""
    model = ProductTranslation
    extra = 1
    fields = ('locale', 'description')
    verbose_name = _('Перевод')
    verbose_name_plural = _('Переводы')


class ProductImageInline(admin.TabularInline):
    """Inline для изображений товара."""
    model = ProductImage
    extra = 1
    fields = ('image_url', 'alt_text', 'is_main', 'sort_order', 'image_preview')
    readonly_fields = ('image_preview',)
    verbose_name = _('Изображение')
    verbose_name_plural = _('Изображения')
    
    def image_preview(self, obj):
        if obj and obj.image_url:
            return format_html(
                '<img src="{}" style="max-width: 100px; max-height: 100px;" />',
                obj.image_url
            )
        return "-"
    image_preview.short_description = _("Превью")


class ProductAttributeInline(admin.TabularInline):
    """Inline для атрибутов товара."""
    model = ProductAttribute
    extra = 1
    fields = ('attribute_type', 'name', 'value', 'sort_order')
    verbose_name = _('Атрибут')
    verbose_name_plural = _('Атрибуты')


class ProductAuthorInline(admin.TabularInline):
    """Inline для авторов книги."""
    model = ProductAuthor
    extra = 1
    fields = ('author', 'sort_order')
    autocomplete_fields = ['author']
    verbose_name = _('Автор')
    verbose_name_plural = _('Авторы')


class BookVariantInline(admin.TabularInline):
    """Inline для вариантов книг в ProductBooks."""
    model = BookVariant
    extra = 0
    fields = ('name', 'cover_type', 'format_type', 'price', 'currency', 'is_active', 'sort_order')


@admin.register(ProductBooks)
class ProductBooksAdmin(admin.ModelAdmin):
    """Админка для товаров-книг."""
    list_display = [
        'name', 'authors_list', 'category', 'price', 
        'old_price', 'rating', 'is_available', 'is_bestseller',
        'is_new', 'isbn', 'publisher', 'created_at'
    ]
    list_filter = [
        'category', 'is_available', 'is_bestseller', 'is_new', 
        'created_at', 'rating', 'publisher', 'language'
    ]
    list_editable = ['price', 'old_price', 'is_available', 'is_bestseller']
    search_fields = ['name', 'description', 'isbn', 'publisher']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['product_type', 'rating', 'reviews_count', 'slug_preview', 'last_synced_at', 'created_at', 'updated_at']
    
    fieldsets = (
        (_('Основное'), {
            'fields': ('name', 'slug', 'slug_preview', 'description')
        }),
        (_('Категоризация'), {
            'fields': ('product_type', 'category')
        }),
        (_('Информация о книге'), {
            'fields': ('isbn', 'publisher', 'publication_date', 'pages', 'language', 'cover_type')
        }),
        (_('Цены и наличие'), {
            'fields': (
                'price', 'currency', 'old_price', 'margin_percent_applied',
                'availability_status', 'is_available', 'stock_quantity',
                'min_order_quantity', 'pack_quantity'
            )
        }),
        (_('Рейтинг и статус'), {
            'fields': ('rating', 'reviews_count', 'is_featured', 'is_bestseller', 'is_new')
        }),
        (_('Логистика'), {
            'fields': (
                'gtin', 'mpn', 'weight_value', 'weight_unit', 'length',
                'width', 'height', 'dimensions_unit', 'country_of_origin'
            ),
            'classes': ('collapse',)
        }),
        (_('SEO (EN)'), {
            'fields': (
                'meta_title', 'meta_description', 'meta_keywords',
                'og_title', 'og_description', 'og_image_url'
            ),
            'classes': ('collapse',),
            'description': _('Англоязычные SEO-поля и OpenGraph используются на сайте и в соцсетях.')
        }),
        (_('Медиа'), {
            'fields': ('main_image',)
        }),
        (_('Мета'), {
            'fields': ('sku', 'barcode'),
            'classes': ('collapse',)
        }),
        (_('Внешние данные'), {
            'fields': ('external_id', 'external_url', 'external_data'),
            'classes': ('collapse',)
        }),
        (_('Синхронизация'), {
            'fields': ('last_synced_at',),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [ProductAuthorInline, ProductTranslationInline, ProductImageInline, ProductAttributeInline, BookVariantInline]
    
    def authors_list(self, obj):
        """Список авторов через запятую."""
        authors = obj.book_authors.all()
        return ', '.join([pa.author.full_name for pa in authors]) if authors else '-'
    authors_list.short_description = _('Авторы')
    
    def get_queryset(self, request):
        """Фильтруем только книги."""
        return super().get_queryset(request).filter(product_type='books')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Фильтруем категории только для книг."""
        if db_field.name == 'category':
            kwargs['queryset'] = Category.objects.filter(
                django_models.Q(slug='books') | 
                django_models.Q(parent__slug='books')
            ).order_by('name')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def slug_preview(self, obj):
        """Предпросмотр slug."""
        if obj:
            return format_html('<code>{}</code>', obj.slug)
        return "-"
    slug_preview.short_description = _("Slug (предпросмотр)")
    
    def save_model(self, request, obj, form, change):
        """Автоматически устанавливаем product_type='books'."""
        obj.product_type = 'books'
        super().save_model(request, obj, form, change)


@admin.register(CategoryBooks)
class CategoryBooksAdmin(admin.ModelAdmin):
    """Админка для категорий книг (жанров)."""
    list_display = ('name', 'slug', 'parent', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'parent', 'created_at')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('sort_order', 'name')
    
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'parent', 'description')
        }),
        (_('Настройки'), {
            'fields': ('is_active', 'sort_order')
        }),
    )
    
    def get_queryset(self, request):
        """Показываем только категории книг."""
        qs = super().get_queryset(request)
        return qs.filter(
            django_models.Q(slug='books') | 
            django_models.Q(parent__slug='books')
        )
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Родительская категория может быть только 'books'."""
        if db_field.name == 'parent':
            kwargs['queryset'] = Category.objects.filter(slug='books')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    """Админка для авторов книг."""
    list_display = ['full_name', 'birth_date', 'books_count', 'created_at']
    list_filter = ['birth_date', 'created_at']
    search_fields = ['first_name', 'last_name']
    readonly_fields = ['created_at', 'updated_at']
    
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name.short_description = _('Полное имя')
    
    def books_count(self, obj):
        return obj.books.count()
    books_count.short_description = _('Количество книг')


# ProductAuthor скрыт из меню - управляется через inline в ProductBooksAdmin
# Но регистрируем для возможности прямого доступа при необходимости
@admin.register(ProductAuthor)
class ProductAuthorAdmin(admin.ModelAdmin):
    """Админка для связи товаров с авторами (скрыто из меню)."""
    list_display = ['product', 'author', 'sort_order', 'created_at']
    list_filter = ['created_at']
    search_fields = ['product__name', 'author__first_name', 'author__last_name']
    readonly_fields = ['created_at']
    
    def get_model_perms(self, request):
        """Скрываем из меню админки."""
        return {}
