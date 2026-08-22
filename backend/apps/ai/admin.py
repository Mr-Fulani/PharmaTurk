import json
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from django.urls import path, reverse, NoReverseMatch
from .models import (
    AIApplicationStatus,
    AIProcessingLog,
    AIProcessingStatus,
    AIModerationQueue,
    AITemplate,
)
from .services.moderation import (
    APPLICATION_LABELS,
    build_change_preview,
    get_moderation_reason_labels,
    get_workflow_title,
    reject_log,
)
from .services.size_inventory import (
    merge_confirmed_sizes,
    parse_moderator_size_list,
    strip_size_inventory_sentences,
    supports_size_inventory,
)


# Атрибуты украшений для формы модерации (применяются к JewelryProduct)
JEWELRY_TYPE_CHOICES = [
    ("", "—"),
    ("ring", "Кольцо"),
    ("bracelet", "Браслет"),
    ("necklace", "Цепь/ожерелье"),
    ("earrings", "Серьги"),
    ("pendant", "Подвеска"),
]
GENDER_CHOICES_FORM = [
    ("", "—"),
    ("men", "Мужская"),
    ("women", "Женская"),
    ("unisex", "Унисекс"),
    ("kids", "Детская"),
]
JEWELRY_FORM_FIELDS = (
    "jewelry_type",
    "material",
    "metal_purity",
    "stone_type",
    "carat_weight",
    "gender",
)


