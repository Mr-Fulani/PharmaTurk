from unittest.mock import patch

from django.apps import apps
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig

from config.admin import MudarobaAdminSite


def _model(object_name, name=None):
    return {
        "object_name": object_name,
        "name": name or object_name,
        "perms": {"view": True},
        "admin_url": f"/admin/test/{object_name.lower()}/",
    }


def _app(app_label, name, *models):
    return {
        "app_label": app_label,
        "name": name,
        "app_url": f"/admin/{app_label}/",
        "has_module_perms": True,
        "models": list(models),
    }


def _models_by_group(groups):
    return {group["name"]: [model["object_name"] for model in group["models"]] for group in groups}


def test_project_admin_site_is_the_configured_default():
    assert isinstance(admin.site, MudarobaAdminSite)
    assert isinstance(apps.get_app_config("admin"), AdminConfig)
    assert admin.site.index_title == "Панель управления Mudaroba"


def test_main_index_groups_media_and_catalog_without_changing_model_links():
    product_image = _model("ProductImage", "Изображения товаров")
    moderation = _model("MediaEnrichmentCandidate", "Модерация изображений")
    banner_media = _model("MarketingBannerMedia", "Медиа баннеров")
    medicine = _model("MedicineProduct", "Товары — Медикаменты")
    category = _model("CategoryMedicines", "Категории — Медицина")
    source_offer = _model("ProductSourceOffer", "Предложения источников")

    source_apps = [
        _app(
            "catalog",
            "Каталог",
            medicine,
            category,
            product_image,
            moderation,
            source_offer,
        ),
        _app("marketing", "Маркетинг", banner_media),
    ]
    site = MudarobaAdminSite(name="test_admin")

    with patch.object(AdminSite, "get_app_list", return_value=source_apps):
        groups = site.get_app_list(request=object())

    models = _models_by_group(groups)
    assert models["Изображения и медиа"] == [
        "MediaEnrichmentCandidate",
        "ProductImage",
        "MarketingBannerMedia",
    ]
    assert models["Товары каталога"] == ["MedicineProduct"]
    assert models["Категории и справочники"] == ["CategoryMedicines"]
    assert models["Источники и проверки"] == ["ProductSourceOffer"]
    assert product_image["admin_url"] == "/admin/test/productimage/"
    assert moderation["perms"] == {"view": True}


def test_app_index_keeps_django_native_grouping():
    source_apps = [_app("catalog", "Каталог", _model("ProductImage"))]
    site = MudarobaAdminSite(name="test_admin")

    with patch.object(AdminSite, "get_app_list", return_value=source_apps):
        result = site.get_app_list(request=object(), app_label="catalog")

    assert result is source_apps
