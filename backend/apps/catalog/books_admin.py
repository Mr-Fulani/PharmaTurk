"""Админки для моделей книг."""

from django.contrib import admin
from .models import Author, ProductAuthor, Product


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


class ProductBooksAdmin(admin.ModelAdmin):
    """Админка для товаров-книг."""
    list_display = [
        'name', 'authors_list', 'category', 'price', 
        'old_price', 'rating', 'is_available', 'is_bestseller',
        'is_new', 'isbn', 'publisher', 'created_at'
    ]
    list_filter = [
        'category', 'is_available', 'is_bestseller', 'is_new', 
        'created_at', 'rating', 'publisher'
    ]
    list_editable = ['price', 'old_price', 'is_available', 'is_bestseller']
    search_fields = ['name', 'description', 'isbn', 'publisher']
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ['book_authors']
    readonly_fields = ['rating', 'reviews_count', 'created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'category', 'book_authors')
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


# Регистрируем админку для книг
admin.site.register(Product, ProductBooksAdmin)
