"""Админка проверки лекарств: окно «Проверить сейчас», поиск по названию/штрихкоду, списки."""

import re

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.views.decorators.http import require_http_methods

from apps.catalog.models import MedicineProduct
from apps.catalog.product_search import filter_by_search

from . import actions
from .models import DrugReferenceEntry, DrugReferenceLoad
from .service import check_barcode, check_medicine, quick_check
from .sources import file_sources

LOOKUP_LIMIT = 25


def _require_medicine_view(request):
    if not request.user.has_perm("catalog.view_medicineproduct"):
        raise PermissionDenied


def _require_medicine_change(request):
    if not request.user.has_perm("catalog.change_medicineproduct"):
        raise PermissionDenied


def _change_url(medicine_id):
    return reverse("admin:catalog_medicineproduct_change", args=[medicine_id])


def _loads():
    """Последняя удачная загрузка каждого файла — показывается под результатом."""
    rows = []
    for source in file_sources():
        rows.append((source.title, source.last_loaded()))
    return rows


@admin.register(DrugReferenceEntry)
class DrugReferenceEntryAdmin(admin.ModelAdmin):
    change_list_template = "admin/drug_check/entry_change_list.html"
    list_display = ("barcode", "name", "source", "status", "status_date", "reason", "price", "price_date", "firm")
    list_filter = ("source", "status")
    search_fields = ("=barcode", "name")
    ordering = ("source", "name")
    list_per_page = 100

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [
            path("check/<int:medicine_id>/", self.admin_site.admin_view(self.check_view), name="drug_check_medicine"),
            path("lookup/", self.admin_site.admin_view(self.lookup_view), name="drug_check_lookup"),
            path(
                "check/<int:medicine_id>/price/",
                self.admin_site.admin_view(require_http_methods(["GET", "POST"])(self.price_view)),
                name="drug_check_price",
            ),
            path(
                "check/<int:medicine_id>/availability/",
                self.admin_site.admin_view(require_http_methods(["GET", "POST"])(self.availability_view)),
                name="drug_check_availability",
            ),
            *super().get_urls(),
        ]

    def _render(self, request, template, context):
        return TemplateResponse(
            request,
            template,
            {**self.admin_site.each_context(request), "opts": self.model._meta, "loads": _loads(), **context},
        )

    def check_view(self, request, medicine_id):
        _require_medicine_view(request)
        medicine = get_object_or_404(MedicineProduct.objects.select_related("base_product"), pk=medicine_id)
        report = check_medicine(medicine)
        context = {"title": f"Проверка: {medicine.name}", "report": report}
        if request.user.has_perm("catalog.change_medicineproduct"):
            context["price_action"] = actions.price_action(report)
            context["availability_action"] = actions.availability_action(report)
        return self._render(request, "admin/drug_check/check.html", context)

    def _log(self, request, medicine, message):
        """Журнал админки (LogEntry) карточки лекарства: кто, когда, было → стало, источник."""
        self.admin_site._registry[MedicineProduct].log_change(request, medicine, message)

    def price_view(self, request, medicine_id):
        """GET — подтверждение «было → станет», POST — запись цены. Без POST ничего не меняется."""
        _require_medicine_change(request)
        medicine = get_object_or_404(MedicineProduct, pk=medicine_id)
        offer = actions.read_offer(request.POST.get("token") or request.GET.get("token"), medicine.pk)
        if offer is None:
            messages.error(request, "Проверка устарела или ссылка неверна — нажмите «Проверить сейчас» ещё раз.")
            return redirect(_change_url(medicine.pk))
        if medicine.is_hospital:
            messages.error(request, "Больничный препарат («цена по запросу») — цену не принимаем.")
            return redirect(_change_url(medicine.pk))
        if request.method == "POST":
            applied = actions.apply_price(medicine.pk, offer)
            if applied is None:
                messages.info(request, "Цена уже такая — ничего не изменено.")
                return redirect(_change_url(medicine.pk))
            medicine, old_price, old_currency = applied
            was = actions.money(old_price, old_currency or "TRY")
            message = (
                f"Проверка лекарств: цена {was} → {actions.money(offer['price'], offer['currency'])} "
                f"(принята цена IlacFiyati{', от ' + offer['price_date'].strftime('%d.%m.%Y') if offer['price_date'] else ''}"
                f"; {offer['url'] or 'адрес не указан'})"
            )
            self._log(request, medicine, message)
            messages.success(request, message.replace("Проверка лекарств: ", "Сохранено: "))
            return redirect(_change_url(medicine.pk))
        return self._render(
            request,
            "admin/drug_check/confirm.html",
            {
                "title": f"Принять цену IlacFiyati: {medicine.name}",
                "medicine": medicine,
                "rows": [("Цена", actions.money(medicine.price, medicine.currency or "TRY"),
                          actions.money(offer["price"], offer["currency"]))],
                "fields": {"token": offer["token"]},
                "submit": f"Принять цену {offer['label']}",
                "note": "Цена в рублях и других валютах пересчитается автоматически. Прежняя цена "
                        "не станет «старой ценой со скидкой».",
            },
        )

    def availability_view(self, request, medicine_id):
        """GET — подтверждение, POST — «в наличии» / «нет в наличии» вручную."""
        _require_medicine_change(request)
        medicine = get_object_or_404(MedicineProduct, pk=medicine_id)
        value = request.POST.get("to") if request.method == "POST" else request.GET.get("to")
        if value not in ("0", "1"):
            messages.error(request, "Не указано, что отметить.")
            return redirect(_change_url(medicine.pk))
        to = value == "1"
        hint = "; ".join(r.short for r in quick_check(medicine).results if r.short)
        if request.method == "POST":
            if actions.apply_availability(medicine.pk, to) is None:
                messages.info(request, f"Уже «{actions.availability_label(to)}» — ничего не изменено.")
                return redirect(_change_url(medicine.pk))
            message = (
                f"Проверка лекарств: наличие «{actions.availability_label(not to)}» → "
                f"«{actions.availability_label(to)}» (вручную; списки: {hint or 'нет данных'})"
            )
            self._log(request, medicine, message)
            messages.success(request, message.replace("Проверка лекарств: ", "Сохранено: "))
            return redirect(_change_url(medicine.pk))
        return self._render(
            request,
            "admin/drug_check/confirm.html",
            {
                "title": f"Наличие вручную: {medicine.name}",
                "medicine": medicine,
                "rows": [("Наличие на сайте", actions.availability_label(medicine.is_available),
                          actions.availability_label(to))],
                "fields": {"to": value},
                "submit": "Отметить: " + actions.availability_label(to),
                "note": f"Что говорят списки (без запроса наружу): {hint or 'нет данных'}. "
                        "Парсер IlacFiyati при следующем обходе может снова поставить наличие по источнику.",
            },
        )

    def lookup_view(self, request):
        _require_medicine_view(request)
        query = (request.GET.get("q") or "").strip()[:200]
        context = {"title": "Проверить по названию или штрихкоду", "query": query}
        if re.fullmatch(r"\d{8,14}", query):
            context["report"] = check_barcode(query)
            context["ours"] = list(MedicineProduct.objects.filter(barcode=query).order_by("-is_active")[:LOOKUP_LIMIT])
        elif len(query) >= 3:
            ours = filter_by_search(MedicineProduct.objects.all(), query, prefix="base_product__")
            context["ours"] = list(ours.order_by("-is_active", "name")[:LOOKUP_LIMIT])
            context["entries"] = list(
                DrugReferenceEntry.objects.filter(name__icontains=query).order_by("name", "source")[:LOOKUP_LIMIT * 2]
            )
        return self._render(request, "admin/drug_check/lookup.html", context)


@admin.register(DrugReferenceLoad)
class DrugReferenceLoadAdmin(admin.ModelAdmin):
    list_display = ("created_at", "source", "result", "file_name", "file_date", "rows", "message")
    list_filter = ("source", "result")
    readonly_fields = ("source", "file_name", "file_url", "file_date", "result", "rows", "message", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
