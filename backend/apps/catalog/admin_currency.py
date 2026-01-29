"""Админ-панель для управления курсами валют и маржой."""

from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from django.urls import reverse
from django.utils.safestring import mark_safe
from decimal import Decimal
from .currency_models import CurrencyRate, MarginSettings, ProductPrice, CurrencyUpdateLog


@admin.register(CurrencyRate)
class CurrencyRateAdmin(admin.ModelAdmin):
    """Админ-панель для курсов валют."""
    
    list_display = [
        'from_currency', 'to_currency', 'rate', 'source_display', 
        'is_active', 'updated_at', 'rate_badge'
    ]
    list_filter = ['from_currency', 'to_currency', 'source', 'is_active']
    search_fields = ['from_currency', 'to_currency']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('from_currency', 'to_currency', 'rate', 'is_active')
        }),
        ('Источник данных', {
            'fields': ('source',)
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def source_display(self, obj):
        """Отображение источника с цветовой индикацией."""
        colors = {
            'centralbank_rf': 'blue',
            'nationalbank_kz': 'green', 
            'centralbank_tr': 'red',
            'openexchangerates': 'purple',
            'manual': 'orange'
        }
        color = colors.get(obj.source, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_source_display()
        )
    source_display.short_description = 'Источник'
    
    def rate_badge(self, obj):
        """Цветовая индикация курса."""
        if not obj.is_active:
            return format_html('<span style="color: gray;">Неактивен</span>')
        
        # Определяем цвет в зависимости от величины курса
        if obj.rate >= 10:
            color = 'red'
        elif obj.rate >= 1:
            color = 'orange'
        else:
            color = 'green'
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, str(obj.rate.quantize(Decimal('0.0001')))
        )
    rate_badge.short_description = 'Курс'
    
    actions = ['activate_rates', 'deactivate_rates', 'refresh_selected_rates']
    
    def activate_rates(self, request, queryset):
        """Активировать выбранные курсы."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано {updated} курсов.')
    activate_rates.short_description = 'Активировать выбранные курсы'
    
    def deactivate_rates(self, request, queryset):
        """Деактивировать выбранные курсы."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано {updated} курсов.')
    deactivate_rates.short_description = 'Деактивировать выбранные курсы'
    
    def refresh_selected_rates(self, request, queryset):
        """Обновить выбранные курсы."""
        try:
            from django.core.management import call_command
            call_command('update_currency_rates')
            self.message_user(request, 'Курсы валют успешно обновлены из внешних источников')
        except Exception as e:
            self.message_user(request, f'Ошибка обновления курсов: {str(e)}')
    refresh_selected_rates.short_description = 'Обновить выбранные курсы'


@admin.register(MarginSettings)
class MarginSettingsAdmin(admin.ModelAdmin):
    """Админ-панель для настроек маржи."""
    
    list_display = [
        'currency_pair', 'margin_percentage', 'is_active', 
        'description', 'updated_at', 'margin_indicator'
    ]
    list_filter = ['is_active', 'currency_pair']
    search_fields = ['currency_pair', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['currency_pair']
    
    fieldsets = (
        ('Основные настройки', {
            'fields': ('currency_pair', 'margin_percentage', 'is_active')
        }),
        ('Описание', {
            'fields': ('description',)
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def margin_indicator(self, obj):
        """Индикатор маржи с цветовой кодировкой."""
        if not obj.is_active:
            return format_html('<span style="color: gray;">Неактивна</span>')
        
        margin = float(obj.margin_percentage)
        if margin >= 30:
            color = 'red'
            text = 'Высокая'
        elif margin >= 15:
            color = 'orange'
            text = 'Средняя'
        else:
            color = 'green'
            text = 'Низкая'
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}%</span> '
            '<span style="color: {}; font-size: 0.9em;">({})</span>',
            color, obj.margin_percentage, color, text
        )
    margin_indicator.short_description = 'Маржа'
    
    actions = ['activate_margins', 'deactivate_margins', 'reset_to_default']
    
    def activate_margins(self, request, queryset):
        """Активировать выбранные маржи."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано {updated} настроек маржи.')
    activate_margins.short_description = 'Активировать выбранные маржи'
    
    def deactivate_margins(self, request, queryset):
        """Деактивировать выбранные маржи."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано {updated} настроек маржи.')
    deactivate_margins.short_description = 'Деактивировать выбранные маржи'
    
    def reset_to_default(self, request, queryset):
        """Сбросить маржу к значению по умолчанию (15%)."""
        from decimal import Decimal
        updated = queryset.update(margin_percentage=Decimal('15.00'))
        self.message_user(request, f'Сброшено {updated} настроек маржи к 15%.')
    reset_to_default.short_description = 'Сбросить к 15 процентов'


@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    """Админ-панель для цен товаров."""
    
    list_display = [
        'product_link', 'base_currency', 'base_price', 
        'rub_price_with_margin', 'usd_price_with_margin', 
        'kzt_price_with_margin', 'try_price_with_margin', 'updated_at'
    ]
    list_filter = ['base_currency', 'updated_at']
    search_fields = ['product__name', 'product__slug']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('product', 'base_currency', 'base_price')
        }),
        ('Цены в рублях', {
            'fields': ('rub_price', 'rub_price_with_margin'),
            'classes': ('collapse',)
        }),
        ('Цены в долларах', {
            'fields': ('usd_price', 'usd_price_with_margin'),
            'classes': ('collapse',)
        }),
        ('Цены в тенге', {
            'fields': ('kzt_price', 'kzt_price_with_margin'),
            'classes': ('collapse',)
        }),
        ('Цены в евро', {
            'fields': ('eur_price', 'eur_price_with_margin'),
            'classes': ('collapse',)
        }),
        ('Цены в турецких лирах', {
            'fields': ('try_price', 'try_price_with_margin'),
            'classes': ('collapse',)
        }),
        ('Доставка', {
            'fields': ('air_shipping_cost', 'sea_shipping_cost', 'ground_shipping_cost'),
            'classes': ('collapse',)
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def product_link(self, obj):
        """Ссылка на товар."""
        if obj.product:
            try:
                url = reverse('admin:apps_catalog_product_change', args=[obj.product.id])
                return format_html(
                    '<a href="{}">{}</a>',
                    url, obj.product.name[:50] + '...' if len(obj.product.name) > 50 else obj.product.name
                )
            except:
                return str(obj.product.name)
        return '-'
    product_link.short_description = 'Товар'
    
    def get_queryset(self, request):
        """Оптимизация запросов."""
        return super().get_queryset(request).select_related('product')
    
    actions = ['recalculate_prices', 'delete_all_prices']
    
    def recalculate_prices(self, request, queryset):
        """Пересчитать выбранные цены."""
        from apps.catalog.utils.currency_converter import currency_converter
        
        success_count = 0
        error_count = 0
        
        for price_info in queryset:
            try:
                # Используем base_price и base_currency из ProductPrice
                if price_info.base_price and price_info.base_currency:
                    # Конвертируем в целевые валюты
                    results = currency_converter.convert_to_multiple_currencies(
                        price_info.base_price, price_info.base_currency, ['RUB', 'USD', 'KZT', 'EUR', 'TRY'], apply_margin=True
                    )
                    
                    if 'RUB' in results and results['RUB']:
                        price_info.rub_price = results['RUB']['converted_price']
                        price_info.rub_price_with_margin = results['RUB']['price_with_margin']
                    
                    if 'USD' in results and results['USD']:
                        price_info.usd_price = results['USD']['converted_price']
                        price_info.usd_price_with_margin = results['USD']['price_with_margin']
                    
                    if 'KZT' in results and results['KZT']:
                        price_info.kzt_price = results['KZT']['converted_price']
                        price_info.kzt_price_with_margin = results['KZT']['price_with_margin']
                    
                    if 'EUR' in results and results['EUR']:
                        price_info.eur_price = results['EUR']['converted_price']
                        price_info.eur_price_with_margin = results['EUR']['price_with_margin']
                    
                    if 'TRY' in results and results['TRY']:
                        price_info.try_price = results['TRY']['converted_price']
                        price_info.try_price_with_margin = results['TRY']['price_with_margin']
                    
                    price_info.save()
                    success_count += 1
                else:
                    error_count += 1
            except Exception:
                error_count += 1
        
        self.message_user(
            request, 
            f'Пересчет завершен: успешно {success_count}, ошибок {error_count}'
        )
    recalculate_prices.short_description = 'Пересчитать цены'
    
    def delete_all_prices(self, request, queryset):
        """Удалить все выбранные цены."""
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f'Удалено {count} записей цен')
    delete_all_prices.short_description = 'Удалить цены'


@admin.register(CurrencyUpdateLog)
class CurrencyUpdateLogAdmin(admin.ModelAdmin):
    """Админ-панель для логов обновления курсов."""
    
    list_display = [
        'source', 'success', 'rates_updated', 'execution_time',
        'created_at', 'status_badge'
    ]
    list_filter = ['source', 'success', 'created_at']
    search_fields = ['source', 'error_message']
    readonly_fields = [
        'source', 'success', 'rates_updated', 'error_message',
        'execution_time_seconds', 'created_at'
    ]
    ordering = ['-created_at']
    
    def has_add_permission(self, request):
        """Запретить добавление записей вручную."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Запретить редактирование записей."""
        return False
    
    def status_badge(self, obj):
        """Индикатор статуса."""
        if obj.success:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Успешно</span>'
            )
        else:
            return format_html(
                '<span style="color: red; font-weight: bold;">✗ Ошибка</span>'
            )
    status_badge.short_description = 'Статус'
    
    def execution_time(self, obj):
        """Отображение времени выполнения."""
        if obj.execution_time_seconds:
            if obj.execution_time_seconds < 1:
                return f"{obj.execution_time_seconds*1000:.0f}мс"
            else:
                return f"{obj.execution_time_seconds:.2f}с"
        return '-'
    execution_time.short_description = 'Время выполнения'
    
    fieldsets = (
        ('Информация об обновлении', {
            'fields': ('source', 'success', 'rates_updated')
        }),
        ('Метрики', {
            'fields': ('execution_time_seconds',)
        }),
        ('Ошибки', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('Временные метки', {
            'fields': ('created_at',)
        }),
    )


# Настройка заголовка админ-панели
admin.site.site_header = 'Управление курсами валют'
admin.site.site_title = 'Валютная система'
admin.site.index_title = 'Панель управления курсами валют и маржой'
