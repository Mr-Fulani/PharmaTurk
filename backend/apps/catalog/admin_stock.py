"""Админка ночной сверки наличия и неактуальных товаров (docs/NIGHTLY_STOCK_CHECK.md, docs/STALE_PRODUCTS.md)."""
from datetime import timedelta

from django.conf import settings
from django.contrib import admin, messages
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models_stock import SOURCE_TITLES, ProductDeletionLog, StaleProductCandidate, StockCheckSourceState

CONFIRM_TEMPLATE = "admin/catalog/stale_products_confirm.html"


def source_title(parser_key: str) -> str:
    return SOURCE_TITLES.get(parser_key, parser_key)


def _mb(size) -> str:
    return f"{(size or 0) / 1024 / 1024:.1f} МБ"


@admin.register(StockCheckSourceState)
class StockCheckSourceStateAdmin(admin.ModelAdmin):
    """Где остановилась сверка каждого источника, итог ночи и пауза предохранителя."""

    list_display = ("source", "night", "checked", "catalog_size", "last_full_cycle_at", "pause")
    readonly_fields = (
        "parser_key", "cursor_pk", "night", "stats", "catalog_size", "last_full_cycle_at",
        "paused_at", "reported_night", "updated_at",
    )
    fields = readonly_fields[:6] + ("paused_reason",) + readonly_fields[6:]

    @admin.display(description="Источник", ordering="parser_key")
    def source(self, obj):
        return source_title(obj.parser_key)

    @admin.display(description="Проверено за ночь")
    def checked(self, obj):
        return (obj.stats or {}).get("checked", 0)

    @admin.display(description="Пауза")
    def pause(self, obj):
        return obj.paused_reason or "—"

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if not obj.paused_reason:
            obj.paused_at = None
        super().save_model(request, obj, form, change)


class OwnerActionsMixin:
    """Действия «скрыть / удалить / оставить / восстановить» — только суперпользователю.

    Обычный сотрудник с правом просмотра видит списки, но действий не получает:
    Django убирает их из меню и отклоняет POST с ними.
    """

    def has_owner_permission(self, request):
        return bool(request.user and request.user.is_active and request.user.is_superuser)


def _confirm_page(request, *, title, action, ids, intro, rows, excluded, refusal, totals, confirm_label):
    return TemplateResponse(request, CONFIRM_TEMPLATE, {
        **admin.site.each_context(request),
        "title": title,
        "action": action,
        "ids": ids,
        "intro": intro,
        "rows": rows,
        "excluded": excluded,
        "refusal": refusal,
        "totals": totals,
        "confirm_label": confirm_label,
    })


