from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html, format_html_join
from decimal import Decimal

from .models import (
    IslamicClothingProduct, IslamicClothingProductTranslation, IslamicClothingProductImage, IslamicClothingProductSize,
    IslamicClothingVariant, IslamicClothingVariantSize, IslamicClothingVariantImage, Category
)
from .admin_base import AIStatusFilter, RunAIActionMixin, ShadowProductCleanupAdminMixin
from .admin import activate_variants, deactivate_variants, PRODUCT_CATEGORY_HELP, ProductAttributeValueInline
from .admin_variant_ai import VariantAIAdminMixin
from .admin_media import AdminMediaHelpTextMixin, resolve_media_url, render_media_preview

class CategoryFieldFilterMixin:
    category_field_name: str | None = None

    def get_category_queryset(self):
        if not self.category_field_name:
            return None
        from .models import Category
        # Support basic category lookup by type
        return Category.objects.filter(
            category_type__slug="islamic-clothing",
            is_active=True,
        ).order_by('sort_order', 'name')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'category':
            qs = self.get_category_queryset()
            if qs is not None:
                kwargs['queryset'] = qs
                kwargs['help_text'] = PRODUCT_CATEGORY_HELP
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

def _product_category_path(obj):
    if obj.category:
        return obj.category.get_breadcrumb_path()
    return "—"


class IslamicClothingProductTranslationInline(admin.StackedInline):
    model = IslamicClothingProductTranslation
    extra = 1
    fieldsets = (
        (None, {'fields': ('locale', 'name', 'description')}),
        (_('Локализованное SEO'), {
            'fields': ('meta_title', 'meta_description', 'meta_keywords', 'og_title', 'og_description'),
        }),
    )

class IslamicClothingProductSizeInline(admin.TabularInline):
    model = IslamicClothingProductSize
    extra = 0
    fields = ('size', 'is_available', 'stock_quantity', 'sort_order')
    ordering = ('sort_order', 'size')

class IslamicClothingVariantInline(AdminMediaHelpTextMixin, admin.TabularInline):
    model = IslamicClothingVariant
    extra = 0
    fields = ('name', 'name_en', 'slug', 'color', 'price', 'currency', 'main_image', 'main_image_file', 'is_active', 'sort_order')
    readonly_fields = ('slug',)
    show_change_link = True

class IslamicClothingProductImageInline(AdminMediaHelpTextMixin, admin.TabularInline):
    model = IslamicClothingProductImage
    extra = 0
    fields = ('image_file', 'image_url', 'alt_text', 'sort_order', 'is_main', 'image_preview')
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj:
            return render_media_preview(resolve_media_url(obj, 'image_file', 'image_url'), max_width=120, max_height=60)
        return "-"

class IslamicClothingVariantSizeInline(admin.TabularInline):
    model = IslamicClothingVariantSize
    extra = 0
    fields = ('size', 'is_available', 'stock_quantity', 'sort_order')
    ordering = ('sort_order', 'size')

class IslamicClothingVariantImageInline(AdminMediaHelpTextMixin, admin.TabularInline):
    model = IslamicClothingVariantImage
    extra = 0
    fields = ('image_file', 'image_url', 'alt_text', 'sort_order', 'is_main', 'image_preview')
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj:
            return render_media_preview(resolve_media_url(obj, 'image_file', 'image_url'), max_width=120, max_height=60)
        return "-"


@admin.register(IslamicClothingVariant)
class IslamicClothingVariantAdmin(AdminMediaHelpTextMixin, VariantAIAdminMixin, admin.ModelAdmin):
    variant_activation_action_names = ("activate_variants", "deactivate_variants")
    list_display = (
        'name', 'product', 'color', 'price', 'currency', 'effective_base', 'is_active', 'sort_order', 'created_at',
    )
    list_filter = ('is_active', 'color', 'currency', 'created_at')
    search_fields = ('name', 'product__name', 'slug', 'color', 'sku', 'barcode', 'gtin', 'mpn')
    ordering = ('product', 'sort_order', '-created_at')
    readonly_fields = ('slug', 'main_media_preview')
    actions = [activate_variants, deactivate_variants]
    fieldsets = (
        (None, {'fields': ('product', 'name', 'name_en', 'slug')}),
        (_('Характеристики'), {
            'fields': ('color',),
            'description': _("Размеры задайте в таблице размеров ниже.")
        }),
        (_('Цены и наличие'), {'fields': ('price', 'currency', 'old_price')}),
        (_('Медиа'), {
            'fields': ('main_image', 'main_image_file', 'main_media_preview'),
            'description': _("Можно использовать внешний URL или загруженный файл."),
        }),
        (_('Идентификаторы'), {'fields': ('sku', 'barcode', 'gtin', 'mpn')}),
        (_('Внешние данные'), {'fields': ('external_id', 'external_url', 'external_data')}),
        (_('Статус'), {'fields': ('is_active', 'sort_order')}),
    )
    inlines = [IslamicClothingVariantSizeInline, IslamicClothingVariantImageInline]

    def _get_effective_price_currency(self, obj):
        if obj.price is not None:
            return obj.price, (obj.currency or obj.product.currency or 'RUB').upper()
        return obj.product.price, (obj.product.currency or 'RUB').upper()

    def effective_base(self, obj):
        price, currency = self._get_effective_price_currency(obj)
        if price is None:
            return '-'
        return f"{price} {currency}"
    effective_base.short_description = _('База')

    def main_media_preview(self, obj):
        if not obj:
            return _("Нет медиа")
        return render_media_preview(resolve_media_url(obj, 'main_image_file', 'main_image'))


