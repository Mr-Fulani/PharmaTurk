"""Админки для доменов Волны 2 (простые домены без вариантов)."""

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.db import models as django_models

from .models import (
    Category,
    MedicineProduct, MedicineProductTranslation, MedicineProductImage, MedicineAnalog,
    SupplementProduct, SupplementProductTranslation, SupplementProductImage,
    MedicalEquipmentProduct, MedicalEquipmentProductTranslation, MedicalEquipmentProductImage,
    TablewareProduct, TablewareProductTranslation, TablewareProductImage,
    AccessoryProduct, AccessoryProductTranslation, AccessoryProductImage,
    IncenseProduct, IncenseProductTranslation, IncenseProductImage,
)


# ─────────────────────────────────────────────────────────────
#  Общие Inline-классы (генератор)
# ─────────────────────────────────────────────────────────────

def _make_translation_inline(model_class, extra_fields=None):
    """Фабрика для StackedInline переводов (чтобы широкие текстовые поля нормально помещались)."""
    inline_fields = ('locale', 'name', 'description')
    if extra_fields:
        inline_fields += tuple(extra_fields)

    class Inline(admin.StackedInline):
        model = model_class
        extra = 2
        fields = inline_fields
        verbose_name = _('Перевод')
        verbose_name_plural = _('Переводы')

    Inline.__name__ = f'{model_class.__name__}Inline'
    return Inline


def _make_image_inline(model_class):
    """Фабрика для TabularInline изображений."""
    class Inline(admin.TabularInline):
        model = model_class
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
                        media_url,
                    )
            return "-"
        image_preview.short_description = _("Превью")

    Inline.__name__ = f'{model_class.__name__}Inline'
    return Inline


# ─────────────────────────────────────────────────────────────
#  Базовый Admin для простых доменов
# ─────────────────────────────────────────────────────────────

