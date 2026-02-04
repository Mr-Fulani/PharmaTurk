from django.contrib import admin
from django.utils.html import format_html
from .models import AIProcessingLog, AITemplate, AIModerationQueue

@admin.register(AIProcessingLog)
class AIProcessingLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'product_link', 'status', 'processing_type', 'created_at', 'cost_usd')
    list_filter = ('status', 'processing_type', 'created_at', 'processed_by')
    search_fields = ('product__name', 'generated_title', 'error_message')
    readonly_fields = ('created_at', 'updated_at', 'completed_at', 'input_data', 'raw_llm_response', 'tokens_used', 'cost_usd', 'processing_time_ms', 'stack_trace')
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('product', 'status', 'processing_type', 'processed_by')
        }),
        ('Результаты генерации', {
            'fields': ('generated_title', 'generated_description', 'suggested_category', 'category_confidence', 'extracted_attributes')
        }),
        ('SEO', {
            'fields': ('generated_seo_title', 'generated_seo_description', 'generated_keywords')
        }),
        ('Анализ изображений', {
            'fields': ('input_images_urls', 'image_analysis')
        }),
        ('Технические метрики', {
            'fields': ('llm_model', 'tokens_used', 'cost_usd', 'processing_time_ms', 'created_at', 'completed_at')
        }),
        ('Отладка', {
            'classes': ('collapse',),
            'fields': ('input_data', 'raw_llm_response', 'error_message', 'stack_trace')
        }),
    )

    def product_link(self, obj):
        if obj.product:
            return format_html('<a href="/admin/catalog/product/{}/change/">{}</a>', obj.product.id, obj.product.name)
        return "-"
    product_link.short_description = 'Товар'

@admin.register(AITemplate)
class AITemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'template_type', 'is_active', 'usage_count', 'updated_at')
    list_filter = ('template_type', 'is_active')
    search_fields = ('name', 'content')

@admin.register(AIModerationQueue)
class AIModerationQueueAdmin(admin.ModelAdmin):
    list_display = ('id', 'log_link', 'priority', 'reason', 'assigned_to', 'created_at', 'resolved_at')
    list_filter = ('priority', 'created_at', 'assigned_to')
    
    def log_link(self, obj):
        return format_html('<a href="/admin/ai/aiprocessinglog/{}/change/">Log #{}</a>', obj.log_entry.id, obj.log_entry.id)
    log_link.short_description = 'Лог обработки'