@admin.register(IslamicClothingProduct)
class IslamicClothingProductAdmin(AdminMediaHelpTextMixin, ShadowProductCleanupAdminMixin, RunAIActionMixin, admin.ModelAdmin):
    ai_logs_prefetch_path = "base_product__ai_logs"
    category_field_name = "islamic-clothing"

    def category_path(self, obj):
        return _product_category_path(obj)
    category_path.short_description = _("Категория")

    list_display = ('name', 'slug', 'get_ai_status', 'category_path', 'brand', 'price', 'currency', 'is_active', 'created_at')
    list_filter = (AIStatusFilter, 'is_active', 'is_new', 'is_featured', 'category', 'brand', 'currency', 'created_at')
    list_select_related = ('category', 'category__parent', 'category__parent__parent', 'category__parent__parent__parent')
    search_fields = ('name', 'slug', 'description')
    ordering = ('-created_at',)
    prepopulated_fields = {'slug': ('name',)}
    exclude = ('size', 'color')
    readonly_fields = ('variant_prices_overview', 'main_media_preview')
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description')}),
        (_('Categorization'), {
            'fields': ('category', 'brand'),
            'description': PRODUCT_CATEGORY_HELP,
        }),
        (_('Pricing'), {'fields': ('price', 'currency', 'old_price', 'variant_prices_overview')}),
        (_('Availability'), {'fields': ('is_available', 'stock_quantity')}),
        (_('SEO (fallback / EN)'), {
            'fields': (
                'meta_title', 'meta_description', 'meta_keywords',
                'og_title', 'og_description', 'og_image_url'
            ),
            'description': _("Общие fallback/англоязычные SEO-поля. Локализованные SEO редактируются в переводах товара.")
        }),
        (_('Media'), {
            'fields': ('main_image', 'main_image_file', 'video_url', 'main_video_file', 'main_media_preview'),
            'description': _("Основное медиа товара. Можно использовать внешний URL или загруженные файлы."),
        }),
        (_('Settings'), {'fields': ('is_active', 'is_new', 'is_featured')}),
        (_('External'), {'fields': ('external_id', 'external_url', 'external_data')}),
    )
    inlines = [IslamicClothingProductTranslationInline, IslamicClothingProductSizeInline, IslamicClothingVariantInline, IslamicClothingProductImageInline, ProductAttributeValueInline]

    def variant_prices_overview(self, obj):
        if not obj or not obj.pk:
            return "-"
        variants = obj.variants.filter(is_active=True).order_by('sort_order', 'id')
        if not variants.exists():
            return "-"
        base_price = obj.price
        base_currency = obj.currency
        rows = []
        for v in variants:
            effective_price = v.price if v.price is not None else base_price
            effective_currency = (v.currency or base_currency) if v.price is not None else base_currency
            price_str = '-' if effective_price is None else f"{effective_price} {effective_currency}"
            rows.append((v.color or '-', v.slug, price_str, 'variant' if v.price is not None else 'base'))
        
        header = format_html(
            '<table style="width:100%; border-collapse:collapse;">'
            '<thead>'
            '<tr>'
            '<th style="text-align:left; padding:6px; border-bottom:1px solid #ddd;">Цвет</th>'
            '<th style="text-align:left; padding:6px; border-bottom:1px solid #ddd;">Slug</th>'
            '<th style="text-align:left; padding:6px; border-bottom:1px solid #ddd;">Цена</th>'
            '<th style="text-align:left; padding:6px; border-bottom:1px solid #ddd;">Источник</th>'
            '</tr>'
            '</thead><tbody>'
        )
        body = format_html(
            '{}',
            format_html_join(
                '',
                '<tr>'
                '<td style="padding:6px; border-bottom:1px solid #f0f0f0;">{}</td>'
                '<td style="padding:6px; border-bottom:1px solid #f0f0f0;"><code>{}</code></td>'
                '<td style="padding:6px; border-bottom:1px solid #f0f0f0;">{}</td>'
                '<td style="padding:6px; border-bottom:1px solid #f0f0f0;">{}</td>'
                '</tr>',
                ((c, s, p, src) for (c, s, p, src) in rows),
            )
        )
        footer = format_html('</tbody></table>')
        return format_html('{}{}{}', header, body, footer)
    variant_prices_overview.short_description = _('Цены вариантов')

    def main_media_preview(self, obj):
        if not obj:
            return _("Нет медиа")
        image_url = resolve_media_url(obj, 'main_image_file', 'main_image')
        video_url = resolve_media_url(obj, 'main_video_file', 'video_url')
        return render_media_preview(image_url or video_url)
