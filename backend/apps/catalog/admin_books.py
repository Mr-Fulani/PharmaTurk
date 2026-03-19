"""Админки для моделей книг."""

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.db import models as django_models

from .forms import PRODUCT_CATEGORY_HELP
from .models import (
    Author, ProductAuthor, BookProduct,
    BookProductTranslation, BookProductImage,
    Category, CategoryBooks,
    BookVariant, BookVariantSize, BookVariantImage,
    ProductGenre, CategoryTranslation
)


@admin.action(description=_("Сделать активными"))
def activate_book_variants(modeladmin, request, queryset):
    queryset.update(is_active=True)


@admin.action(description=_("Сделать неактивными"))
def deactivate_book_variants(modeladmin, request, queryset):
    queryset.update(is_active=False)


class BookVariantSizeInline(admin.TabularInline):
    """Inline для форматов вариантов книг."""
    model = BookVariantSize
    extra = 1
    fields = ('size', 'is_available', 'stock_quantity', 'sort_order')


class BookVariantImageInline(admin.TabularInline):
    """Inline для изображений вариантов книг."""
    model = BookVariantImage
    extra = 1
    fields = ('image_file', 'image_url', 'alt_text', 'is_main', 'sort_order')


@admin.register(BookVariant)
class BookVariantAdmin(admin.ModelAdmin):
    """Админка для вариантов книг."""
    list_display = ('name', 'product', 'cover_type', 'format_type', 'price', 'currency', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'cover_type', 'format_type', 'currency', 'created_at')
    search_fields = ('name', 'product__name', 'slug', 'cover_type', 'format_type', 'sku', 'barcode')
    ordering = ('product', 'sort_order', '-created_at')
    readonly_fields = ('slug',)
    actions = [activate_book_variants, deactivate_book_variants]
    fieldsets = (
        (None, {'fields': ('product', 'name', 'name_en', 'slug')}),
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


class BookProductTranslationInline(admin.TabularInline):
    """Inline для переводов книги."""
    model = BookProductTranslation
    extra = 1
    fields = ('locale', 'name', 'description')
    verbose_name = _('Перевод')
    verbose_name_plural = _('Переводы')


class BookProductImageInline(admin.TabularInline):
    """Inline для изображений книги."""
    model = BookProductImage
    extra = 1
    fields = ('image_file', 'image_url', 'alt_text', 'is_main', 'sort_order')
    readonly_fields = ('image_preview',)
    verbose_name = _('Изображение')
    verbose_name_plural = _('Изображения')
    
    def image_preview(self, obj):
        if obj:
            media_url = None
            if obj.image_file:
                media_url = obj.image_file.url
            elif obj.image_url:
                media_url = obj.image_url
            if media_url:
                return format_html(
                    '<img src="{}" style="max-width: 100px; max-height: 100px;" />',
                    media_url
                )
        return "-"
    image_preview.short_description = _("Превью")


class ProductAuthorInline(admin.TabularInline):
    """Inline для авторов книги."""
    model = ProductAuthor
    extra = 1
    fields = ('author', 'sort_order')
    autocomplete_fields = ['author']
    verbose_name = _('Автор')
    verbose_name_plural = _('Авторы')


class ProductGenreInline(admin.TabularInline):
    """Inline для жанров книги."""
    model = ProductGenre
    extra = 1
    fields = ('genre', 'sort_order')
    verbose_name = _('Жанр')
    verbose_name_plural = _('Жанры')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'genre':
            kwargs['queryset'] = Category.objects.filter(
                django_models.Q(slug='books') |
                django_models.Q(parent__slug='books')
            ).order_by('name')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class BookVariantInline(admin.TabularInline):
    """Inline для вариантов книг в BookProduct."""
    model = BookVariant
    extra = 0
    fields = ('name', 'name_en', 'cover_type', 'format_type', 'price', 'currency', 'main_image', 'is_active', 'sort_order')


@admin.register(BookProduct)
class BookProductAdmin(admin.ModelAdmin):
    """Админка для товаров-книг."""
    actions = ["run_ai", "run_ai_auto_apply", "run_find_merge_duplicates"]
    list_display = [
        'name', 'authors_list', 'category', 'price', 
        'old_price', 'is_available', 'is_bestseller',
        'is_new', 'isbn', 'publisher', 'created_at'
    ]
    list_filter = [
        'category', 'is_available', 'is_bestseller', 'is_new', 
        'created_at', 'rating', 'publisher', 'language'
    ]
    list_editable = ['price', 'old_price', 'is_available', 'is_bestseller']
    search_fields = ['name', 'description', 'isbn', 'publisher']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['rating', 'reviews_count', 'slug_preview', 'created_at', 'updated_at']
    
    fieldsets = (
        (_('Основное'), {
            'fields': ('name', 'slug', 'slug_preview', 'description')
        }),
        (_('Категоризация'), {
            'fields': ('category', 'brand'),
            'description': PRODUCT_CATEGORY_HELP,
        }),
        (_('Информация о книге'), {
            'fields': ('isbn', 'publisher', 'publication_date', 'pages', 'language', 'cover_type')
        }),
        (_('Цены и наличие'), {
            'fields': ('price', 'currency', 'old_price', 'is_available', 'stock_quantity')
        }),
        (_('Рейтинг и статус'), {
            'fields': ('rating', 'reviews_count', 'is_featured', 'is_bestseller', 'is_new')
        }),
        (_("SEO (EN)"), {
            'fields': (
                'meta_title', 'meta_description', 'meta_keywords',
                'og_title', 'og_description', 'og_image_url'
            ),
            'description': _("Англоязычные SEO-поля и OpenGraph.")
        }),
        (_('Медиа'), {
            'fields': ('main_image', 'main_image_file')
        }),
        (_('Внешние данные'), {
            'fields': ('external_id', 'external_url', 'external_data'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [ProductAuthorInline, ProductGenreInline, BookProductTranslationInline, BookProductImageInline, BookVariantInline]

    def delete_queryset(self, request, queryset):
        """При удалении книг в админке удаляем и базовый Product, чтобы товар пропал с фронта."""
        from apps.catalog.models import Product
        base_ids = list(queryset.values_list("base_product_id", flat=True).distinct())
        super().delete_queryset(request, queryset)
        if base_ids:
            Product.objects.filter(pk__in=base_ids).delete()

    def delete_model(self, request, obj):
        """При удалении одной книги удаляем и базовый Product."""
        from apps.catalog.models import Product
        base_id = obj.base_product_id
        super().delete_model(request, obj)
        if base_id:
            Product.objects.filter(pk=base_id).delete()

    def authors_list(self, obj):
        """Список авторов через запятую."""
        authors = obj.book_authors.all()
        return ', '.join([pa.author.full_name for pa in authors]) if authors else '-'
    authors_list.short_description = _('Авторы')
    
    def get_queryset(self, request):
        """Книги — теперь из собственной таблицы."""
        return super().get_queryset(request)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Показываем все категории книг (L1, L2, L3) для выбора при привязке товара."""
        if db_field.name == 'category':
            kwargs['queryset'] = Category.objects.filter(
                category_type__slug='books',
                is_active=True,
            ).order_by('sort_order', 'name')
            kwargs['help_text'] = PRODUCT_CATEGORY_HELP
        elif db_field.name == 'genre':
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

    def run_ai(self, request, queryset):
        """Поставить выбранные товары в очередь AI; результат — в логах, применить вручную после одобрения."""
        from apps.ai.tasks import process_product_ai_task
        for book in queryset:
            process_product_ai_task.delay(
                product_id=book.base_product_id,
                processing_type="full",
                auto_apply=False,
            )
        self.message_user(
            request,
            _("Запущена полная AI обработка для %(count)s товаров. Результаты появятся в разделе «Логи AI»; применить к товару — вручную после одобрения.")
            % {"count": queryset.count()},
            level=messages.SUCCESS,
        )
    run_ai.short_description = _("Полная AI обработка (без авто-применения)")

    def run_ai_auto_apply(self, request, queryset):
        """Один запуск: полная обработка + авто-применение. Не нужно идти в «Логи AI»."""
        from apps.ai.tasks import process_product_ai_task
        for book in queryset:
            process_product_ai_task.delay(
                product_id=book.base_product_id,
                processing_type="full",
                auto_apply=True,
            )
        self.message_user(
            request,
            _("Запущена полная AI обработка с авто-применением для %(count)s товаров. Результаты будут применены к товарам автоматически после завершения.")
            % {"count": queryset.count()},
            level=messages.SUCCESS,
        )
    run_ai_auto_apply.short_description = _("Полная AI обработка + авто-применение")

    def run_find_merge_duplicates(self, request, queryset):
        """Запуск поиска и объединения дубликатов по всему каталогу."""
        from apps.scrapers.tasks import find_and_merge_duplicates
        find_and_merge_duplicates.delay()
        self.message_user(
            request,
            _("Запущен поиск и объединение дубликатов по всему каталогу. Результаты будут в логах Celery."),
            level=messages.SUCCESS,
        )
    run_find_merge_duplicates.short_description = _("Поиск и объединение дубликатов")

    def save_model(self, request, obj, form, change):
        """Сохраняем книгу."""
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
    
    class CategoryBooksTranslationInline(admin.TabularInline):
        model = CategoryTranslation
        extra = 1
        fields = ('locale', 'name', 'description')
        verbose_name = _('Перевод')
        verbose_name_plural = _('Переводы')

    inlines = [CategoryBooksTranslationInline]
    
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


# ProductAuthor скрыт из меню - управляется через inline в BookProductAdmin
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