class _SimpleDomainAdmin(admin.ModelAdmin):
    """Базовый ModelAdmin для простых доменных моделей без вариантов."""
    actions = ["run_ai", "run_ai_auto_apply", "run_find_merge_duplicates"]

    list_display = [
        'name', 'category', 'gender', 'price', 'old_price',
        'is_available', 'is_new', 'is_featured', 'created_at',
    ]
    list_filter = ['category', 'gender', 'is_available', 'is_new', 'is_featured', 'created_at']
    list_editable = ['price', 'old_price', 'is_available']
    search_fields = ['name', 'description', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['slug_preview', 'created_at', 'updated_at']

    # Базовые fieldsets — домены расширяют через _domain_fieldset
    _base_fieldsets = (
        (_('Основное'), {
            'fields': ('name', 'slug', 'slug_preview', 'description'),
        }),
        (_('Категоризация'), {
            'fields': ('category', 'brand', 'gender'),
        }),
    )
    _price_fieldsets = (
        (_('Цены и наличие'), {
            'fields': ('price', 'currency', 'old_price', 'is_available', 'stock_quantity'),
        }),
    )
    _status_fieldsets = (
        (_('Статус'), {
            'fields': ('is_featured', 'is_new'),
        }),
        (_('Медиа'), {
            'fields': ('main_image', 'main_image_file'),
        }),
        (_('Внешние данные'), {
            'fields': ('external_id', 'external_url', 'external_data'),
            'classes': ('collapse',),
        }),
    )

    _seo_fieldsets = (
        (_("SEO (EN)"), {
            "fields": (
                "meta_title", "meta_description", "meta_keywords",
                "og_title", "og_description", "og_image_url"
            ),
            "description": _("Англоязычные SEO-поля и OpenGraph.")
        }),
    )

    # Подклассы переопределяют этот атрибут
    _domain_fieldset = None
    # Slug типа категории для фильтрации FK
    _category_type_slug = None

    @property
    def fieldsets(self):
        parts = list(self._base_fieldsets)
        if self._domain_fieldset:
            parts.append(self._domain_fieldset)
        parts.extend(self._price_fieldsets)
        parts.extend(self._status_fieldsets)
        parts.extend(self._seo_fieldsets)
        return tuple(parts)

    def slug_preview(self, obj):
        if obj:
            return format_html('<code>{}</code>', obj.slug)
        return "-"
    slug_preview.short_description = _("Slug (предпросмотр)")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'category' and self._category_type_slug:
            type_slug = str(self._category_type_slug).replace('_', '-')
            kwargs['queryset'] = Category.objects.filter(
                category_type__slug=type_slug,
                is_active=True,
            ).order_by('sort_order', 'name')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def run_ai(self, request, queryset):
        from apps.ai.tasks import process_product_ai_task
        for obj in queryset:
            process_product_ai_task.delay(
                product_id=getattr(obj, "base_product_id", None) or obj.id,
                processing_type="full",
                auto_apply=False,
            )
        self.message_user(
            request,
            _("Запущена полная AI обработка для %(count)s товаров.")
            % {"count": queryset.count()},
            level=messages.SUCCESS,
        )
    run_ai.short_description = _("Полная AI обработка (без авто-применения)")

    def run_ai_auto_apply(self, request, queryset):
        from apps.ai.tasks import process_product_ai_task
        for obj in queryset:
            process_product_ai_task.delay(
                product_id=getattr(obj, "base_product_id", None) or obj.id,
                processing_type="full",
                auto_apply=True,
            )
        self.message_user(
            request,
            _("Запущена полная AI обработка с авто-применением для %(count)s товаров.")
            % {"count": queryset.count()},
            level=messages.SUCCESS,
        )
    run_ai_auto_apply.short_description = _("Полная AI обработка + авто-применение")

    def run_find_merge_duplicates(self, request, queryset):
        from apps.scrapers.tasks import find_and_merge_duplicates
        find_and_merge_duplicates.delay()
        self.message_user(
            request,
            _("Запущен поиск и объединение дубликатов."),
            level=messages.SUCCESS,
        )
    run_find_merge_duplicates.short_description = _("Поиск и объединение дубликатов")


# ─────────────────────────────────────────────────────────────
#  МЕДИКАМЕНТЫ
# ─────────────────────────────────────────────────────────────

@admin.register(MedicineProduct)
class MedicineProductAdmin(_SimpleDomainAdmin):
    _category_type_slug = "medicines"
    _domain_fieldset = (_('Специфика медикамента'), {
        'fields': (
            'dosage_form', 'active_ingredient', 'prescription_required', 'prescription_type',
            'volume', 'origin_country',
            'barcode', 'atc_code', 'administration_route',
            'shelf_life', 'storage_conditions',
            'sgk_status', 'special_notes',
        ),
    })
    list_display = [
        'name', 'category', 'dosage_form', 'active_ingredient', 'barcode', 'atc_code',
        'prescription_required', 'price', 'old_price',
        'is_available', 'is_new', 'created_at',
    ]
    list_filter = [
        'category', 'is_available', 'prescription_required',
        'dosage_form', 'is_new', 'created_at',
    ]
    inlines = [
        _make_translation_inline(MedicineProductTranslation, extra_fields=(
            'usage_instructions', 'side_effects', 'contraindications',
            'storage_conditions', 'indications',
            'dosage_form', 'active_ingredient', 'volume', 'origin_country',
        )),
        _make_image_inline(MedicineProductImage),
        type('MedicineAnalogInline', (admin.TabularInline,), {
            'model': MedicineAnalog,
            'extra': 0,
            'fields': ('name', 'barcode', 'atc_code', 'source', 'external_id'),
            'verbose_name': _('Аналог'),
            'verbose_name_plural': _('Аналоги (из Eşdeğeri)'),
        }),
    ]


# ─────────────────────────────────────────────────────────────
#  БАДы
# ─────────────────────────────────────────────────────────────

@admin.register(SupplementProduct)
class SupplementProductAdmin(_SimpleDomainAdmin):
    _category_type_slug = "supplements"
    _domain_fieldset = (_('Специфика БАД'), {
        'fields': ('dosage_form', 'active_ingredient'),
    })
    list_display = [
        'name', 'category', 'dosage_form', 'active_ingredient',
        'price', 'old_price', 'is_available', 'is_new', 'created_at',
    ]
    list_filter = [
        'category', 'is_available', 'dosage_form', 'is_new', 'created_at',
    ]
    inlines = [
        _make_translation_inline(SupplementProductTranslation, extra_fields=(
            'dosage_form', 'active_ingredient', 'serving_size'
        )),
        _make_image_inline(SupplementProductImage),
    ]


# ─────────────────────────────────────────────────────────────
#  МЕДТЕХНИКА
# ─────────────────────────────────────────────────────────────

@admin.register(MedicalEquipmentProduct)
class MedicalEquipmentProductAdmin(_SimpleDomainAdmin):
    _category_type_slug = "medical-equipment"
    _domain_fieldset = (_('Специфика медтехники'), {
        'fields': ('equipment_type',),
    })
    list_display = [
        'name', 'category', 'equipment_type',
        'price', 'old_price', 'is_available', 'is_new', 'created_at',
    ]
    list_filter = [
        'category', 'is_available', 'is_new', 'created_at',
    ]
    inlines = [
        _make_translation_inline(MedicalEquipmentProductTranslation),
        _make_image_inline(MedicalEquipmentProductImage),
    ]


# ─────────────────────────────────────────────────────────────
#  ПОСУДА
# ─────────────────────────────────────────────────────────────

@admin.register(TablewareProduct)
class TablewareProductAdmin(_SimpleDomainAdmin):
    _category_type_slug = "tableware"
    _domain_fieldset = (_('Специфика посуды'), {
        'fields': ('material',),
    })
    list_display = [
        'name', 'category', 'material',
        'price', 'old_price', 'is_available', 'is_new', 'created_at',
    ]
    list_filter = [
        'category', 'is_available', 'material', 'is_new', 'created_at',
    ]
    inlines = [
        _make_translation_inline(TablewareProductTranslation),
        _make_image_inline(TablewareProductImage),
    ]


# ─────────────────────────────────────────────────────────────
#  АКСЕССУАРЫ
# ─────────────────────────────────────────────────────────────

@admin.register(AccessoryProduct)
class AccessoryProductAdmin(_SimpleDomainAdmin):
    _category_type_slug = "accessories"
    _domain_fieldset = (_('Специфика аксессуара'), {
        'fields': ('accessory_type', 'material'),
    })
    list_display = [
        'name', 'category', 'accessory_type', 'material',
        'price', 'old_price', 'is_available', 'is_new', 'created_at',
    ]
    list_filter = [
        'category', 'is_available', 'accessory_type', 'is_new', 'created_at',
    ]
    inlines = [
        _make_translation_inline(AccessoryProductTranslation),
        _make_image_inline(AccessoryProductImage),
    ]


# ─────────────────────────────────────────────────────────────
#  БЛАГОВОНИЯ
# ─────────────────────────────────────────────────────────────

@admin.register(IncenseProduct)
class IncenseProductAdmin(_SimpleDomainAdmin):
    _category_type_slug = "incense"
    _domain_fieldset = (_('Специфика благовония'), {
        'fields': ('scent_type',),
    })
    list_display = [
        'name', 'category', 'scent_type',
        'price', 'old_price', 'is_available', 'is_new', 'created_at',
    ]
    list_filter = [
        'category', 'is_available', 'scent_type', 'is_new', 'created_at',
    ]
    inlines = [
        _make_translation_inline(IncenseProductTranslation),
        _make_image_inline(IncenseProductImage),
    ]
