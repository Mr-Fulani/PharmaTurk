import json
from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from django.urls import reverse, NoReverseMatch
from apps.catalog.models import (
    MedicineProduct,
    SupplementProduct,
    MedicalEquipmentProduct,
    TablewareProduct,
    FurnitureProduct,
    AccessoryProduct,
    JewelryProduct,
    ClothingProduct,
    BookProduct,
    IncenseProduct,
    ShoeProduct,
    PerfumeryProduct,
)
from .models import AIProcessingLog, AITemplate, AIModerationQueue, AIProcessingStatus


def _get_product_admin_url(product):
    """
    Возвращает URL change-страницы доменной модели (BookProduct, ClothingProduct и т.д.)
    для базового товара Product.

    ВАЖНО: ID доменной модели НЕ совпадает с ID Product, поэтому нужно находить
    доменную запись через связь base_product (related_name вида *_item).
    """

    # Карта: product_type -> (модель доменного товара, related_name от Product)
    product_type_map = {
        "medicines": (MedicineProduct, "medicine_item"),
        "supplements": (SupplementProduct, "supplement_item"),
        "medical_equipment": (MedicalEquipmentProduct, "medical_equipment_item"),
        "tableware": (TablewareProduct, "tableware_item"),
        "furniture": (FurnitureProduct, "furniture_item"),
        "accessories": (AccessoryProduct, "accessory_item"),
        "jewelry": (JewelryProduct, "jewelry_item"),
        "clothing": (ClothingProduct, "clothing_item"),
        "underwear": (ClothingProduct, "clothing_item"),
        "headwear": (ClothingProduct, "clothing_item"),
        "shoes": (ShoeProduct, "shoe_item"),
        "books": (BookProduct, "book_item"),
        "perfumery": (PerfumeryProduct, "perfumery_item"),
        "incense": (IncenseProduct, "incense_item"),
    }

    entry = product_type_map.get(product.product_type)
    if not entry:
        return None

    model, rel_name = entry

    # Пытаемся взять доменный объект через related_name (book_item, clothing_item и т.д.)
    domain_obj = getattr(product, rel_name, None)

    # Fallback: если по каким-то причинам related_name не сработал, ищем по base_product
    if domain_obj is None:
        try:
            domain_obj = model.objects.filter(base_product=product).first()
        except Exception:
            domain_obj = None

    if not domain_obj:
        return None

    try:
        return reverse(
            f"admin:{model._meta.app_label}_{model._meta.model_name}_change",
            args=[domain_obj.pk],
        )
    except NoReverseMatch:
        return None


