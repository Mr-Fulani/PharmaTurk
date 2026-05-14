import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from apps.catalog.admin import ClothingProductAdmin, ServiceAdmin
from apps.catalog.admin_books import BookProductAdmin
from apps.catalog.admin_headwear import HeadwearProductAdmin, HeadwearVariantAdmin
from apps.catalog.admin_perfumery import PerfumeryProductAdmin
from apps.catalog.admin_wave2 import MedicineProductAdmin, SupplementProductAdmin
from apps.catalog.models import (
    BookProduct,
    ClothingProduct,
    HeadwearProduct,
    HeadwearVariant,
    MedicineProduct,
    PerfumeryProduct,
    Service,
    SupplementProduct,
)


@pytest.fixture
def admin_request():
    class DummySuperUser:
        is_active = True
        is_staff = True
        is_superuser = True

        def has_perm(self, perm, obj=None):
            return True

        def has_perms(self, perm_list, obj=None):
            return True

        def has_module_perms(self, app_label):
            return True

    request = RequestFactory().get("/admin/")
    request.user = DummySuperUser()
    return request


def _action_names(model_admin_class, model, request):
    model_admin = model_admin_class(model, AdminSite())
    return list(model_admin.get_actions(request).keys())


@pytest.mark.parametrize(
    ("model_admin_class", "model"),
    [
        (ClothingProductAdmin, ClothingProduct),
        (BookProductAdmin, BookProduct),
        (HeadwearProductAdmin, HeadwearProduct),
    ],
)
def test_product_admins_share_same_core_bulk_actions(model_admin_class, model, admin_request):
    action_names = _action_names(model_admin_class, model, admin_request)

    assert action_names[:5] == [
        "make_active",
        "make_inactive",
        "run_ai",
        "run_ai_auto_apply",
        "run_find_merge_duplicates",
    ]
    assert "delete_selected" in action_names


@pytest.mark.parametrize(
    ("model_admin_class", "model"),
    [
        (MedicineProductAdmin, MedicineProduct),
        (SupplementProductAdmin, SupplementProduct),
    ],
)
def test_media_enrichment_domains_keep_consistent_action_menu(model_admin_class, model, admin_request):
    action_names = _action_names(model_admin_class, model, admin_request)

    assert action_names[:6] == [
        "make_active",
        "make_inactive",
        "run_ai",
        "run_ai_auto_apply",
        "run_find_merge_duplicates",
        "run_media_enrichment",
    ]
    assert "delete_selected" in action_names


def test_perfumery_admin_inherits_global_and_ai_bulk_actions(admin_request):
    action_names = _action_names(PerfumeryProductAdmin, PerfumeryProduct, admin_request)

    assert action_names[:5] == [
        "make_active",
        "make_inactive",
        "run_ai",
        "run_ai_auto_apply",
        "run_find_merge_duplicates",
    ]
    assert "mark_featured" not in action_names
    assert "delete_selected" in action_names


def test_variant_admin_keeps_activation_and_ai_actions(admin_request):
    action_names = _action_names(HeadwearVariantAdmin, HeadwearVariant, admin_request)

    assert action_names[:2] == [
        "activate_variants",
        "deactivate_variants",
    ]
    assert "run_variant_ai" in action_names
    assert "apply_variant_ai_draft" in action_names


def test_duplicate_search_action_label_marks_global_scope():
    model_admin = ClothingProductAdmin(ClothingProduct, AdminSite())

    assert (
        model_admin.run_find_merge_duplicates.short_description
        == "[Общее] Поиск кандидатов в дубликаты (на модерацию)"
    )


def test_service_admin_gets_global_activation_actions(admin_request):
    action_names = _action_names(ServiceAdmin, Service, admin_request)

    assert action_names[:2] == [
        "make_active",
        "make_inactive",
    ]
    assert "delete_selected" in action_names


def test_run_ai_action_mixin_uses_domain_ai_logs_prefetch_for_perfumery():
    model_admin = PerfumeryProductAdmin(PerfumeryProduct, AdminSite())

    assert model_admin.get_ai_logs_prefetch_path() == "base_product__ai_logs"
