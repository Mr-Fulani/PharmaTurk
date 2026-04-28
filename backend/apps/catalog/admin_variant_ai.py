from django.contrib import messages
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _


class VariantAIAdminMixin:
    """Общий UI для ручного запуска AI-обработки варианта товара."""

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions["run_variant_ai"] = (
            VariantAIAdminMixin.run_variant_ai,
            "run_variant_ai",
            self.run_variant_ai.short_description,
        )
        actions["apply_variant_ai_draft"] = (
            VariantAIAdminMixin.apply_variant_ai_draft,
            "apply_variant_ai_draft",
            self.apply_variant_ai_draft.short_description,
        )
        return actions

    def get_list_display(self, request):
        list_display = list(super().get_list_display(request))
        if "ai_variant_status" not in list_display:
            insert_at = min(2, len(list_display))
            list_display.insert(insert_at, "ai_variant_status")
        return tuple(list_display)

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        for field in ("ai_variant_status", "ai_variant_preview"):
            if field not in readonly_fields:
                readonly_fields.append(field)
        return tuple(readonly_fields)

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        ai_fields = ("ai_variant_status", "ai_variant_preview")
        for title, options in fieldsets:
            fields = options.get("fields") or ()
            if any(field in fields for field in ai_fields):
                return fieldsets
        fieldsets.append(
            (
                _("AI варианта"),
                {
                    "fields": ai_fields,
                    "description": _(
                        "Ручной запуск AI для варианта. Результат сохраняется только в external_data варианта и не затирает базовую карточку товара."
                    ),
                },
            )
        )
        return fieldsets

    def run_variant_ai(self, request, queryset):
        from apps.ai.tasks import process_variant_ai_task

        submitted = 0
        model_label = queryset.model._meta.label
        for variant in queryset:
            process_variant_ai_task.delay(model_label=model_label, variant_id=variant.pk, force=False)
            submitted += 1

        self.message_user(
            request,
            _(
                "Запущена AI-обработка для %(count)s вариантов. Черновик сохранится только в данных варианта."
            )
            % {"count": submitted},
            level=messages.SUCCESS,
        )

    run_variant_ai.short_description = _("Запустить AI для выбранных вариантов")

    def apply_variant_ai_draft(self, request, queryset):
        applied = 0
        skipped = 0

        for variant in queryset:
            external_data = dict(variant.external_data) if isinstance(variant.external_data, dict) else {}
            payload = external_data.get("ai_variant_content")
            draft = payload.get("draft") if isinstance(payload, dict) else None
            if not isinstance(draft, dict) or not draft:
                skipped += 1
                continue

            ru = draft.get("ru") or {}
            en = draft.get("en") or {}
            update_fields = ["external_data"]

            ru_title = (ru.get("generated_title") or "").strip()
            en_title = (en.get("generated_title") or "").strip()
            if ru_title and getattr(variant, "name", "") != ru_title:
                variant.name = ru_title
                update_fields.append("name")
            if hasattr(variant, "name_en") and en_title and getattr(variant, "name_en", "") != en_title:
                variant.name_en = en_title
                update_fields.append("name_en")

            external_data["ai_variant_applied"] = {
                "status": "applied",
                "applied_at": timezone.now().isoformat(),
                "source_processed_at": payload.get("processed_at") if isinstance(payload, dict) else None,
                "draft": draft,
            }
            variant.external_data = external_data
            variant.save(update_fields=sorted(set(update_fields)))
            applied += 1

        if applied:
            self.message_user(
                request,
                _("Применён AI-черновик к %(count)s вариантам. Изменения записаны только в сам вариант.") % {"count": applied},
                level=messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                _("Пропущено вариантов без готового AI-черновика: %(count)s.") % {"count": skipped},
                level=messages.WARNING,
            )

    apply_variant_ai_draft.short_description = _("Применить черновик AI к выбранным вариантам")

    def ai_variant_status(self, obj):
        applied_payload = self._get_variant_applied_payload(obj)
        if applied_payload:
            applied_at = applied_payload.get("applied_at") or ""
            if applied_at:
                return format_html(
                    '<span style="color:#166534;font-weight:600;">{}</span><br><span style="color:#6b7280;font-size:11px;">{}</span>',
                    _("Применено"),
                    applied_at,
                )
            return format_html(
                '<span style="color:#166534;font-weight:600;">{}</span>',
                _("Применено"),
            )

        payload = self._get_variant_ai_payload(obj)
        if not payload:
            return format_html('<span style="color:#6b7280;">{}</span>', _("Нет черновика"))

        status = payload.get("status") or "unknown"
        colors = {
            "completed": "#15803d",
            "skipped": "#92400e",
            "processing": "#1d4ed8",
            "failed": "#b91c1c",
        }
        labels = {
            "completed": _("Готово"),
            "skipped": _("Пропущено"),
            "processing": _("В обработке"),
            "failed": _("Ошибка"),
            "unknown": _("Неизвестно"),
        }
        label = labels.get(status, status)
        color = colors.get(status, "#374151")
        processed_at = payload.get("processed_at") or payload.get("updated_at") or ""
        if processed_at:
            return format_html(
                '<span style="color:{};font-weight:600;">{}</span><br><span style="color:#6b7280;font-size:11px;">{}</span>',
                color,
                label,
                processed_at,
            )
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>',
            color,
            label,
        )

    ai_variant_status.short_description = _("AI статус")

    def ai_variant_preview(self, obj):
        payload = self._get_variant_applied_payload(obj) or self._get_variant_ai_payload(obj)
        if not payload:
            return _("Черновик варианта ещё не сгенерирован.")

        draft = payload.get("draft") or {}
        ru = draft.get("ru") or {}
        en = draft.get("en") or {}
        ru_text = (ru.get("generated_description") or "").strip()
        en_text = (en.get("generated_description") or "").strip()
        title = (ru.get("generated_title") or en.get("generated_title") or "").strip()
        error_message = (payload.get("error_message") or "").strip()

        fragments = []
        if title:
            fragments.append(format_html("<strong>{}</strong>", title))
        if ru_text:
            fragments.append(format_html("<div><strong>RU:</strong> {}</div>", ru_text[:600]))
        if en_text:
            fragments.append(format_html("<div><strong>EN:</strong> {}</div>", en_text[:600]))
        if error_message:
            fragments.append(
                format_html(
                    "<div style='color:#b91c1c;'><strong>Error:</strong> {}</div>",
                    error_message[:300],
                )
            )
        if not fragments:
            return _("Черновик сохранён, но текст пока пуст.")
        return mark_safe("".join(str(fragment) for fragment in fragments))

    ai_variant_preview.short_description = _("Черновик AI")

    def _get_variant_ai_payload(self, obj):
        external_data = getattr(obj, "external_data", None)
        if not isinstance(external_data, dict):
            return {}
        payload = external_data.get("ai_variant_content")
        return payload if isinstance(payload, dict) else {}

    def _get_variant_applied_payload(self, obj):
        external_data = getattr(obj, "external_data", None)
        if not isinstance(external_data, dict):
            return {}
        payload = external_data.get("ai_variant_applied")
        return payload if isinstance(payload, dict) else {}
