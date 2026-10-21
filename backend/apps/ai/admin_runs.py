"""Админка «AI-прогоны»: запуск массовой AI-обработки и обслуживания кнопками.

Логика запусков — services/ai_runs.py; здесь только формы, страницы и кнопки.
"""

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import AutocompleteSelect
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.dateparse import parse_datetime
from django.utils.html import format_html

from apps.catalog.models import Category, Product

from .models import AIRun
from .services import ai_runs
from .services.medicine_memory import PARAGRAPH_NAMESPACE
from .services.medicine_paragraph_batch import MAX_DEFECT, PART_SIZE

STATUS_COLORS = {
    AIRun.Status.DRAFT: ("#475569", "#e2e8f0"),
    AIRun.Status.RUNNING: ("#1d4ed8", "#dbeafe"),
    AIRun.Status.STOPPED: ("#92400e", "#fef3c7"),
    AIRun.Status.FINISHED: ("#166534", "#dcfce7"),
    AIRun.Status.FAILED: ("#991b1b", "#fee2e2"),
}


class AIRunLaunchForm(forms.Form):
    product_type = forms.ChoiceField(
        label="Тип товара",
        choices=[("", "— выберите —"), *Product.PRODUCT_TYPE_CHOICES],
        help_text="За один прогон обрабатывается один тип товаров.",
    )
    category = forms.ModelChoiceField(
        label="Категория (необязательно)",
        queryset=Category.objects.all(),
        required=False,
        help_text="Если выбрать, войдут только товары этой категории и её подкатегорий.",
    )
    limit = forms.IntegerField(
        label="Сколько товаров обработать",
        min_value=1,
        max_value=ai_runs.MAX_PRODUCTS_PER_RUN,
        initial=20,
        help_text=(
            f"Не больше {ai_runs.MAX_PRODUCTS_PER_RUN} за раз. Начинайте с 10–20, "
            "проверьте результат, потом увеличивайте."
        ),
    )
    missing_description = forms.BooleanField(
        label="Только товары без описания", required=False
    )
    auto_apply = forms.BooleanField(
        label="Сразу применять результат к товарам",
        required=False,
        help_text=(
            "Без галочки AI только готовит тексты — вы проверяете и применяете их сами "
            "в разделе «Логи AI обработки». С галочкой тексты сразу появятся на сайте "
            "(сомнительные всё равно уйдут на модерацию)."
        ),
    )
    cost_confirmed = forms.BooleanField(label="", required=False)

    def __init__(self, *args, admin_site, **kwargs):
        super().__init__(*args, **kwargs)
        category = self.fields["category"]
        category.widget = AutocompleteSelect(AIRun._meta.get_field("category"), admin_site)
        category.widget.choices = category.choices


class MaintenanceForm(forms.Form):
    limit = forms.IntegerField(
        label="Сколько записей за раз",
        min_value=1,
        max_value=ai_runs.MAINTENANCE_MAX_LIMIT,
        initial=50,
    )
    product_type = forms.ChoiceField(
        label="Тип товара",
        choices=[("", "Все типы"), *Product.PRODUCT_TYPE_CHOICES],
        required=False,
    )


class ParagraphRunForm(forms.Form):
    part_size = forms.IntegerField(
        label="Абзацев в части",
        min_value=ai_runs.PARAGRAPH_MIN_PART,
        max_value=ai_runs.PARAGRAPH_MAX_PART,
        initial=PART_SIZE,
        help_text=(
            f"Часть из {PART_SIZE} абзацев стоит ≈ $0.16 и готовится в OpenAI до 24 часов. "
            "Для первой пробы поставьте 200–500."
        ),
    )
    max_defect = forms.IntegerField(
        label="Порог брака, %",
        min_value=1,
        max_value=100,
        initial=round(MAX_DEFECT * 100),
        help_text="Если в готовой части не прошло проверку больше этой доли абзацев, прогон остановится сам.",
    )
    wait_each_part = forms.BooleanField(
        label="После каждой части ждать моей кнопки «Следующая часть»",
        required=False,
        help_text="Без галочки следующая часть отправляется сама, если брак не выше порога.",
    )


