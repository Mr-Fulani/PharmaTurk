"""Админ-интерфейс для управления парсерами."""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Q
from django.contrib import messages
from django.http import HttpResponseRedirect

from .models import (
    ScraperConfig, ScrapingSession, CategoryMapping, 
    BrandMapping, ScrapedProductLog
)
from .tasks import run_scraper_task, update_scraper_status


@admin.register(ScraperConfig)
class ScraperConfigAdmin(admin.ModelAdmin):
    """Админ для конфигураций парсеров."""
    
    list_display = [
        'name', 'status_badge', 'base_url', 'priority', 
        'success_rate_display', 'last_run_display', 'actions_column'
    ]
    list_filter = ['status', 'is_enabled', 'sync_enabled', 'use_proxy', 'created_at']
    search_fields = ['name', 'base_url', 'description']
    ordering = ['priority', 'name']
    
    fieldsets = [
        ('Основная информация', {
            'fields': ['name', 'parser_class', 'base_url', 'description']
        }),
        ('Статус и настройки', {
            'fields': ['status', 'is_enabled', 'priority']
        }),
        ('Параметры парсинга', {
            'fields': [
                ('delay_min', 'delay_max'), 
                ('timeout', 'max_retries'),
                ('max_pages_per_run', 'max_products_per_run')
            ],
            'classes': ['collapse']
        }),
        ('Расписание', {
            'fields': ['sync_enabled', 'sync_interval_hours'],
            'classes': ['collapse']
        }),
        ('Дополнительные настройки', {
            'fields': ['use_proxy', 'user_agent', 'headers', 'cookies'],
            'classes': ['collapse']
        }),
        ('Статистика', {
            'fields': [
                'last_run_at', 'last_success_at', 'last_error_at',
                'total_runs', 'successful_runs', 'total_products_scraped'
            ],
            'classes': ['collapse'],
            'description': 'Статистика обновляется автоматически'
        })
    ]
    
    readonly_fields = [
        'last_run_at', 'last_success_at', 'last_error_at', 'last_error_message',
        'total_runs', 'successful_runs', 'total_products_scraped'
    ]
    
    actions = ['run_selected_scrapers', 'enable_scrapers', 'disable_scrapers']
    
    def status_badge(self, obj):
        """Отображает статус с цветным бейджем."""
        colors = {
            'active': 'green',
            'inactive': 'gray',
            'error': 'red',
            'maintenance': 'orange'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">●</span> {}',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Статус'
    
    def success_rate_display(self, obj):
        """Отображает процент успешных запусков."""
        try:
            rate = obj.success_rate
            if rate is None:
                return "0.0%"
            rate_float = float(rate)
            color = 'green' if rate_float >= 80 else 'orange' if rate_float >= 50 else 'red'
            return format_html(
                '<span style="color: {};">{:.1f}%</span>',
                color, rate_float
            )
        except (ValueError, TypeError, AttributeError):
            return "0.0%"
    success_rate_display.short_description = 'Успешность'
    
    def last_run_display(self, obj):
        """Отображает время последнего запуска."""
        if not obj.last_run_at:
            return 'Никогда'
        
        delta = timezone.now() - obj.last_run_at
        if delta.days > 0:
            return f'{delta.days} дн. назад'
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f'{hours} ч. назад'
        else:
            minutes = delta.seconds // 60
            return f'{minutes} мин. назад'
    last_run_display.short_description = 'Последний запуск'
    
    def actions_column(self, obj):
        """Колонка с действиями."""
        run_url = reverse('admin:scrapers_scraperconfig_run', args=[obj.pk])
        sessions_url = reverse('admin:scrapers_scrapingsession_changelist') + f'?scraper_config__id={obj.pk}'
        
        return format_html(
            '<a href="{}" class="button">Запустить</a> '
            '<a href="{}" class="button">Сессии</a>',
            run_url, sessions_url
        )
    actions_column.short_description = 'Действия'
    
    def get_urls(self):
        """Добавляем кастомные URL."""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:scraper_id>/run/',
                self.admin_site.admin_view(self.run_scraper_view),
                name='scrapers_scraperconfig_run'
            ),
        ]
        return custom_urls + urls
    
    def run_scraper_view(self, request, scraper_id):
        """Запускает парсер."""
        try:
            scraper_config = ScraperConfig.objects.get(id=scraper_id)
            
            # Запускаем задачу Celery
            task = run_scraper_task.delay(scraper_id)
            
            messages.success(
                request, 
                f'Парсер "{scraper_config.name}" запущен. ID задачи: {task.id}'
            )
            
        except ScraperConfig.DoesNotExist:
            messages.error(request, 'Парсер не найден')
        except Exception as e:
            messages.error(request, f'Ошибка запуска парсера: {e}')
        
        return HttpResponseRedirect(reverse('admin:scrapers_scraperconfig_changelist'))
    
    def run_selected_scrapers(self, request, queryset):
        """Действие: запустить выбранные парсеры."""
        started_count = 0
        
        for scraper_config in queryset.filter(is_enabled=True):
            try:
                run_scraper_task.delay(scraper_config.id)
                started_count += 1
            except Exception as e:
                messages.error(request, f'Ошибка запуска {scraper_config.name}: {e}')
        
        if started_count:
            messages.success(request, f'Запущено {started_count} парсеров')
    run_selected_scrapers.short_description = 'Запустить выбранные парсеры'
    
    def enable_scrapers(self, request, queryset):
        """Действие: включить парсеры."""
        updated = queryset.update(is_enabled=True, status='active')
        messages.success(request, f'Включено {updated} парсеров')
    enable_scrapers.short_description = 'Включить выбранные парсеры'
    
    def disable_scrapers(self, request, queryset):
        """Действие: отключить парсеры."""
        updated = queryset.update(is_enabled=False, status='inactive')
        messages.success(request, f'Отключено {updated} парсеров')
    disable_scrapers.short_description = 'Отключить выбранные парсеры'


