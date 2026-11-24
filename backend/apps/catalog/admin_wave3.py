from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (
    SportsProduct, SportsProductTranslation, SportsProductImage, SportsVariant,
    AutoPartProduct, AutoPartProductTranslation, AutoPartProductImage, AutoPartVariant,
    AutoPartNumber, AutoPartFitment,
)
from .admin_wave2 import _SimpleDomainAdmin, _make_translation_inline, _make_image_inline
from .admin_base import AIStatusFilter


@admin.register(SportsProduct)
class SportsProductAdmin(_SimpleDomainAdmin):
    _category_type_slug = "sports"
    _domain_fieldset = (_('Характеристики спорттовара'), {
        'fields': ('sport_type', 'equipment_type', 'material'),
    })
    list_display = [
        'name', 'get_ai_status', 'category', 'sport_type', 'equipment_type',
        'price', 'old_price', 'is_available', 'created_at',
    ]
    list_filter = [
        AIStatusFilter, 'category', 'is_available', 'sport_type', 'equipment_type', 'created_at'
    ]
    
    class SportsVariantInline(admin.TabularInline):
        model = SportsVariant
        extra = 0
        fields = ('color', 'size', 'sku', 'price', 'stock_quantity', 'is_available')
        verbose_name = _("Вариант")
        verbose_name_plural = _("Варианты")

    inlines = [
        _make_translation_inline(SportsProductTranslation),
        _make_image_inline(SportsProductImage),
        SportsVariantInline,
    ]


@admin.register(AutoPartProduct)
class AutoPartProductAdmin(_SimpleDomainAdmin):
    _category_type_slug = "auto_parts"
    _domain_fieldset = (_('Характеристики запчасти'), {
        'fields': (
            'part_number', 'part_number_normalized', 'fitment_summary',
            'car_brand', 'car_model', 'compatibility_years',
        ),
        'description': _(
            'OEM-номера и аналоги — в таблице ниже на этой странице. Полный список автомобилей, '
            'к которым подходит деталь, открывается по ссылке «Применимость».'
        ),
    })
    list_display = [
        'name', 'get_ai_status', 'category', 'part_number', 'car_brand',
        'price', 'old_price', 'is_available', 'created_at',
    ]
    list_filter = [
        AIStatusFilter, 'category', 'is_available', 'car_brand', 'created_at'
    ]
    search_fields = _SimpleDomainAdmin.search_fields + [
        'part_number', 'part_number_normalized', 'numbers__number_normalized', 'car_brand', 'car_model',
    ]
    readonly_fields = _SimpleDomainAdmin.readonly_fields + ['part_number_normalized', 'fitment_summary']

    @admin.display(description=_("Применимость"))
    def fitment_summary(self, obj):
        if not obj or not obj.pk:
            return "—"
        count = obj.fitments.count()
        if not count:
            return _("нет строк")
        makes = list(obj.fitments.order_by().values_list("make", flat=True).distinct()[:8])
        url = f"{reverse('admin:catalog_autopartfitment_changelist')}?product__id__exact={obj.pk}"
        return format_html(
            '<a href="{}">{} — открыть список</a><br>{}',
            url, _("Автомобилей: %(count)s") % {"count": count}, ", ".join(makes),
        )

    class AutoPartVariantInline(admin.TabularInline):
        model = AutoPartVariant
        extra = 0
        fields = ('condition', 'manufacturer', 'sku', 'price', 'stock_quantity', 'is_available')
        verbose_name = _("Вариант")
        verbose_name_plural = _("Варианты")

    class AutoPartNumberInline(admin.TabularInline):
        model = AutoPartNumber
        extra = 0
        fields = ('number', 'kind', 'maker', 'source')
        verbose_name = _("Номер (OEM, аналог)")
        verbose_name_plural = _("Номера: OEM и аналоги")

    inlines = [
        _make_translation_inline(AutoPartProductTranslation),
        _make_image_inline(AutoPartProductImage),
        AutoPartVariantInline,
        AutoPartNumberInline,
    ]


@admin.register(AutoPartNumber)
class AutoPartNumberAdmin(admin.ModelAdmin):
    """Поиск детали по OEM-номеру или номеру-аналогу (пробелы и дефисы не важны)."""

    list_display = ['number', 'kind', 'maker', 'product', 'source']
    list_filter = ['kind', 'source']
    search_fields = ['number', 'number_normalized', 'maker', 'product__part_number_normalized']
    autocomplete_fields = ['product']
    list_select_related = ['product']

    def get_search_results(self, request, queryset, search_term):
        from .utils.part_numbers import normalize_part_number

        queryset, distinct = super().get_search_results(request, queryset, search_term)
        normalized = normalize_part_number(search_term)
        if len(normalized) >= 4:
            queryset |= self.model.objects.filter(number_normalized=normalized)
        return queryset, distinct


@admin.register(AutoPartFitment)
class AutoPartFitmentAdmin(admin.ModelAdmin):
    """Применимость: к каким автомобилям подходит деталь."""

    list_display = [
        'product', 'make', 'model', 'generation', 'year_from', 'year_to',
        'engine', 'power_kw', 'power_hp', 'note',
    ]
    list_filter = ['source']
    search_fields = ['make', 'model', 'generation', 'engine', 'product__part_number_normalized', 'product__name']
    autocomplete_fields = ['product']
    list_select_related = ['product']
    list_per_page = 100
    show_full_result_count = False
