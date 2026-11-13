"""Админка проверки лекарств: окно «Проверить сейчас», поиск по названию/штрихкоду, списки."""

import re

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path

from apps.catalog.models import MedicineProduct
from apps.catalog.product_search import filter_by_search

from .models import DrugReferenceEntry, DrugReferenceLoad
from .service import check_barcode, check_medicine
from .sources import file_sources

LOOKUP_LIMIT = 25


def _require_medicine_view(request):
    if not request.user.has_perm("catalog.view_medicineproduct"):
        raise PermissionDenied


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
        return self._render(
            request,
            "admin/drug_check/check.html",
            {"title": f"Проверка: {medicine.name}", "report": check_medicine(medicine)},
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