PARAGRAPH_INFO = {
    "title": "Перевести абзацы инструкций лекарств (Batch API)",
    "text": (
        "Переводит на русский и английский абзацы инструкций лекарств (показания, противопоказания, "
        "применение, побочные действия, хранение), которых ещё нет в памяти переводов. Работает через "
        "OpenAI Batch API: вдвое дешевле обычной обработки, но каждая часть готовится до 24 часов. "
        "Абзацы уходят частями; готовую часть система забирает сама, проверяет каждый перевод теми же "
        "правилами, что обычная обработка, и записывает принятые в память. Товары на сайте сами не "
        "меняются: обработка лекарств потом берёт переводы из памяти бесплатно."
    ),
    "submit_label": "🧮 Посчитать",
    "intro": (
        "Сначала ничего не отправляется: система посчитает, сколько абзацев не переведено, сколько "
        "это частей и примерно сколько стоит. Отправка — только после кнопки «▶ Запустить»."
    ),
}


MAINTENANCE_INFO = {
    AIRun.Kind.RETRY_TITLES: {
        "title": "Перегенерировать отклонённые названия БАДов",
        "text": (
            "AI заново придумает название для БАДов, у которых проверка отклонила название "
            "(потерян бренд/фасовка или осталось по-турецки). Один короткий запрос на товар, "
            "≈ $0.0002. Товары на сайте не меняются: новые названия попадают в модерацию. "
            "Чтобы применить их, после этой операции нажмите «Закрыть решённые записи модерации»."
        ),
        "with_type": False,
    },
    AIRun.Kind.CLOSE_MODERATION: {
        "title": "Закрыть решённые записи модерации",
        "text": (
            "Находит записи на модерации, у которых больше нет причин для проверки (например, "
            "после исправления названий), применяет к товарам разрешённые поля и закрывает "
            "записи — так же, как кнопка «Проверено — применить к товару». AI не вызывается, "
            "денег не тратит."
        ),
        "with_type": True,
    },
}


class AIRunLogFilter(admin.SimpleListFilter):
    """Фильтр «Логи AI обработки» по прогону (ссылка «Логи прогона»)."""

    title = "AI-прогон"
    parameter_name = "ai_run"

    def lookups(self, request, model_admin):
        runs = AIRun.objects.filter(kind=AIRun.Kind.PRODUCTS).order_by("-id")[:20]
        return [(str(run.pk), f"#{run.pk} {run.get_product_type_display()}") for run in runs]

    def queryset(self, request, queryset):
        if self.value() and self.value().isdigit():
            return queryset.filter(ai_runs__id=int(self.value()))
        return queryset