@admin.register(ScrapingSession)
class ScrapingSessionAdmin(admin.ModelAdmin):
    """Админ для сессий парсинга."""
    
    list_display = [
        'scraper_config', 'status_badge', 'started_at', 'duration_display',
        'products_stats', 'pages_processed', 'errors_count'
    ]
    list_filter = [
        'status', 'scraper_config', 'started_at', 'finished_at'
    ]
    search_fields = ['scraper_config__name', 'start_url', 'error_message']
    ordering = ['-created_at']
    
    fieldsets = [
        ('Основная информация', {
            'fields': ['scraper_config', 'status', 'task_id']
        }),
        ('Параметры запуска', {
            'fields': ['start_url', 'max_pages', 'max_products']
        }),
        ('Результаты', {
            'fields': [
                ('products_found', 'products_created'),
                ('products_updated', 'products_skipped'),
                ('pages_processed', 'errors_count')
            ]
        }),
        ('Временные метки', {
            'fields': ['started_at', 'finished_at', 'created_at'],
            'classes': ['collapse']
        }),
        ('Логи и ошибки', {
            'fields': ['error_message', 'log_messages'],
            'classes': ['collapse']
        })
    ]
    
    readonly_fields = ['created_at', 'started_at', 'finished_at']
    
    def status_badge(self, obj):
        """Отображает статус с цветным бейджем."""
        colors = {
            'pending': 'blue',
            'running': 'orange',
            'completed': 'green',
            'failed': 'red',
            'cancelled': 'gray'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">●</span> {}',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Статус'
    
    def duration_display(self, obj):
        """Отображает продолжительность."""
        if obj.duration:
            total_seconds = int(obj.duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            if hours:
                return f'{hours}ч {minutes}м {seconds}с'
            elif minutes:
                return f'{minutes}м {seconds}с'
            else:
                return f'{seconds}с'
        return '-'
    duration_display.short_description = 'Длительность'
    
    def products_stats(self, obj):
        """Отображает статистику товаров."""
        return format_html(
            '<span style="color: green;">+{}</span> / '
            '<span style="color: blue;">~{}</span> / '
            '<span style="color: gray;">-{}</span>',
            int(obj.products_created), int(obj.products_updated), int(obj.products_skipped)
        )
    products_stats.short_description = 'Создано / Обновлено / Пропущено'


@admin.register(CategoryMapping)
class CategoryMappingAdmin(admin.ModelAdmin):
    """Админ для маппинга категорий."""
    
    list_display = [
        'external_category_name', 'internal_category', 
        'scraper_config', 'is_active', 'priority'
    ]
    list_filter = ['scraper_config', 'is_active', 'internal_category']
    search_fields = ['external_category_name', 'internal_category__name']
    ordering = ['scraper_config', 'priority', 'external_category_name']
    
    fieldsets = [
        ('Маппинг', {
            'fields': [
                'scraper_config', 'internal_category',
                'external_category_name', 'external_category_url', 'external_category_id'
            ]
        }),
        ('Настройки', {
            'fields': ['is_active', 'priority']
        })
    ]


@admin.register(BrandMapping)
class BrandMappingAdmin(admin.ModelAdmin):
    """Админ для маппинга брендов."""
    
    list_display = [
        'external_brand_name', 'internal_brand', 
        'scraper_config', 'is_active', 'priority'
    ]
    list_filter = ['scraper_config', 'is_active', 'internal_brand']
    search_fields = ['external_brand_name', 'internal_brand__name']
    ordering = ['scraper_config', 'priority', 'external_brand_name']
    
    fieldsets = [
        ('Маппинг', {
            'fields': [
                'scraper_config', 'internal_brand',
                'external_brand_name', 'external_brand_url', 'external_brand_id'
            ]
        }),
        ('Настройки', {
            'fields': ['is_active', 'priority']
        })
    ]


@admin.register(ScrapedProductLog)
class ScrapedProductLogAdmin(admin.ModelAdmin):
    """Админ для логов товаров."""
    
    list_display = [
        'product_name', 'action_badge', 'session', 
        'external_id', 'created_at'
    ]
    list_filter = [
        'action', 'session__scraper_config', 'created_at'
    ]
    search_fields = [
        'product_name', 'external_id', 'external_url', 'message'
    ]
    ordering = ['-created_at']
    
    fieldsets = [
        ('Основная информация', {
            'fields': ['session', 'product', 'action']
        }),
        ('Данные товара', {
            'fields': [
                'product_name', 'external_id', 'external_url'
            ]
        }),
        ('Дополнительно', {
            'fields': ['message', 'scraped_data'],
            'classes': ['collapse']
        })
    ]
    
    readonly_fields = ['created_at']
    
    def action_badge(self, obj):
        """Отображает действие с цветным бейджем."""
        colors = {
            'created': 'green',
            'updated': 'blue',
            'skipped': 'gray',
            'error': 'red',
            'duplicate': 'orange'
        }
        color = colors.get(obj.action, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">●</span> {}',
            color, obj.get_action_display()
        )
    action_badge.short_description = 'Действие'


# Кастомизация админки
admin.site.site_header = 'PharmaTurk - Управление парсерами'
admin.site.site_title = 'PharmaTurk Admin'
admin.site.index_title = 'Панель управления парсерами'