@admin.register(AIProcessingLog)
class AIProcessingLogAdmin(admin.ModelAdmin):
    change_list_template = "admin/ai/aiprocessinglog/change_list.html"
    change_form_template = "admin/ai/aiprocessinglog/change_form.html"
    list_display = (
        "view_log_link",
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
        "moderation_date",
        "input_data",
        "image_urls_failed_warning",
        "formatted_llm_content",
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
            "Модерация",
            {
                "fields": ("moderation_notes", "moderation_date", "updated_at"),
                "description": (
                    "Оставьте заметки для себя или коллег. После правки сгенерированных полей "
                    "нажмите «Сохранить и применить к товару» — изменения сразу уйдут в карточку."
                ),
            },
        ),
        (
            "Технические метрики",
            {
                "classes": ("collapse",),
                "fields": (
                    "llm_model",
                    "tokens_used",
                    "cost_usd",
                    "processing_time_ms",
                    "created_at",
                    "completed_at",
                ),
            },
        ),
        (
            "Ответ LLM (для просмотра и правки выше)",
            {
                "classes": (),
                "fields": ("formatted_llm_content",),
                "description": (
                    "Ниже — ответ модели в удобном виде. Редактируйте поля в блоках «Результаты генерации» и «SEO» выше — "
                    "именно они будут применены к товару по кнопке «Сохранить и применить к товару»."
                ),
            },
        ),
        (
            "Отладка (сырой ответ и ошибки)",
            {
                "classes": ("collapse",),
                "fields": (
                    "input_data",
                    "raw_llm_response",
                    "error_message",
                    "stack_trace",
                ),
                "description": "Если «Результаты генерации» и «SEO» пустые — откройте raw_llm_response и проверьте формат ответа модели.",
            },
        ),
    )

    def formatted_llm_content(self, obj):
        """
        Показывает ответ LLM в удобном для человека виде: секции RU/EN/SEO/категория,
        затем полный JSON в сворачиваемом блоке. Редактировать нужно поля выше (результаты, SEO).
        """
        if not obj or not obj.raw_llm_response:
            return mark_safe("<p>Ответ модели ещё не получен или пуст.</p>")
        raw = obj.raw_llm_response
        content = raw.get("content") if isinstance(raw, dict) else raw
        if content is None:
            content = raw
        if not isinstance(content, dict):
            try:
                content = json.loads(content) if isinstance(content, str) else {"_raw": str(content)}
            except (TypeError, ValueError):
                content = {"_raw": str(content)[:2000]}
        parts = []
        # Секция RU
        ru = content.get("ru") or content
        if isinstance(ru, dict):
            ru_title = ru.get("generated_title") or ""
            ru_desc = ru.get("generated_description") or ""
            if ru_title or ru_desc:
                parts.append(
                    '<div class="formatted-llm-section" style="margin-bottom: 1em;">'
                    '<strong style="color: #0c5460;">Русский (ru)</strong>'
                    '<div style="margin-left: 0.5em; margin-top: 0.25em;">'
                    f'<div><strong>Заголовок:</strong> {escape(ru_title) or "—"}</div>'
                    f'<div><strong>Описание:</strong><div class="formatted-llm-block" style="white-space: pre-wrap; max-height: 200px; overflow: auto; background: #f8f9fa; padding: 0.5em; border-radius: 4px; margin-top: 0.25em;">{escape(ru_desc) or "—"}</div></div>'
                    "</div></div>"
                )
        # Секция EN
        en = content.get("en")
        if isinstance(en, dict):
            en_title = en.get("generated_title") or ""
            en_desc = en.get("generated_description") or ""
            seo_title = en.get("seo_title") or ""
            seo_desc = en.get("seo_description") or ""
            keywords = en.get("keywords") or []
            kw_str = ", ".join(str(x) for x in keywords if x)[:500] if keywords else "—"
            if any([en_title, en_desc, seo_title, seo_desc, kw_str != "—"]):
                parts.append(
                    '<div class="formatted-llm-section" style="margin-bottom: 1em;">'
                    '<strong style="color: #0c5460;">English (en)</strong>'
                    '<div style="margin-left: 0.5em; margin-top: 0.25em;">'
                    f'<div><strong>Title:</strong> {escape(en_title) or "—"}</div>'
                    f'<div><strong>Description:</strong><div class="formatted-llm-block" style="white-space: pre-wrap; max-height: 200px; overflow: auto; background: #f8f9fa; padding: 0.5em; border-radius: 4px; margin-top: 0.25em;">{escape(en_desc) or "—"}</div></div>'
                    f'<div><strong>SEO title:</strong> {escape(seo_title) or "—"}</div>'
                    f'<div><strong>SEO description:</strong> {escape(seo_desc) or "—"}</div>'
                    f'<div><strong>Keywords:</strong> {escape(kw_str)}</div>'
                    "</div></div>"
                )
        # Категория
        cat_name = content.get("suggested_category_name") or ""
        conf = content.get("category_confidence")
        if cat_name or conf is not None:
            parts.append(
                '<div class="formatted-llm-section" style="margin-bottom: 1em;">'
                '<strong style="color: #0c5460;">Категория</strong>'
                f'<div style="margin-left: 0.5em;">{escape(cat_name) or "—"}'
                f'{f" (уверенность: {conf})" if conf is not None else ""}</div></div>'
            )
        # Атрибуты
        attrs = content.get("attributes")
        if isinstance(attrs, dict) and attrs:
            attrs_str = json.dumps(attrs, ensure_ascii=False, indent=2)
            parts.append(
                '<div class="formatted-llm-section" style="margin-bottom: 1em;">'
                '<strong style="color: #0c5460;">Атрибуты</strong>'
                f'<pre class="formatted-llm-block" style="white-space: pre-wrap; max-height: 150px; overflow: auto; background: #f8f9fa; padding: 0.5em; border-radius: 4px; font-size: 12px;">{escape(attrs_str)}</pre></div>'
            )
        if not parts:
            parts.append("<p>В ответе нет распознанных полей ru/en/SEO. См. полный JSON ниже.</p>")
        # Полный JSON в сворачиваемом блоке
        try:
            json_str = json.dumps(content, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            json_str = str(content)
        parts.append(
            '<details style="margin-top: 0.5em;">'
            '<summary style="cursor: pointer; color: #0c5460;">Полный JSON ответа</summary>'
            f'<pre class="formatted-llm-block" style="white-space: pre-wrap; max-height: 400px; overflow: auto; background: #f1f3f4; padding: 0.75em; border-radius: 4px; font-size: 12px; margin-top: 0.25em;">{escape(json_str)}</pre>'
            "</details>"
        )
        return mark_safe("<div class=\"formatted-llm-content\">" + "".join(parts) + "</div>")

    formatted_llm_content.short_description = "Ответ LLM (читабельный вид)"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """Добавляем кнопку «Сохранить и применить к товару» в форму лога."""
        extra_context = extra_context or {}
        extra_context["show_save_and_apply"] = True
        return super().change_view(request, object_id, form_url, extra_context)

    def response_change(self, request, obj):
        """Обрабатываем нажатие кнопки «Сохранить и применить к товару»."""
        if "_save_and_apply" in request.POST:
            # Применяем отредактированные AI-данные к товару
            if obj.status not in (AIProcessingStatus.COMPLETED, AIProcessingStatus.MODERATION):
                messages.warning(
                    request,
                    f"Лог #{obj.id}: применение невозможно — статус «{obj.get_status_display()}». "
                    "Нужен статус «Завершено» или «На модерации».",
                )
                return self._response_post_save(request, obj)
            try:
                from .services.content_generator import ContentGenerator
                gen = ContentGenerator()
                gen._apply_changes_to_product(obj.product, obj)
                obj.status = AIProcessingStatus.APPROVED
                obj.processed_by = request.user
                obj.moderation_date = timezone.now()
                obj.save(update_fields=["status", "processed_by", "moderation_date"])
                messages.success(
                    request,
                    f"Лог #{obj.id}: результаты применены к товару «{obj.product.name}».",
                )
            except Exception as e:
                messages.error(request, f"Ошибка при применении: {e}")
            return self._response_post_save(request, obj)
        return super().response_change(request, obj)

    def _response_post_save(self, request, obj):
        """Редирект обратно на форму после сохранения."""
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(
            reverse("admin:ai_aiprocessinglog_change", args=[obj.pk])
        )

    def view_log_link(self, obj):
        """Ссылка на форму лога (результаты AI). Клик сюда — просмотр и применение."""
        if obj.pk:
            url = reverse("admin:ai_aiprocessinglog_change", args=[obj.pk])
            return format_html(
                '<a href="{}" style="font-weight: bold;">Просмотр / применить</a>',
                url,
            )
        return "-"

    view_log_link.short_description = "Результаты AI"

    def product_link(self, obj):
        if obj.product:
            url = _get_product_admin_url(obj.product)
            name = obj.product.name
            if url:
                return format_html(
                    '{} <a href="{}" style="font-size:11px;color:#999;">→ товар</a>',
                    escape(name),
                    url,
                )
            return name
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