@admin.register(StaleProductCandidate)
class StaleProductCandidateAdmin(OwnerActionsMixin, admin.ModelAdmin):
    """Товары, которых больше нет у продавца. Ничего не удаляется автоматически.

    Шаг 1 — «Скрыть с сайта» (обратимо), шаг 2 — «Удалить окончательно» через
    STALE_PRODUCT_DELETE_AFTER_HIDDEN_DAYS дней. Каждый шаг — со страницей подтверждения.
    """

    list_display = (
        "product_link", "source", "status", "gone_since", "protection", "files_to_free_column", "next_step", "source_link",
    )
    list_filter = ("status", "parser_key")
    search_fields = ("product__name", "source_url")
    list_select_related = ("product",)
    list_per_page = 50
    actions = ("hide_selected", "delete_selected_forever", "keep_selected")
    readonly_fields = (
        "product", "parser_key", "source_url", "reason", "status", "first_seen_at", "last_gone_at",
        "gone_checks", "hidden_at", "status_changed_by", "files_total", "files_to_free", "bytes_to_free",
        "media_stats_at", "updated_at",
    )

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)  # обычное удаление админки — без копий и проверок
        return actions

    @admin.display(description="Товар", ordering="product__name")
    def product_link(self, obj):
        url = reverse("admin:catalog_product_change", args=[obj.product_id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)

    @admin.display(description="Источник", ordering="parser_key")
    def source(self, obj):
        return source_title(obj.parser_key)

    @admin.display(description="Нет у продавца", ordering="first_seen_at")
    def gone_since(self, obj):
        days = (timezone.now() - obj.first_seen_at).days
        return f"{days} дн. (с {timezone.localtime(obj.first_seen_at):%d.%m})"

    @admin.display(description="Защита (только скрыть)")
    def protection(self, obj):
        from .services.stale_products import protection_reasons

        return ", ".join(protection_reasons([obj.product]).get(obj.product_id, [])) or "—"

    @admin.display(description="Освободится")
    def files_to_free_column(self, obj):
        if obj.media_stats_at is None:
            return "посчитается ночью"
        return f"{obj.files_to_free} из {obj.files_total} файлов, {_mb(obj.bytes_to_free)}"

    @admin.display(description="Что дальше")
    def next_step(self, obj):
        from .services.stale_products import delete_after_hidden_days, min_gone_days

        now = timezone.now()
        if obj.status == StaleProductCandidate.Status.CANDIDATE:
            ready = obj.first_seen_at + timedelta(days=min_gone_days())
            return "можно скрыть" if ready <= now else f"скрыть можно с {timezone.localtime(ready):%d.%m}"
        if obj.status == StaleProductCandidate.Status.HIDDEN and obj.hidden_at:
            ready = obj.hidden_at + timedelta(days=delete_after_hidden_days())
            return "можно удалить" if ready <= now else f"удалить можно с {timezone.localtime(ready):%d.%m}"
        if obj.status == StaleProductCandidate.Status.RETURNED:
            return "вернуть на сайт: «Оставить, не удалять»"
        return "—"

    @admin.display(description="У продавца")
    def source_link(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">открыть</a>', obj.source_url)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @staticmethod
    def _rows(plan):
        return [
            {
                "name": candidate.product.name,
                "source": source_title(candidate.parser_key),
                "info": (
                    f"нет у продавца {(timezone.now() - candidate.first_seen_at).days} дн.; "
                    + (
                        f"{candidate.files_to_free} файлов, {_mb(candidate.bytes_to_free)}"
                        if candidate.media_stats_at else "файлы ещё не посчитаны"
                    )
                ),
            }
            for candidate in plan.eligible
        ]

    @staticmethod
    def _excluded(plan):
        return [{"name": candidate.product.name, "reason": reason} for candidate, reason in plan.excluded]

    @admin.action(description="Скрыть с сайта (обратимо)", permissions=["owner"])
    def hide_selected(self, request, queryset):
        from .services.stale_products import StaleProductsRefused, hide_candidates, plan_action

        queryset = queryset.select_related("product")
        if request.POST.get("confirm") == "yes":
            try:
                plan = hide_candidates(queryset.values_list("pk", flat=True), request.user)
            except StaleProductsRefused as exc:
                self.message_user(request, str(exc), messages.ERROR)
                return None
            self.message_user(
                request,
                f"Скрыто с сайта: {len(plan.eligible)}. Не тронуто: {len(plan.excluded)}. "
                "Вернуть — «Оставить, не удалять».",
                messages.SUCCESS,
            )
            return None
        plan = plan_action(queryset, "hide")
        return _confirm_page(
            request,
            title="Скрыть с сайта",
            action="hide_selected",
            ids=[candidate.pk for candidate in queryset],
            intro=[
                "Товары пропадут из каталога, поиска и карты сайта. Ничего не удаляется — "
                "вернуть можно действием «Оставить, не удалять».",
                "Окончательно удалить можно будет через "
                f"{getattr(settings, 'STALE_PRODUCT_DELETE_AFTER_HIDDEN_DAYS', 14)} дней после скрытия.",
            ],
            rows=self._rows(plan),
            excluded=self._excluded(plan),
            refusal=plan.refusal,
            totals=f"Будет скрыто: {len(plan.eligible)}.",
            confirm_label=f"Да, скрыть {len(plan.eligible)}",
        )

    @admin.action(description="Удалить окончательно вместе с файлами", permissions=["owner"])
    def delete_selected_forever(self, request, queryset):
        from .services.stale_products import plan_action
        from .tasks import delete_stale_products_task

        queryset = queryset.select_related("product")
        plan = plan_action(queryset, "delete")
        if request.POST.get("confirm") == "yes":
            if plan.refusal or not plan.eligible:
                self.message_user(request, plan.refusal or "Нечего удалять.", messages.ERROR)
                return None
            delete_stale_products_task.delay([candidate.pk for candidate in plan.eligible], request.user.pk)
            self.message_user(
                request,
                f"Удаление {len(plan.eligible)} товаров запущено в фоне. Перед удалением каждый ещё раз "
                "проверяется у продавца. Итог придёт в Telegram и появится в «Журнал удалений товаров».",
                messages.SUCCESS,
            )
            return None
        keep = getattr(settings, "MEDIA_BACKUP_KEEP_DELETED_DAYS", 30)
        totals = f"Будет удалено товаров: {len(plan.eligible)}, файлов ≈ {plan.files_to_free}, освободится ≈ {_mb(plan.bytes_to_free)}."
        if plan.without_stats:
            totals += f" У {plan.without_stats} товаров файлы ещё не посчитаны (считаются ночью)."
        return _confirm_page(
            request,
            title="Удалить окончательно",
            action="delete_selected_forever",
            ids=[candidate.pk for candidate in queryset],
            intro=[
                "Прямо перед удалением каждый товар ещё раз проверяется у продавца: если он снова "
                "есть — не удаляется.",
                "Строки базы сохраняются в «Журнал удалений товаров», файлы — в резервную копию на "
                f"{keep} дней. Из журнала товар можно восстановить.",
                "Из облака удаляются только файлы, на которые больше никто не ссылается; общие с "
                "другими товарами остаются.",
            ],
            rows=self._rows(plan),
            excluded=self._excluded(plan),
            refusal=plan.refusal,
            totals=totals,
            confirm_label=f"Да, удалить {len(plan.eligible)} навсегда",
        )

    @admin.action(description="Оставить, не удалять (вернуть на сайт)", permissions=["owner"])
    def keep_selected(self, request, queryset):
        from .services.stale_products import keep_candidates

        kept = keep_candidates(queryset.values_list("pk", flat=True), request.user)
        self.message_user(request, f"Оставлено: {kept}. Скрытые возвращены на сайт.", messages.SUCCESS)


@admin.register(ProductDeletionLog)
class ProductDeletionLogAdmin(OwnerActionsMixin, admin.ModelAdmin):
    """Что удалено, кем и когда; восстановление из копии."""

    list_display = ("created_at", "product", "source", "files_deleted", "freed", "status", "deleted_by")
    list_filter = ("status", "parser_key")
    search_fields = ("product_name", "product_id")
    actions = ("restore_selected",)
    exclude = ("rows_backup",)
    readonly_fields = (
        "created_at", "deleted_by", "product_id", "product_name", "product_type", "parser_key",
        "source_url", "first_seen_at", "hidden_at", "status", "objects_count", "files", "files_deleted",
        "bytes_freed", "note", "restored_at", "restored_by",
    )

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    @admin.display(description="Товар", ordering="product_name")
    def product(self, obj):
        return f"{obj.product_name} (ID {obj.product_id})"

    @admin.display(description="Источник", ordering="parser_key")
    def source(self, obj):
        return source_title(obj.parser_key)

    @admin.display(description="Освобождено", ordering="bytes_freed")
    def freed(self, obj):
        return _mb(obj.bytes_freed)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Восстановить товар и файлы", permissions=["owner"])
    def restore_selected(self, request, queryset):
        from .services.stale_products import StaleProductsRefused, restore_deletion

        logs = list(queryset[:20])
        keep = getattr(settings, "MEDIA_BACKUP_KEEP_DELETED_DAYS", 30)
        if request.POST.get("confirm") == "yes":
            for log in logs:
                try:
                    failed = restore_deletion(log, request.user)
                except StaleProductsRefused as exc:
                    self.message_user(request, f"{log.product_name}: {exc}", messages.ERROR)
                    continue
                if failed:
                    self.message_user(
                        request, f"{log.product_name}: восстановлен, но {len(failed)} файлов в копии уже нет.",
                        messages.WARNING,
                    )
                else:
                    self.message_user(request, f"{log.product_name}: восстановлен (скрыт с сайта).", messages.SUCCESS)
            return None
        old = timezone.now() - timedelta(days=keep)
        return _confirm_page(
            request,
            title="Восстановить удалённые товары",
            action="restore_selected",
            ids=[log.pk for log in logs],
            intro=[
                "Строки базы вернутся из журнала, файлы — из резервной копии. Товар вернётся скрытым "
                "с сайта; показать его — «Неактуальные товары» → «Оставить, не удалять».",
                f"Файлы хранятся в копии {keep} дней: у удалённых раньше часть картинок может не вернуться.",
                "За раз — не больше 20 товаров.",
            ],
            rows=[
                {
                    "name": log.product_name,
                    "source": source_title(log.parser_key),
                    "info": f"удалён {timezone.localtime(log.created_at):%d.%m.%Y}, файлов {log.files_deleted}"
                    + (" — копия файлов могла истечь" if log.created_at < old else ""),
                }
                for log in logs
                if log.status == ProductDeletionLog.Status.DELETED
            ],
            excluded=[
                {"name": log.product_name, "reason": "уже восстановлен"}
                for log in logs
                if log.status != ProductDeletionLog.Status.DELETED
            ],
            refusal="",
            totals="",
            confirm_label="Да, восстановить",
        )