class AIProcessingLogForm(forms.ModelForm):
    """Форма с полями EN/OG и атрибутами украшений; всё хранится в extracted_attributes и применяется к товару."""
    generated_en_title = forms.CharField(
        max_length=255,
        required=False,
        label="Заголовок (EN)",
        help_text="Английское название — уходит в перевод en и в карточку товара.",
        widget=forms.TextInput(attrs={"size": 80}),
    )
    generated_en_description = forms.CharField(
        required=False,
        label="Описание (EN)",
        help_text="Английское описание — уходит в перевод en.",
        widget=forms.Textarea(attrs={"rows": 4, "cols": 80}),
    )
    og_title = forms.CharField(
        max_length=255,
        required=False,
        label="OG title",
        help_text="og:title для соцсетей (латиница).",
        widget=forms.TextInput(attrs={"size": 80}),
    )
    og_description = forms.CharField(
        max_length=255,
        required=False,
        label="OG description",
        help_text="og:description для соцсетей (латиница).",
        widget=forms.Textarea(attrs={"rows": 2, "cols": 80}),
    )
    inventory_sizes = forms.CharField(
        required=False,
        label="Доступные размеры",
        help_text=(
            "Через запятую. При применении размеры добавятся в карточку товара; "
            "существующие размеры и остатки не удаляются."
        ),
        widget=forms.TextInput(attrs={"size": 80, "placeholder": "M, XL, 2XL"}),
    )
    # Атрибуты украшений (применяются к JewelryProduct при «Сохранить и применить»)
    jewelry_type = forms.ChoiceField(
        choices=JEWELRY_TYPE_CHOICES,
        required=False,
        label="Тип украшения",
        widget=forms.Select(attrs={"style": "max-width: 200px"}),
    )
    material = forms.CharField(
        max_length=100,
        required=False,
        label="Материал",
        widget=forms.TextInput(attrs={"size": 40}),
    )
    metal_purity = forms.CharField(
        max_length=50,
        required=False,
        label="Проба металла",
        help_text="Напр. 925, 585",
        widget=forms.TextInput(attrs={"size": 20}),
    )
    stone_type = forms.CharField(
        max_length=100,
        required=False,
        label="Тип камня",
        widget=forms.TextInput(attrs={"size": 40}),
    )
    carat_weight = forms.DecimalField(
        required=False,
        label="Вес камней (карат)",
        min_value=0,
        max_digits=6,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "style": "width: 100px"}),
    )
    gender = forms.ChoiceField(
        choices=GENDER_CHOICES_FORM,
        required=False,
        label="Пол",
        widget=forms.Select(attrs={"style": "max-width: 120px"}),
    )

    class Meta:
        model = AIProcessingLog
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["generated_title"].label = "Название (RU)"
        self.fields["generated_description"].label = "Описание (RU)"
        self.fields["generated_seo_title"].label = "SEO title (RU)"
        self.fields["generated_seo_description"].label = "SEO description (RU)"
        self.fields["generated_keywords"].label = "Ключевые слова (RU)"
        product = getattr(self.instance, "product", None) if self.instance else None
        product_type = getattr(product, "product_type", None)
        attrs = self.instance.extracted_attributes or {} if self.instance else {}
        if self.instance and self.instance.pk:
            seo_translations = attrs.get("seo_translations") or {}
            seo_en = seo_translations.get("en") or attrs.get("seo_en") or {}
            self.fields["generated_en_title"].initial = seo_en.get("generated_title") or ""
            self.fields["generated_en_description"].initial = seo_en.get("generated_description") or ""
            self.fields["og_title"].initial = seo_en.get("og_title") or ""
            self.fields["og_description"].initial = seo_en.get("og_description") or ""
            # Атрибуты украшений из лога или с карточки товара
            self.fields["jewelry_type"].initial = attrs.get("jewelry_type") or ""
            self.fields["material"].initial = attrs.get("material") or ""
            self.fields["metal_purity"].initial = attrs.get("metal_purity") or ""
            self.fields["stone_type"].initial = attrs.get("stone_type") or ""
            self.fields["carat_weight"].initial = attrs.get("carat_weight")
            self.fields["gender"].initial = attrs.get("gender") or ""
            if product and getattr(product, "product_type", None) == "jewelry":
                domain = getattr(product, "jewelry_item", None)
                if domain and not attrs.get("metal_purity") and getattr(domain, "metal_purity", None):
                    self.fields["metal_purity"].initial = domain.metal_purity
                if domain and not attrs.get("material") and getattr(domain, "material", None):
                    self.fields["material"].initial = domain.material
                if domain and not attrs.get("jewelry_type") and getattr(domain, "jewelry_type", None):
                    self.fields["jewelry_type"].initial = domain.jewelry_type
                if domain and not attrs.get("stone_type") and getattr(domain, "stone_type", None):
                    self.fields["stone_type"].initial = domain.stone_type
                if domain and getattr(domain, "gender", None):
                    self.fields["gender"].initial = domain.gender or ""
            else:
                # Эти поля имеют смысл только для JewelryAIApplier. Если оставить
                # их в bound-форме другого типа, пустые значения могут затереть
                # одноимённые ключи extracted_attributes чужой категории.
                for field_name in JEWELRY_FORM_FIELDS:
                    self.fields.pop(field_name, None)
        elif product_type != "jewelry":
            for field_name in JEWELRY_FORM_FIELDS:
                self.fields.pop(field_name, None)

        if supports_size_inventory(product_type):
            effective_attrs = merge_confirmed_sizes(
                attrs,
                getattr(self.instance, "input_data", None) or {},
                product_type,
                allow_moderator_override=True,
            )
            self.fields["inventory_sizes"].initial = ", ".join(
                row["size"] for row in effective_attrs.get("sizes") or []
            )
            # Legacy logs may still contain size inventory in generated prose.
            # Show the moderator exactly the cleaned values that the applier
            # will write, instead of making the preview and edit form disagree.
            self.initial["generated_description"] = strip_size_inventory_sentences(
                getattr(self.instance, "generated_description", "")
            )
            self.initial["generated_seo_description"] = strip_size_inventory_sentences(
                getattr(self.instance, "generated_seo_description", "")
            )
            self.fields["generated_en_description"].initial = strip_size_inventory_sentences(
                self.fields["generated_en_description"].initial
            )
            self.fields["og_description"].initial = strip_size_inventory_sentences(
                self.fields["og_description"].initial
            )
        else:
            self.fields.pop("inventory_sizes", None)

    def save(self, commit=True):
        obj = super().save(commit=commit)
        if obj.pk:
            attrs = dict(obj.extracted_attributes or {})
            seo_translations = dict(attrs.get("seo_translations") or {})
            seo_ru = dict(seo_translations.get("ru") or {})
            seo_en = dict(seo_translations.get("en") or attrs.get("seo_en") or {})
            # RU-поля формы — единственный редактируемый источник истины.
            # Без этой синхронизации apply предпочитал старый вложенный RU payload
            # и мог проигнорировать видимую правку модератора.
            seo_ru.update(
                {
                    "generated_title": (obj.generated_title or "").strip() or None,
                    "generated_description": (obj.generated_description or "").strip() or None,
                    "meta_title": (obj.generated_seo_title or "").strip() or None,
                    "meta_description": (obj.generated_seo_description or "").strip() or None,
                    "meta_keywords": obj.generated_keywords or [],
                }
            )
            if self.cleaned_data.get("generated_en_title") is not None:
                seo_en["generated_title"] = (self.cleaned_data.get("generated_en_title") or "").strip() or None
            if self.cleaned_data.get("generated_en_description") is not None:
                seo_en["generated_description"] = (self.cleaned_data.get("generated_en_description") or "").strip() or None
            if self.cleaned_data.get("og_title") is not None:
                seo_en["og_title"] = (self.cleaned_data.get("og_title") or "").strip() or None
            if self.cleaned_data.get("og_description") is not None:
                seo_en["og_description"] = (self.cleaned_data.get("og_description") or "").strip() or None
            seo_translations["ru"] = seo_ru
            seo_translations["en"] = seo_en
            attrs["seo_translations"] = seo_translations
            attrs["seo_en"] = seo_en
            product_type = getattr(getattr(obj, "product", None), "product_type", None)
            if "inventory_sizes" in self.cleaned_data and supports_size_inventory(product_type):
                moderator_sizes = parse_moderator_size_list(
                    self.cleaned_data.get("inventory_sizes"),
                    product_type,
                )
                attrs["moderator_sizes"] = moderator_sizes
                attrs["sizes"] = moderator_sizes
            # Атрибуты украшений
            for key, field_name in [
                ("jewelry_type", "jewelry_type"),
                ("material", "material"),
                ("metal_purity", "metal_purity"),
                ("stone_type", "stone_type"),
                ("carat_weight", "carat_weight"),
                ("gender", "gender"),
            ]:
                if field_name not in self.cleaned_data:
                    continue
                val = self.cleaned_data.get(field_name)
                if val is not None:
                    if val == "" or (isinstance(val, (int, float)) and val == 0 and key != "carat_weight"):
                        attrs[key] = None
                    else:
                        attrs[key] = val
            obj.extracted_attributes = attrs
            if commit:
                obj.save(update_fields=["extracted_attributes"])
        return obj


