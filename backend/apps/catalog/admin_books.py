"""Админки для моделей книг."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Author, ProductAuthor, Product, BookVariant, BookVariantSize, BookVariantImage


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


class BookVariantInline(admin.TabularInline):
    """Inline для вариантов книг в ProductBooks."""
    model = BookVariant
    extra = 1
    fields = ('name', 'cover_type', 'format_type', 'price', 'currency', 'is_active', 'sort_order')


@admin.register(Product)
class ProductBooksAdmin(admin.ModelAdmin):
    """Админка для товаров-книг."""
    list_display = [
        'name', 'authors_list', 'category', 'brand', 'price', 
        'old_price', 'rating', 'is_available', 'is_bestseller',
        'is_new', 'isbn', 'publisher', 'created_at'
    ]
    list_filter = [
        'category', 'brand', 'is_available', 'is_bestseller', 'is_new', 
        'created_at', 'rating', 'publisher'
    ]
    list_editable = ['price', 'old_price', 'is_available', 'is_bestseller']
    search_fields = ['name', 'description', 'isbn', 'publisher']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['rating', 'reviews_count', 'created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'category', 'brand', 'book_authors')
        }),
        ('Описание', {
            'fields': ('description',)
        }),
        ('Цена', {
            'fields': ('price', 'old_price', 'currency')
        }),
        ('Информация о книге', {
            'fields': ('isbn', 'publisher', 'publication_date', 'pages', 'language', 'cover_type')
        }),
        ('Рейтинг и отзывы', {
            'fields': ('rating', 'reviews_count')
        }),
        ('Статус', {
            'fields': ('is_available', 'is_featured', 'is_bestseller', 'is_new')
        }),
        ('Изображение', {
            'fields': ('main_image',)
        }),
        ('Метаданные', {
            'classes': ('collapse',),
            'fields': ('meta_title', 'meta_description', 'meta_keywords', 'og_title', 'og_description', 'og_image_url')
        }),
    )
    
    def authors_list(self, obj):
        """Список авторов через запятую."""
        authors = obj.book_authors.all()
        return ', '.join([pa.author.full_name for pa in authors])
    authors_list.short_description = 'Авторы'
    
    def get_queryset(self, request):
        """Фильтруем только книги."""
        return super().get_queryset(request).filter(product_type='books')
    
    def get_inline_instances(self, request, obj=None):
        """Добавляем inline для вариантов книг только для книг."""
        inlines = super().get_inline_instances(request, obj)
        if obj and obj.product_type == 'books':
            inlines.append(BookVariantInline(self.model.admin_site, self.model))
        return inlines


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    """Админка для авторов книг."""
    list_display = ['full_name', 'birth_date', 'created_at']
    list_filter = ['birth_date', 'created_at']
    search_fields = ['first_name', 'last_name']
    readonly_fields = ['created_at', 'updated_at']
    
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name.short_description = 'Полное имя'


@admin.register(ProductAuthor)
class ProductAuthorAdmin(admin.ModelAdmin):
    """Админка для связи товаров с авторами."""
    list_display = ['product', 'author', 'created_at']
    list_filter = ['created_at']
    search_fields = ['product__name', 'author__first_name', 'author__last_name']
    readonly_fields = ['created_at']
