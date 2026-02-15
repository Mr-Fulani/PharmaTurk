from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from django.urls import reverse, NoReverseMatch
from apps.catalog.models import (
    ProductMedicines,
    ProductSupplements,
    ProductMedicalEquipment,
    ProductTableware,
    ProductFurniture,
    ProductAccessories,
    JewelryProduct,
    ProductUnderwear,
    ProductHeadwear,
    ProductBooks,
)
from .models import AIProcessingLog, AITemplate, AIModerationQueue, AIProcessingStatus


def _get_product_admin_url(product):
    product_type_map = {
        "medicines": ProductMedicines,
        "supplements": ProductSupplements,
        "medical_equipment": ProductMedicalEquipment,
        "tableware": ProductTableware,
        "furniture": ProductFurniture,
        "accessories": ProductAccessories,
        "jewelry": JewelryProduct,
        "underwear": ProductUnderwear,
        "headwear": ProductHeadwear,
        "books": ProductBooks,
    }
    model = product_type_map.get(product.product_type)
    if model:
        try:
            return reverse(
                f"admin:{model._meta.app_label}_{model._meta.model_name}_change",
                args=[product.id],
            )
        except NoReverseMatch:
            return None
    return None


@admin.register(AIProcessingLog)
class AIProcessingLogAdmin(admin.ModelAdmin):
    change_list_template = "admin/ai/aiprocessinglog/change_list.html"
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
        "image_urls_failed_warning",
        "raw_llm_response",
        "tokens_used",
        "cost_usd",
        "processing_time_ms",
        "stack_trace",
    )
    actions = (
        "apply_to_product",
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
            {"fields": ("input_images_urls", "image_urls_failed_warning", "image_analysis")},
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
            url = _get_product_admin_url(obj.product)
            if url:
                return format_html(
                    '<a href="{}">{}</a>',
                    url,
                    obj.product.name,
                )
            return obj.product.name
        return "-"

    product_link.short_description = "Товар"

    def tokens_total(self, obj):
        tokens = obj.tokens_used or {}
        return tokens.get("total") or tokens.get("total_tokens") or 0

    tokens_total.short_description = "Токены"

    def image_urls_failed_warning(self, obj):
        """Предупреждение о недоступных ссылках на изображения."""
        if not obj or not obj.input_data:
            return ""
        failed = obj.input_data.get("image_urls_failed") or []
        if not failed:
            return ""
        lines = [f"Не удалось загрузить {len(failed)} изображений (ссылки не работают или не изображения):"]
        for u in failed[:10]:
            lines.append(f"• {u[:120]}{'…' if len(u) > 120 else ''}")
        if len(failed) > 10:
            lines.append(f"… и ещё {len(failed) - 10}.")
        return format_html(
            '<div style="background:#fef3c7;padding:8px;border-radius:4px;color:#92400e;">{}</div>',
            mark_safe("<br>".join(escape(ln) for ln in lines)),
        )

    image_urls_failed_warning.short_description = "Предупреждение: недоступные изображения"

    def apply_to_product(self, request, queryset):
        """Применить результат AI к товару (описание, SEO, авторы и т.д.)."""
        from .services.content_generator import ContentGenerator
        gen = ContentGenerator()
        applied = 0
        for log in queryset:
            if log.status not in (
                AIProcessingStatus.COMPLETED,
                AIProcessingStatus.MODERATION,
            ):
                continue
            if not log.product_id:
                continue
            try:
                gen._apply_changes_to_product(log.product, log)
                log.status = AIProcessingStatus.APPROVED
                log.processed_by = request.user
                log.moderation_date = timezone.now()
                log.save(update_fields=["status", "processed_by", "moderation_date"])
                applied += 1
            except Exception as e:
                messages.error(
                    request,
                    f"Лог #{log.id}: не удалось применить — {e}",
                )
        if applied:
            messages.success(
                request,
                f"Результаты применены к {applied} товарам.",
            )

    apply_to_product.short_description = "Применить результат к товару"

    def rerun_ai_full(self, request, queryset):
        from .tasks import process_product_ai_task

        product_ids = list(
            queryset.values_list("product_id", flat=True).distinct()
        )
        for product_id in product_ids:
            process_product_ai_task.delay(
                product_id=product_id, processing_type="full", auto_apply=False
            )
        messages.success(
            request,
            f"Запущена AI обработка (full) для {len(product_ids)} товаров. "
            "Результаты появятся в логах; применить к товару — вручную после одобрения.",
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
                auto_apply=False,
            )
        message = (
            "Запущена AI обработка (description_only) для "
            f"{len(product_ids)} товаров. Результаты в логах; применить — вручную после одобрения."
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
            url = _get_product_admin_url(product)
            if url:
                return format_html(
                    '<a href="{}">{}</a>',
                    url,
                    product.name,
                )
            return product.name
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