@admin.register(AIRun)
class AIRunAdmin(admin.ModelAdmin):
    change_list_template = "admin/ai/airun/change_list.html"
    list_display = (
        "run_link",
        "kind",
        "status_badge",
        "product_type",
        "progress",
        "moderation_count",
        "failed_count",
        "cost_display",
        "created_by",
        "created_at",
    )
    list_display_links = None
    list_filter = ("kind", "status", "product_type")
    list_select_related = ("created_by",)

    # --- список

    @admin.display(description="Прогон", ordering="id")
    def run_link(self, obj):
        return format_html(
            '<a href="{}"><b>#{}</b> открыть</a>', reverse("admin:ai_airun_change", args=[obj.pk]), obj.pk
        )

    @admin.display(description="Состояние", ordering="status")
    def status_badge(self, obj):
        fg, bg = STATUS_COLORS.get(obj.status, ("#111", "#eee"))
        return format_html(
            '<span style="color:{};background:{};padding:2px 8px;border-radius:10px;font-weight:600">{}</span>',
            fg, bg, obj.get_status_display(),
        )

    @admin.display(description="Готово / отобрано")
    def progress(self, obj):
        return f"{obj.done_count} / {obj.selected_count}"

    @admin.display(description="Потрачено", ordering="cost_usd")
    def cost_display(self, obj):
        return f"${obj.cost_usd:.4f}"

    # --- права: прогон меняется только кнопками

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Часть в OpenAI без прогона никто не заберёт — деньги за неё пропадут.
        if obj is not None and (obj.status == AIRun.Status.RUNNING or ai_runs.part_in_flight(obj)):
            return False
        return super().has_delete_permission(request, obj)

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {"title": "AI-прогоны", **(extra_context or {})})

    def _require_add(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied

    # --- URL

    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [
            path(
                "maintenance/<str:kind>/",
                wrap(self.maintenance_view),
                name="ai_airun_maintenance",
            ),
            path("<int:run_id>/status/", wrap(self.status_view), name="ai_airun_status"),
            path("<int:run_id>/stop/", wrap(self.stop_view), name="ai_airun_stop"),
            path("<int:run_id>/resume/", wrap(self.resume_view), name="ai_airun_resume"),
            path("<int:run_id>/confirm/", wrap(self.confirm_view), name="ai_airun_confirm"),
            path("paragraphs/", wrap(self.paragraphs_view), name="ai_airun_paragraphs"),
            path("<int:run_id>/next-part/", wrap(self.next_part_view), name="ai_airun_next_part"),
            path("<int:run_id>/retry-part/", wrap(self.retry_part_view), name="ai_airun_retry_part"),
        ] + super().get_urls()

    def _context(self, request, **extra):
        return {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
            **extra,
        }

    def _get_run(self, request, run_id):
        run = AIRun.objects.filter(pk=run_id).first()
        if run is None:
            raise Http404("Прогон не найден")
        if not self.has_view_permission(request, run):
            raise PermissionDenied
        return run

    # --- форма запуска (вместо стандартного «Добавить»)

    def add_view(self, request, form_url="", extra_context=None):
        self._require_add(request)
        preview = None
        if request.method == "POST":
            form = AIRunLaunchForm(request.POST, admin_site=self.admin_site)
            action = request.POST.get("action")
            if form.is_valid():
                data = form.cleaned_data
                params = {
                    "product_type": data["product_type"],
                    "category": data["category"],
                    "limit": data["limit"],
                    "missing_description": data["missing_description"],
                }
                try:
                    if action == "start":
                        run = ai_runs.start_products_run(
                            user=request.user,
                            auto_apply=data["auto_apply"],
                            cost_confirmed=data["cost_confirmed"],
                            **params,
                        )
                        messages.success(request, f"Прогон #{run.pk} запущен. Страница обновляется сама.")
                        return HttpResponseRedirect(reverse("admin:ai_airun_change", args=[run.pk]))
                    preview = ai_runs.preview_products_run(**params)
                except ai_runs.RunError as exc:
                    messages.error(request, str(exc))
                    if action == "start":
                        try:
                            preview = ai_runs.preview_products_run(**params)
                        except ai_runs.RunError:
                            preview = None
        else:
            form = AIRunLaunchForm(admin_site=self.admin_site)
        context = self._context(
            request,
            title="Новый AI-прогон",
            form=form,
            preview=preview,
            cost_warning=ai_runs.COST_WARNING_USD,
            cost_over=bool(preview and preview["estimate"] > ai_runs.COST_WARNING_USD),
            running=AIRun.objects.filter(status=AIRun.Status.RUNNING).order_by("-id"),
            batch_size=ai_runs.BATCH_SIZE,
            max_error_percent=int(ai_runs.MAX_ERROR_SHARE * 100),
            media=self.media + form.media,
        )
        return TemplateResponse(request, "admin/ai/airun/launch.html", context)

    # --- страница прогона (вместо стандартной формы изменения)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        run = self._get_run(request, object_id)
        if run.kind == AIRun.Kind.PRODUCTS and run.status != AIRun.Status.DRAFT:
            ai_runs.refresh_counters(run, save=True)
        context = self._context(
            request,
            title=f"AI-прогон #{run.pk}",
            run=run,
            original=run,
            state=self._state(run),
            can_act=self.has_add_permission(request),
            logs_url=f"{reverse('admin:ai_aiprocessinglog_changelist')}?ai_run={run.pk}",
            moderation_url=reverse("admin:ai_aimoderationqueue_changelist"),
            memory_url=f"{reverse('admin:ai_aitranslationmemory_changelist')}?namespace={PARAGRAPH_NAMESPACE}",
            info=PARAGRAPH_INFO if run.kind == AIRun.Kind.MEDICINE_PARAGRAPHS else MAINTENANCE_INFO.get(run.kind),
            parts=self._parts(run),
        )
        return TemplateResponse(request, "admin/ai/airun/run_detail.html", context)

    def _parts(self, run):
        """Строки таблицы частей перевода абзацев, новые сверху."""
        if run.kind != AIRun.Kind.MEDICINE_PARAGRAPHS:
            return []
        rows = []
        for part in reversed(run.report.get("parts") or []):
            state = ai_runs.PART_STATES.get(part["state"], part["state"])
            if part["state"] == "collected" and part.get("openai_status") != "completed":
                state = f"забрана частично ({ai_runs.PART_STATES.get(part['openai_status'], part['openai_status'])})"
            collected = part["state"] == "collected"
            rows.append({
                **part,
                "state_label": state,
                "collected": collected,
                "defect_percent": f"{part['defect']:.1%}" if collected else "",
                "reasons_text": ai_runs.reason_text(part.get("reasons") or {}) if collected else "",
                "cost": f"{part['cost_usd']:.4f}" if collected else "",
                "estimate": f"{part['estimate_usd']:.4f}",
                "per_1000": f"{part['per_1000']:.4f}" if collected else "",
                "sent": parse_datetime(part["sent_at"]),
                "collected_at_dt": parse_datetime(part["collected_at"]) if collected else None,
            })
        return rows

    def _state(self, run):
        """Данные для страницы и для автообновления (status/)."""
        processed = run.done_count + run.moderation_count + run.failed_count + run.skipped_count
        total = run.selected_count or 0
        stalled = ai_runs.is_stalled(run)
        can_resume = run.kind == AIRun.Kind.PRODUCTS and (
            stalled
            or (
                run.status in (AIRun.Status.STOPPED, AIRun.Status.FAILED)
                and bool(run.pending_product_ids or run.current_batch_log_ids)
            )
        )
        return {
            "status": run.status,
            "status_label": run.get_status_display(),
            "selected": total,
            "queued": run.queued_count,
            "in_progress": ai_runs.in_progress_count(run),
            "done": run.done_count,
            "moderation": run.moderation_count,
            "failed": run.failed_count,
            "cancelled": run.cancelled_count,
            "skipped": run.skipped_count,
            "remaining": len(run.pending_product_ids or []),
            "processed": processed,
            "percent": min(100, round(processed * 100 / total)) if total else 0,
            "cost": f"{run.cost_usd:.4f}",
            "estimate": f"{run.estimated_cost_usd:.4f}",
            "message": run.message,
            "stalled": stalled,
            "can_stop": run.kind == AIRun.Kind.PRODUCTS and run.status == AIRun.Status.RUNNING,
            "can_resume": can_resume,
            "preview_ready": bool(run.report.get("preview")),
            "live": run.status == AIRun.Status.RUNNING
            or (run.status == AIRun.Status.DRAFT and not run.report.get("preview"))
            or (run.status == AIRun.Status.STOPPED and ai_runs.in_progress_count(run) > 0),
            "parts_key": "",
            **(ai_runs.paragraph_state(run) if run.kind == AIRun.Kind.MEDICINE_PARAGRAPHS else {}),
        }

    def status_view(self, request, run_id):
        run = self._get_run(request, run_id)
        if run.kind == AIRun.Kind.PRODUCTS and run.status != AIRun.Status.DRAFT:
            ai_runs.refresh_counters(run, save=True)
        return JsonResponse(self._state(run))

    def _post_action(self, request, run_id, action, success):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        self._require_add(request)
        run = self._get_run(request, run_id)
        try:
            action(run)
            messages.success(request, success)
        except ai_runs.RunError as exc:
            messages.error(request, str(exc))
        return HttpResponseRedirect(reverse("admin:ai_airun_change", args=[run.pk]))

    def stop_view(self, request, run_id):
        if self._get_run(request, run_id).kind == AIRun.Kind.MEDICINE_PARAGRAPHS:
            return self._post_action(
                request, run_id, ai_runs.stop_paragraph_run,
                "Новые части отправляться не будут. Если часть уже в OpenAI, её заберём, когда она будет "
                "готова, и прогон остановится.",
            )
        return self._post_action(
            request, run_id, ai_runs.stop_run,
            "Прогон остановлен. Товары, которые уже обрабатывались, доработают; "
            "остальные отменены и войдут в следующий запуск.",
        )

    def resume_view(self, request, run_id):
        return self._post_action(request, run_id, ai_runs.resume_run, "Прогон продолжен.")

    def confirm_view(self, request, run_id):
        if self._get_run(request, run_id).kind == AIRun.Kind.MEDICINE_PARAGRAPHS:
            return self._post_action(
                request, run_id, ai_runs.start_paragraph_run,
                "Прогон запущен: первая часть уйдёт в OpenAI в течение минуты. Страница обновляется сама.",
            )
        return self._post_action(
            request, run_id, ai_runs.confirm_maintenance, "Операция запущена. Страница обновляется сама."
        )

    def next_part_view(self, request, run_id):
        return self._post_action(
            request, run_id, ai_runs.next_paragraph_part, "Следующая часть уйдёт в OpenAI в течение минуты."
        )

    def retry_part_view(self, request, run_id):
        return self._post_action(
            request, run_id, ai_runs.retry_paragraph_part,
            "Отклонённые абзацы уйдут в OpenAI повторной частью в течение минуты.",
        )

    # --- перевод абзацев инструкций (Batch API)

    def paragraphs_view(self, request):
        self._require_add(request)
        if request.method == "POST":
            form = ParagraphRunForm(request.POST)
            if form.is_valid():
                data = form.cleaned_data
                try:
                    run = ai_runs.create_paragraph_preview(
                        user=request.user,
                        part_size=data["part_size"],
                        max_defect=data["max_defect"] / 100,
                        wait_each_part=data["wait_each_part"],
                    )
                except ai_runs.RunError as exc:
                    messages.error(request, str(exc))
                else:
                    return HttpResponseRedirect(reverse("admin:ai_airun_change", args=[run.pk]))
        else:
            form = ParagraphRunForm()
        context = self._context(request, title=PARAGRAPH_INFO["title"], info=PARAGRAPH_INFO, form=form)
        return TemplateResponse(request, "admin/ai/airun/maintenance.html", context)

    # --- обслуживающие операции

    def maintenance_view(self, request, kind):
        self._require_add(request)
        if kind not in ai_runs.MAINTENANCE_KINDS:
            raise Http404("Неизвестная операция")
        info = MAINTENANCE_INFO[kind]
        if request.method == "POST":
            form = MaintenanceForm(request.POST)
            if form.is_valid():
                try:
                    run = ai_runs.create_maintenance_preview(
                        kind=kind,
                        user=request.user,
                        product_type=form.cleaned_data["product_type"] if info["with_type"] else "",
                        limit=form.cleaned_data["limit"],
                    )
                except ai_runs.RunError as exc:
                    messages.error(request, str(exc))
                else:
                    return HttpResponseRedirect(reverse("admin:ai_airun_change", args=[run.pk]))
        else:
            form = MaintenanceForm()
        if not info["with_type"]:
            del form.fields["product_type"]
        context = self._context(request, title=info["title"], info=info, form=form)
        return TemplateResponse(request, "admin/ai/airun/maintenance.html", context)