def _get_product_admin_url(product):
    """URL фактической доменной карточки для любого зарегистрированного типа."""
    if product is None:
        return None
    domain_obj = product.domain_item
    try:
        return reverse(
            f"admin:{domain_obj._meta.app_label}_{domain_obj._meta.model_name}_change",
            args=[domain_obj.pk],
        )
    except NoReverseMatch:
        return None


@admin.register(AIProcessingLog)
class AIProcessingLogAdmin(admin.ModelAdmin):
    form = AIProcessingLogForm
    change_list_template = "admin/ai/aiprocessinglog/change_list.html"
    change_form_template = "admin/ai/aiprocessinglog/change_form.html"
    # The production catalog contains thousands of products and categories.
    # Rendering all of them as <select> options on every log change page causes
    # large allocations in the already memory-constrained gunicorn workers.
    raw_id_fields = ("suggested_category",)
    list_display = (
        "view_log_link",
        "id",
        "product_link",
        "workflow_state",
        "application_state",
        "processing_type",
        "celery_task_id",
        "created_at",
        "completed_at",
        "tokens_total",
        "cost_usd",
        "llm_model",
    )
    list_filter = (
        "status",
        "application_status",
        "processing_type",
        "created_at",
        "processed_by",
        "llm_model",
    )
    search_fields = ("product__name", "generated_title", "error_message")
    list_select_related = ("product",)
    date_hierarchy = "created_at"
    readonly_fields = (
        "workflow_overview",
        "change_preview",
        "product",
        "status",
        "application_status",
        "application_report_view",
        "applied_at",
        "processed_by",
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
        "reject_results",
        "rerun_ai_full",
        "rerun_ai_description_only",
    )

    def get_urls(self):
        """Keep rerun independent from validation of the editable log form."""
        custom_urls = [
            path(
                "<path:object_id>/rerun/",
                self.admin_site.admin_view(self.rerun_view),
                name="ai_aiprocessinglog_rerun",
            ),
        ]
        return custom_urls + super().get_urls()

    def rerun_view(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404("AI processing log does not exist")
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        return self._enqueue_rerun(request, obj)

    @admin.display(description="Celery task", ordering="created_at")
    def celery_task_id(self, obj):
        return str((obj.input_data or {}).get("celery_task_id") or "—")

    @admin.display(description="Состояние", ordering="status")
    def workflow_state(self, obj):
        title, tone = get_workflow_title(obj)
        colors = {
            "success": ("#166534", "#dcfce7"),
            "warning": ("#92400e", "#fef3c7"),
            "danger": ("#991b1b", "#fee2e2"),
            "info": ("#075985", "#e0f2fe"),
            "neutral": ("#374151", "#f3f4f6"),
        }
        foreground, background = colors.get(tone, colors["neutral"])
        return format_html(
            '<span style="display:inline-block;padding:3px 8px;border-radius:999px;'
            'font-weight:600;color:{};background:{};">{}</span>',
            foreground,
            background,
            title,
        )

    @admin.display(description="Применение", ordering="application_status")
    def application_state(self, obj):
        return APPLICATION_LABELS.get(obj.application_status, obj.get_application_status_display())

    fieldsets = (
        (
            "Состояние и товар",
            {
                "fields": (
                    "workflow_overview",
                    "product",
                    "processing_type",
                    "status",
                    "application_status",
                    "processed_by",
                    "moderation_date",
                    "applied_at",
                ),
            },
        ),
        (
            "Что изменится в товаре",
            {
                "fields": ("change_preview",),
                "description": (
                    "Сравнение строится по фактической доменной карточке товара. "
                    "Заблокированные поля сервис применения не запишет."
                ),
            },
        ),
        (
            "Контент на русском",
            {
                "fields": (
                    "generated_title",
                    "generated_description",
                ),
                "description": "Можно исправить предложение AI перед применением.",
            },
        ),
        (
            "Категория",
            {
                "fields": (
                    "suggested_category",
                    "category_confidence",
                    "category_alternatives",
                ),
                "description": "Категория применяется только при уверенности не ниже 75%.",
            },
        ),
        (
            "SEO на русском",
            {
                "fields": (
                    "generated_seo_title",
                    "generated_seo_description",
                    "generated_keywords",
                )
            },
        ),
        (
            "Контент и SEO на английском",
            {
                "fields": (
                    "generated_en_title",
                    "generated_en_description",
                    "og_title",
                    "og_description",
                ),
                "description": "Эти поля попадут в перевод EN и SEO/OG карточки.",
            },
        ),
        (
            "Размеры и наличие",
            {
                "fields": ("inventory_sizes",),
                "description": (
                    "Размеры хранятся в отдельных полях карточки и не попадут в описание. "
                    "Если у товара есть варианты, применение будет остановлено до выбора варианта."
                ),
            },
        ),
        (
            "Атрибуты украшения (применяются к карточке товара)",
            {
                "fields": (
                    "jewelry_type",
                    "material",
                    "metal_purity",
                    "stone_type",
                    "carat_weight",
                    "gender",
                ),
                "description": "Этот блок отображается только для товаров типа «Украшения».",
            },
        ),
        (
            "Решение модератора",
            {
                "fields": ("moderation_notes",),
                "description": (
                    "Оставьте пояснение для коллег. Основная кнопка одновременно сохранит правки, "
                    "применит разрешённые поля и закроет очередь при полном успехе."
                ),
            },
        ),
        (
            "Извлечённые атрибуты (JSON)",
            {
                "classes": ("collapse",),
                "fields": ("extracted_attributes",),
                "description": (
                    "Техническое редактирование атрибутов для всех категорий. "
                    "Итоговые значения показаны в таблице сравнения выше."
                ),
            },
        ),
        (
            "Анализ изображений",
            {
                "classes": ("collapse",),
                "fields": ("input_images_urls", "image_urls_failed_warning", "image_analysis"),
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
                    "updated_at",
                    "application_report_view",
                ),
            },
        ),
        (
            "Исходный ответ AI",
            {
                "classes": ("collapse",),
                "fields": ("formatted_llm_content",),
                "description": (
                    "Только для сверки. Источником применения служат редактируемые поля выше."
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

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        product_type = getattr(getattr(obj, "product", None), "product_type", None)
        if product_type != "jewelry":
            fieldsets = [
                fieldset
                for fieldset in fieldsets
                if fieldset[0] != "Атрибуты украшения (применяются к карточке товара)"
            ]
        if not supports_size_inventory(product_type):
            fieldsets = [
                fieldset for fieldset in fieldsets if fieldset[0] != "Размеры и наличие"
            ]
        return fieldsets

    @admin.display(description="Итог обработки")
    def workflow_overview(self, obj):
        if not obj or not obj.pk:
            return "—"
        title, tone = get_workflow_title(obj)
        colors = {
            "success": ("#166534", "#dcfce7", "#86efac"),
            "warning": ("#92400e", "#fef3c7", "#fcd34d"),
            "danger": ("#991b1b", "#fee2e2", "#fca5a5"),
            "info": ("#075985", "#e0f2fe", "#7dd3fc"),
            "neutral": ("#374151", "#f3f4f6", "#d1d5db"),
        }
        foreground, background, border = colors.get(tone, colors["neutral"])
        reasons = []
        if obj.status in (AIProcessingStatus.COMPLETED, AIProcessingStatus.MODERATION):
            try:
                reasons = get_moderation_reason_labels(
                    obj,
                    semantic_report=self._semantic_report(obj),
                )
            except Exception as exc:
                reasons = [f"Не удалось рассчитать причины: {exc}"]
        product_url = _get_product_admin_url(obj.product)
        product_link = escape(obj.product.name)
        if product_url:
            product_link = (
                f'<a href="{escape(product_url)}" target="_blank" rel="noopener" '
                f'style="font-weight:700;">{escape(obj.product.name)} ↗</a>'
            )
        reason_html = ""
        if reasons:
            reason_html = (
                '<ul style="margin:8px 0 0 18px;">'
                + "".join(f"<li>{escape(reason)}</li>" for reason in reasons)
                + "</ul>"
            )
        application_label = APPLICATION_LABELS.get(
            obj.application_status,
            obj.get_application_status_display(),
        )
        return mark_safe(
            f'<div class="ai-workflow-card" style="padding:14px 16px;border:1px solid {border};'
            f'border-left:5px solid {border};background:{background};color:{foreground};'
            'border-radius:6px;max-width:1100px;">'
            f'<div style="font-size:17px;font-weight:800;">{escape(title)}</div>'
            f'<div style="margin-top:6px;color:inherit;">Товар: {product_link}</div>'
            f'<div style="margin-top:3px;color:inherit;">Тип: '
            f'{escape(obj.product.get_product_type_display())} · Применение: '
            f'<strong>{escape(application_label)}</strong></div>'
            f'{reason_html}</div>'
        )

    @admin.display(description="Сравнение текущего товара и результата AI")
    def change_preview(self, obj):
        if not obj or not obj.pk:
            return "—"
        try:
            rows = build_change_preview(
                obj,
                semantic_report=self._semantic_report(obj),
            )
        except Exception as exc:
            return format_html(
                '<div style="color:#991b1b;background:#fee2e2;padding:10px;border-radius:4px;">'
                "Не удалось построить сравнение: {}</div>",
                str(exc),
            )
        if not rows:
            return mark_safe(
                '<div style="padding:10px;background:#f3f4f6;border-radius:4px;">'
                "AI не предложил полей, которые поддерживает текущий обработчик товара.</div>"
            )
        decision_colors = {
            "apply": ("#166534", "#dcfce7"),
            "unchanged": ("#374151", "#f3f4f6"),
            "blocked": ("#991b1b", "#fee2e2"),
            "preserved": ("#92400e", "#fef3c7"),
            "empty": ("#6b7280", "#f9fafb"),
        }
        body = []
        previous_section = None
        hide_unchanged = getattr(obj.product, "product_type", None) == "medicines"
        unchanged_count = sum(row.decision == "unchanged" for row in rows)
        changed_count = sum(row.decision == "apply" for row in rows)
        blocked_count = sum(row.decision == "blocked" for row in rows)
        table_id = f"ai-preview-{obj.pk}"
        section_decisions = {}
        for preview_row in rows:
            section_decisions.setdefault(preview_row.section, []).append(preview_row.decision)
        for row in rows:
            if row.section != previous_section:
                section_hidden = (
                    hide_unchanged
                    and all(
                        decision == "unchanged"
                        for decision in section_decisions.get(row.section, [])
                    )
                )
                section_class = "ai-preview-unchanged" if section_hidden else "ai-preview-section"
                section_style = "display:none;" if section_hidden else ""
                body.append(
                    f'<tr class="ai-preview-section {section_class}" style="{section_style}"><th colspan="4" '
                    'style="text-align:left;padding:9px 10px;background:#e5e7eb;color:#111827;">'
                    f'{escape(row.section)}</th></tr>'
                )
                previous_section = row.section
            foreground, background = decision_colors.get(
                row.decision,
                decision_colors["unchanged"],
            )
            reason = (
                f'<div style="font-size:11px;margin-top:3px;">{escape(row.reason)}</div>'
                if row.reason
                else ""
            )
            row_hidden = hide_unchanged and row.decision == "unchanged"
            row_class = "ai-preview-unchanged" if row_hidden else ""
            row_style = "display:none;" if row_hidden else ""
            body.append(
                f'<tr class="{row_class}" style="{row_style}">'
                f'<td style="font-weight:650;min-width:150px;">{escape(row.label)}</td>'
                f'<td><div class="ai-preview-value">{escape(row.current)}</div></td>'
                f'<td><div class="ai-preview-value">{escape(row.proposed)}</div></td>'
                f'<td><span style="display:inline-block;padding:3px 7px;border-radius:999px;'
                f'font-weight:650;color:{foreground};background:{background};">'
                f'{escape(row.decision_label)}</span>{reason}</td>'
                "</tr>"
            )
        toggle = ""
        if hide_unchanged and unchanged_count:
            toggle = (
                f'<button type="button" class="button" style="margin-left:8px;" '
                f'onclick="var rows=document.querySelectorAll(\'#{table_id} .ai-preview-unchanged\');'
                "var show=Array.prototype.some.call(rows,function(row){return row.style.display===\'none\';});"
                "Array.prototype.forEach.call(rows,function(row){row.style.display=show?\'table-row\':\'none\';});"
                f'this.textContent=show?\'Скрыть неизменённые ({unchanged_count})\':\'Показать неизменённые ({unchanged_count})\';">'
                f'Показать неизменённые ({unchanged_count})</button>'
            )
        summary = (
            '<div style="margin:0 0 10px;padding:8px 10px;background:#f3f4f6;border-radius:4px;">'
            f'<strong>Будет изменено: {changed_count}</strong> · '
            f'Заблокировано: {blocked_count} · Без изменений: {unchanged_count}{toggle}</div>'
        )
        return mark_safe(
            summary
            +
            '<div class="ai-preview-wrap" style="overflow-x:auto;max-width:1200px;">'
            f'<table id="{table_id}" class="ai-preview-table" style="width:100%;border-collapse:collapse;">'
            '<thead><tr><th>Поле</th><th>Сейчас в товаре</th><th>Предложение AI</th>'
            '<th>Что произойдёт</th></tr></thead><tbody>'
            + "".join(body)
            + "</tbody></table></div>"
        )

    @staticmethod
    def _semantic_report(obj):
        """Calculate semantic validation once for all read-only admin blocks."""
        cache_attr = "_ai_admin_semantic_report"
        report = getattr(obj, cache_attr, None)
        if report is None:
            from .services.semantic_validator import SemanticValidator

            report = SemanticValidator().validate_log(obj)
            setattr(obj, cache_attr, report)
        return report

    @admin.display(description="Последний отчёт применения")
    def application_report_view(self, obj):
        if not obj or not obj.application_report:
            return "—"
        return format_html(
            '<pre style="white-space:pre-wrap;max-height:260px;overflow:auto;">{}</pre>',
            json.dumps(obj.application_report, ensure_ascii=False, indent=2),
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
        """Добавить контекст однозначных действий модератора."""
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj is not None:
            extra_context.update(
                {
                    "can_review_and_apply": obj.status
                    in (
                        AIProcessingStatus.COMPLETED,
                        AIProcessingStatus.MODERATION,
                        AIProcessingStatus.APPROVED,
                    ),
                    "can_reject_result": obj.status
                    in (AIProcessingStatus.COMPLETED, AIProcessingStatus.MODERATION),
                    "can_rerun_ai": obj.status
                    not in (AIProcessingStatus.PENDING, AIProcessingStatus.PROCESSING),
                    "is_reapply": obj.status == AIProcessingStatus.APPROVED,
                    "product_admin_url": _get_product_admin_url(obj.product),
                    "rerun_url": reverse(
                        "admin:ai_aiprocessinglog_rerun",
                        args=[obj.pk],
                    ),
                }
            )
        return super().change_view(request, object_id, form_url, extra_context)

    def response_change(self, request, obj):
        """Обработать review/apply, reject и re-run из формы лога."""
        if "_save_and_apply" in request.POST:
            if obj.status not in (
                AIProcessingStatus.COMPLETED,
                AIProcessingStatus.MODERATION,
                AIProcessingStatus.APPROVED,
            ):
                messages.warning(
                    request,
                    f"Лог #{obj.id}: применение невозможно — статус «{obj.get_status_display()}». "
                    "Нужен завершённый, проверяемый или уже применённый результат.",
                )
                return self._response_post_save(request, obj)
            try:
                from .services.content_generator import ContentGenerator
                gen = ContentGenerator()
                gen.apply_log_to_product(
                    obj,
                    user=request.user,
                    allow_approved=True,
                )
                if obj.application_status == AIApplicationStatus.PARTIAL:
                    rejected = (obj.application_report or {}).get("rejected_fields") or []
                    messages.warning(
                        request,
                        f"Лог #{obj.id}: разрешённые поля применены, но "
                        f"заблокированных полей не перенесено: {len(rejected)}. "
                        "Запись остаётся на модерации; отдельное предварительное "
                        "одобрение не требуется.",
                    )
                else:
                    messages.success(
                        request,
                        f"Лог #{obj.id}: проверено и применено к товару «{obj.product.name}». "
                        "Очередь модерации закрыта.",
                    )
            except Exception as e:
                messages.error(request, f"Ошибка при применении: {e}")
            return self._response_post_save(request, obj)
        if "_reject_result" in request.POST:
            try:
                reject_log(
                    obj,
                    user=request.user,
                    notes=obj.moderation_notes or "",
                )
                messages.success(request, f"Лог #{obj.id}: результат отклонён.")
            except ValueError as exc:
                messages.warning(request, str(exc))
            return self._response_post_save(request, obj)
        if "_rerun_ai" in request.POST:
            return self._enqueue_rerun(request, obj)
        return super().response_change(request, obj)

    def _enqueue_rerun(self, request, obj):
        from .tasks import enqueue_product_ai_task

        try:
            queued_log, _task_id, submitted = enqueue_product_ai_task(
                product_id=obj.product_id,
                processing_type=obj.processing_type,
                auto_apply=False,
                force=True,
            )
            if submitted:
                messages.success(
                    request,
                    f"Создан новый AI-лог #{queued_log.id}; результат не будет применён автоматически.",
                )
            else:
                messages.warning(request, "Повторный запуск уже находится в очереди.")
        except Exception as exc:
            messages.error(request, f"Не удалось перезапустить AI: {exc}")
        return self._response_post_save(request, obj)

    def _response_post_save(self, request, obj):
        """Редирект обратно на форму после сохранения."""
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
        """Проверить и применить результат AI к товару."""
        from .services.content_generator import ContentGenerator
        gen = ContentGenerator()
        applied = 0
        partial = 0
        partial_ids = []
        skipped = 0
        for log in queryset:
            if log.status not in (
                AIProcessingStatus.COMPLETED,
                AIProcessingStatus.MODERATION,
                AIProcessingStatus.APPROVED,
            ):
                skipped += 1
                continue
            if not log.product_id:
                skipped += 1
                continue
            try:
                gen.apply_log_to_product(
                    log,
                    user=request.user,
                    allow_approved=True,
                )
                if log.application_status == AIApplicationStatus.PARTIAL:
                    partial += 1
                    partial_ids.append(log.id)
                else:
                    applied += 1
            except Exception as e:
                messages.error(
                    request,
                    f"Лог #{log.id}: не удалось применить — {e}",
                )
        if applied:
            messages.success(
                request,
                f"Проверено и полностью применено к товарам: {applied}.",
            )
        if partial:
            visible_ids = ", ".join(f"#{log_id}" for log_id in partial_ids[:5])
            if len(partial_ids) > 5:
                visible_ids += ", …"
            messages.warning(
                request,
                f"Разрешённые поля применены, но заблокированные поля не перенесены: "
                f"{partial} ({visible_ids}). Записи остаются на модерации; отдельное "
                "предварительное одобрение не требуется.",
            )
        if skipped:
            messages.info(request, f"Пропущено логов с неподходящим статусом: {skipped}.")

    apply_to_product.short_description = "Проверено — применить к товару"

    def reject_results(self, request, queryset):
        rejected = 0
        skipped = 0
        for log in queryset.select_related("product"):
            try:
                reject_log(log, user=request.user)
                rejected += 1
            except ValueError:
                skipped += 1
        if rejected:
            messages.success(request, f"Отклонено результатов: {rejected}.")
        if skipped:
            messages.info(request, f"Пропущено логов с неподходящим статусом: {skipped}.")

    reject_results.short_description = "Отклонить результат"

    def rerun_ai_full(self, request, queryset):
        from .tasks import enqueue_product_ai_task

        product_ids = list(
            queryset.values_list("product_id", flat=True).distinct()
        )
        for product_id in product_ids:
            enqueue_product_ai_task(
                product_id=product_id,
                processing_type="full",
                auto_apply=False,
                force=True,
            )
        messages.success(
            request,
            f"Запущена AI обработка (full) для {len(product_ids)} товаров. "
            "Результаты появятся в логах; применить к товару — вручную после проверки.",
        )

    rerun_ai_full.short_description = (
        "Перезапустить AI (full) по товарам"
    )

    def rerun_ai_description_only(self, request, queryset):
        from .tasks import enqueue_product_ai_task

        product_ids = list(
            queryset.values_list("product_id", flat=True).distinct()
        )
        for product_id in product_ids:
            enqueue_product_ai_task(
                product_id=product_id,
                processing_type="description_only",
                auto_apply=False,
                force=True,
            )
        message = (
            "Запущена AI обработка (description_only) для "
            f"{len(product_ids)} товаров. Результаты в логах; применить — вручную после проверки."
        )
        messages.success(request, message)

    rerun_ai_description_only.short_description = (
        "Перезапустить AI (description_only) по товарам"
    )

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
        "log_status",
        "application_state",
        "priority",
        "human_reason",
        "assigned_to",
        "created_at",
        "resolved_at",
    )
    list_filter = (
        "priority",
        "created_at",
        "assigned_to",
        "reason",
        ("resolved_at", admin.EmptyFieldListFilter),
    )
    list_select_related = (
        "log_entry",
        "assigned_to",
        "log_entry__product",
    )
    date_hierarchy = "created_at"
    actions = (
        "set_priority_low",
        "set_priority_medium",
        "set_priority_high",
    )

    def log_link(self, obj):
        return format_html(
            '<a href="/admin/ai/aiprocessinglog/{}/change/" style="font-weight:700;">'
            "Проверить результат #{}</a>",
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

    @admin.display(description="Состояние AI", ordering="log_entry__status")
    def log_status(self, obj):
        title, _tone = get_workflow_title(obj.log_entry)
        return title

    @admin.display(description="Применение", ordering="log_entry__application_status")
    def application_state(self, obj):
        return APPLICATION_LABELS.get(
            obj.log_entry.application_status,
            obj.log_entry.get_application_status_display(),
        )

    @admin.display(description="Причина", ordering="reason")
    def human_reason(self, obj):
        from .services.moderation import MODERATION_REASON_LABELS

        return MODERATION_REASON_LABELS.get(obj.reason, obj.reason)

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
