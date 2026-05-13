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
from .admin_base import AIStatusFilter, RunAIActionMixin, MediaEnrichmentStatusFilter, MediaEnrichmentMixin, ShadowProductCleanupAdminMixin


# ─────────────────────────────────────────────────────────────
#  Общие Inline-классы (генератор)
# ─────────────────────────────────────────────────────────────

def _make_translation_inline(model_class, extra_fields=None):
    """Фабрика для StackedInline переводов (чтобы широкие текстовые поля нормально помещались)."""
    base_fieldsets = [
        (None, {'fields': ('locale', 'name', 'description')}),
        (_('Локализованное SEO'), {
            'fields': (
                'meta_title', 'meta_description', 'meta_keywords',
                'og_title', 'og_description',
            ),
            'description': _('SEO-поля для конкретного языка перевода (например ru или en).'),
        }),
    ]
    if extra_fields:
        base_fieldsets.append(
            (_('Дополнительные поля'), {
                'fields': tuple(extra_fields),
                'classes': ('collapse',),
            })
        )

    class Inline(admin.StackedInline):
        model = model_class
        extra = 2
        fieldsets = tuple(base_fieldsets)
        verbose_name = _('Перевод')
        verbose_name_plural = _('Переводы')

    Inline.__name__ = f'{model_class.__name__}Inline'
    return Inline


def _make_image_inline(model_class):
    """Фабрика для TabularInline изображений."""
    class Inline(admin.TabularInline):
        model = model_class
        extra = 1
        fields = ('image_file', 'image_url', 'alt_text', 'is_main', 'sort_order', 'image_preview')
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

class _SimpleDomainAdmin(ShadowProductCleanupAdminMixin, RunAIActionMixin, admin.ModelAdmin):
    """Базовый ModelAdmin для простых доменных моделей без вариантов."""
    ai_logs_prefetch_path = "base_product__ai_logs"
    actions = ["run_ai", "run_ai_auto_apply", "run_find_merge_duplicates"]

    list_display = [
        'name', 'get_ai_status', 'category', 'gender', 'price', 'old_price',
        'is_available', 'is_new', 'is_featured', 'created_at',
    ]
    list_filter = [AIStatusFilter, 'category', 'gender', 'is_available', 'is_new', 'is_featured', 'created_at']
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
        (_("SEO (fallback / EN)"), {
            "fields": (
                "meta_title", "meta_description", "meta_keywords",
                "og_title", "og_description", "og_image_url"
            ),
            "description": _("Общие fallback/англоязычные SEO-поля. Локализованные SEO редактируются в переводах товара.")
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

    # run_ai, run_ai_auto_apply, run_find_merge_duplicates inherited from RunAIActionMixin


# ─────────────────────────────────────────────────────────────
#  МЕДИКАМЕНТЫ
# ─────────────────────────────────────────────────────────────

def _medicine_stub_display_flag(obj):
    external_data = obj.external_data if isinstance(obj.external_data, dict) else {}
    attrs = external_data.get('attributes') if isinstance(external_data.get('attributes'), dict) else {}
    return (
        external_data.get('is_stub') is True
        or attrs.get('is_stub') is True
        or (
            str(external_data.get('source') or '').strip() == 'ilacfiyati'
            and not str(obj.description or '').strip()
            and obj.price is None
        )
    )


class MedicineStubStatusFilter(admin.SimpleListFilter):
    title = _('Техпризнак')
    parameter_name = 'medicine_stub_status'

    def lookups(self, request, model_admin):
        return (
            ('parsed', _('Спарсен')),
            ('stub', _('Заглушка')),
        )

    def _stub_q(self):
        explicit_stub_q = (
            django_models.Q(external_data__has_key='is_stub') &
            django_models.Q(external_data__is_stub=True)
        )
        attrs_stub_q = (
            django_models.Q(external_data__attributes__has_key='is_stub') &
            django_models.Q(external_data__attributes__is_stub=True)
        )
        legacy_stub_q = (
            django_models.Q(external_data__source='ilacfiyati') &
            django_models.Q(description='') &
            django_models.Q(price__isnull=True)
        )
        return explicit_stub_q | attrs_stub_q | legacy_stub_q

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'stub':
            return queryset.filter(self._stub_q())
        if value == 'parsed':
            return queryset.exclude(self._stub_q())
        return queryset


@admin.register(MedicineProduct)
class MedicineProductAdmin(_SimpleDomainAdmin, MediaEnrichmentMixin):
    _category_type_slug = "medicines"
    _domain_fieldset = (_('Специфика медикамента'), {
        'fields': (
            'manufacturer',
            'dosage_form', 'active_ingredient', 'prescription_required', 'prescription_type',
            'volume', 'origin_country',
            'barcode', 'atc_code', 'nfc_code', 'administration_route',
            'shelf_life', 'storage_conditions',
            'sgk_status', 'sgk_equivalent_code', 'sgk_active_ingredient_code', 'sgk_public_no', 'special_notes',
        ),
    })
    list_display = [
        'name', 'stub_status', 'get_ai_status', 'get_media_enrichment_status', 'category', 'dosage_form', 'active_ingredient', 'barcode', 'atc_code', 'nfc_code', 'sgk_public_no',
        'prescription_required', 'price', 'old_price',
        'is_available', 'is_new', 'created_at',
    ]
    list_filter = [
        MedicineStubStatusFilter, AIStatusFilter, MediaEnrichmentStatusFilter, 'category', 'is_available', 'prescription_required',
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
            'fk_name': 'product',
            'extra': 0,
            'fields': (
                'name', 'analog_product', 'barcode', 'atc_code',
                'sgk_equivalent_code', 'source', 'source_tab', 'external_id',
            ),
            'verbose_name': _('Аналог'),
            'verbose_name_plural': _('Аналоги (из Eşdeğeri)'),
        }),
    ]

    actions = ["run_ai", "run_ai_auto_apply", "run_media_enrichment"]

    @admin.display(description=_('Тип'), ordering='external_data')
    def stub_status(self, obj):
        if _medicine_stub_display_flag(obj):
            return format_html(
                '<span style="display:inline-block;padding:2px 6px;border-radius:6px;'
                'background:#fff3cd;color:#8a5a00;font-weight:600;">Заглушка</span>'
            )
        return format_html(
            '<span style="display:inline-block;padding:2px 6px;border-radius:6px;'
            'background:#d1e7dd;color:#0f5132;font-weight:600;">Спарсен</span>'
        )


