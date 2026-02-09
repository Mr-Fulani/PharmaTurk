from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html
from .models import AIProcessingLog, AITemplate, AIModerationQueue


@admin.register(AIProcessingLog)
class AIProcessingLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product_link",
        "status",
        "processing_type",
        "created_at",
        "completed_at",
        "tokens_total",
        "cost_usd",
        "llm_model",
    )
    list_filter = (
        "status",
        "processing_type",
        "created_at",
        "processed_by",
        "llm_model",
    )
    search_fields = ("product__name", "generated_title", "error_message")
    list_select_related = ("product",)
    date_hierarchy = "created_at"
    readonly_fields = (
        "created_at",
        "updated_at",
        "completed_at",
        "input_data",
        "raw_llm_response",
        "tokens_used",
        "cost_usd",
        "processing_time_ms",
        "stack_trace",
    )
    actions = (
        "rerun_ai_full",
        "rerun_ai_description_only",
        "mark_status_moderation",
        "mark_status_approved",
        "mark_status_rejected",
        "clear_moderation_notes",
    )

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": (
                    "product",
                    "status",
                    "processing_type",
                    "processed_by",
                )
            },
        ),
        (
            "Результаты генерации",
            {
                "fields": (
                    "generated_title",
                    "generated_description",
                    "suggested_category",
                    "category_confidence",
                    "extracted_attributes",
                )
            },
        ),
        (
            "SEO",
            {
                "fields": (
                    "generated_seo_title",
                    "generated_seo_description",
                    "generated_keywords",
                )
            },
        ),
        (
            "Анализ изображений",
            {"fields": ("input_images_urls", "image_analysis")},
        ),
        (
            "Технические метрики",
            {
                "fields": (
                    "llm_model",
                    "tokens_used",
                    "cost_usd",
                    "processing_time_ms",
                    "created_at",
                    "completed_at",
                )
            },
        ),
        (
            "Отладка",
            {
                "classes": ("collapse",),
                "fields": (
                    "input_data",
                    "raw_llm_response",
                    "error_message",
                    "stack_trace",
                ),
            },
        ),
    )

    def product_link(self, obj):
        if obj.product:
            return format_html(
                '<a href="/admin/catalog/product/{}/change/">{}</a>',
                obj.product.id,
                obj.product.name,
            )
        return "-"

    product_link.short_description = "Товар"

    def tokens_total(self, obj):
        tokens = obj.tokens_used or {}
        return tokens.get("total") or tokens.get("total_tokens") or 0

    tokens_total.short_description = "Токены"

    def rerun_ai_full(self, request, queryset):
        from .tasks import process_product_ai_task

        product_ids = list(
            queryset.values_list("product_id", flat=True).distinct()
        )
        for product_id in product_ids:
            process_product_ai_task.delay(
                product_id=product_id, processing_type="full", auto_apply=True
            )
        messages.success(
            request,
            f"Запущена AI обработка (full) для {len(product_ids)} товаров",
        )

    rerun_ai_full.short_description = (
        "Перезапустить AI (full) по товарам"
    )

    def rerun_ai_description_only(self, request, queryset):
        from .tasks import process_product_ai_task

        product_ids = list(
            queryset.values_list("product_id", flat=True).distinct()
        )
        for product_id in product_ids:
            process_product_ai_task.delay(
                product_id=product_id,
                processing_type="description_only",
                auto_apply=True,
            )
        message = (
            "Запущена AI обработка (description_only) для "
            f"{len(product_ids)} товаров"
        )
        messages.success(request, message)

    rerun_ai_description_only.short_description = (
        "Перезапустить AI (description_only) по товарам"
    )

    def mark_status_moderation(self, request, queryset):
        updated = queryset.update(
            status="moderation",
            moderation_date=timezone.now(),
        )
        messages.success(request, f"Отправлено на модерацию: {updated}")

    mark_status_moderation.short_description = "Отправить в модерацию"

    def mark_status_approved(self, request, queryset):
        updated = queryset.update(
            status="approved",
            moderation_date=timezone.now(),
        )
        messages.success(request, f"Одобрено: {updated}")

    mark_status_approved.short_description = "Одобрить"

    def mark_status_rejected(self, request, queryset):
        updated = queryset.update(
            status="rejected",
            moderation_date=timezone.now(),
        )
        messages.success(request, f"Отклонено: {updated}")

    mark_status_rejected.short_description = "Отклонить"

    def clear_moderation_notes(self, request, queryset):
        updated = queryset.update(
            moderation_notes="",
            moderation_date=None,
        )
        messages.success(
            request,
            f"Очищены заметки модератора: {updated}",
        )

    clear_moderation_notes.short_description = "Очистить заметки модератора"


@admin.register(AITemplate)
class AITemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "template_type",
        "language",
        "category",
        "is_active",
        "usage_count",
        "success_rate",
        "updated_at",
    )
    list_filter = ("template_type", "is_active", "language", "category")
    search_fields = ("name", "content")
    readonly_fields = (
        "usage_count",
        "success_rate",
        "created_at",
        "updated_at",
    )
    list_select_related = ("category",)


@admin.register(AIModerationQueue)
class AIModerationQueueAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "log_link",
        "product_link",
        "priority",
        "reason",
        "assigned_to",
        "created_at",
        "resolved_at",
    )
    list_filter = ("priority", "created_at", "assigned_to", "reason")
    list_select_related = (
        "log_entry",
        "assigned_to",
        "log_entry__product",
    )
    date_hierarchy = "created_at"
    actions = (
        "mark_resolved_now",
        "set_priority_low",
        "set_priority_medium",
        "set_priority_high",
    )

    def log_link(self, obj):
        return format_html(
            '<a href="/admin/ai/aiprocessinglog/{}/change/">Log #{}</a>',
            obj.log_entry.id,
            obj.log_entry.id,
        )

    log_link.short_description = "Лог обработки"

    def product_link(self, obj):
        product = getattr(obj.log_entry, "product", None)
        if product:
            return format_html(
                '<a href="/admin/catalog/product/{}/change/">{}</a>',
                product.id,
                product.name,
            )
        return "-"

    product_link.short_description = "Товар"

    def mark_resolved_now(self, request, queryset):
        updated = queryset.update(resolved_at=timezone.now())
        messages.success(request, f"Отмечено как решено: {updated}")

    mark_resolved_now.short_description = "Отметить как решено"

    def set_priority_low(self, request, queryset):
        updated = queryset.update(priority=1)
        messages.success(request, f"Приоритет: низкий ({updated})")

    set_priority_low.short_description = "Приоритет: низкий"

    def set_priority_medium(self, request, queryset):
        updated = queryset.update(priority=2)
        messages.success(request, f"Приоритет: средний ({updated})")

    set_priority_medium.short_description = "Приоритет: средний"

    def set_priority_high(self, request, queryset):
        updated = queryset.update(priority=3)
        messages.success(request, f"Приоритет: высокий ({updated})")

    set_priority_high.short_description = "Приоритет: высокий"