# ─────────────────────────────────────────────────────────────
#  БАДы
# ─────────────────────────────────────────────────────────────

@admin.register(SupplementProduct)
class SupplementProductAdmin(_SimpleDomainAdmin, MediaEnrichmentMixin):
    _category_type_slug = "supplements"
    _domain_fieldset = (_('Специфика БАД'), {
        'fields': ('dosage_form', 'active_ingredient'),
    })
    list_display = [
        'name', 'get_ai_status', 'get_media_enrichment_status', 'category', 'dosage_form', 'active_ingredient',
        'price', 'old_price', 'is_available', 'is_new', 'created_at',
    ]
    list_filter = [
        AIStatusFilter, MediaEnrichmentStatusFilter, 'category', 'is_available', 'dosage_form', 'is_new', 'created_at',
    ]
    actions = ["run_ai", "run_ai_auto_apply", "run_media_enrichment"]
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
        'name', 'get_ai_status', 'category', 'equipment_type',
        'price', 'old_price', 'is_available', 'is_new', 'created_at',
    ]
    list_filter = [
        AIStatusFilter, 'category', 'is_available', 'is_new', 'created_at',
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
        'name', 'get_ai_status', 'category', 'material',
        'price', 'old_price', 'is_available', 'is_new', 'created_at',
    ]
    list_filter = [
        AIStatusFilter, 'category', 'is_available', 'material', 'is_new', 'created_at',
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
    list_display = [
        'name', 'get_ai_status', 'category',
        'price', 'old_price', 'is_available', 'is_new', 'created_at',
    ]
    list_filter = [
        AIStatusFilter, 'category', 'is_available', 'is_new', 'created_at',
    ]
    inlines = [
        _make_translation_inline(AccessoryProductTranslation),
        _make_image_inline(AccessoryProductImage),
        # Here we import the inline from admin.py to avoid circular imports if needed, 
        # but since we're in admin_wave2.py which is imported in admin.py, we should be careful.
        # Actually, ProductAttributeValueInline is defined in admin.py.
    ]

    def get_inlines(self, request, obj):
        from .admin import ProductAttributeValueInline
        return self.inlines + [ProductAttributeValueInline]



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
        'name', 'get_ai_status', 'category', 'scent_type',
        'price', 'old_price', 'is_available', 'is_new', 'created_at',
    ]
    list_filter = [
        AIStatusFilter, 'category', 'is_available', 'scent_type', 'is_new', 'created_at',
    ]
    inlines = [
        _make_translation_inline(IncenseProductTranslation),
        _make_image_inline(IncenseProductImage),
    ]
