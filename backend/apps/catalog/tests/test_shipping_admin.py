from django.contrib import admin

from apps.catalog.currency_models import (
    CurrencyUpdateLog,
    GlobalCurrencySettings,
    GlobalShippingSettings,
    ProductPrice,
    ProductVariantPrice,
)
from apps.catalog.models import Category


def flattened_fields(model_admin):
    return {
        field
        for _title, options in model_admin.fieldsets
        for field in options.get("fields", ())
    }


def test_margin_and_shipping_have_separate_admin_sections():
    margin_admin = admin.site._registry[GlobalCurrencySettings]
    shipping_admin = admin.site._registry[GlobalShippingSettings]

    assert "default_air_shipping_usd" not in flattened_fields(margin_admin)
    assert "free_shipping_min_subtotal_usd" not in flattened_fields(margin_admin)
    assert "default_air_shipping_usd" in flattened_fields(shipping_admin)
    assert "free_shipping_min_subtotal_usd" in flattened_fields(shipping_admin)


def test_category_shipping_rule_is_visible_without_collapsed_section():
    category_admin = admin.site._registry[Category]
    shipping_section = next(options for title, options in category_admin.fieldsets if str(title) == "Доставка")

    assert "shipping_calculation" in shipping_section["fields"]
    assert "classes" not in shipping_section
    assert "shipping_calculation" in category_admin.list_display
    assert "shipping_calculation" in category_admin.list_filter


def test_product_and_variant_shipping_sections_explain_highest_priority():
    product_admin = admin.site._registry[ProductPrice]
    variant_admin = admin.site._registry[ProductVariantPrice]

    product_title = next(str(title) for title, _options in product_admin.fieldsets if "доставка" in str(title).lower())
    variant_title = next(str(title) for title, _options in variant_admin.fieldsets if "доставка" in str(title).lower())

    assert "наивысший приоритет" in product_title.lower()
    assert "наивысший приоритет" in variant_title.lower()


def test_currency_update_log_admin_uses_only_log_fields(rf, django_user_model):
    request = rf.get("/admin/catalog/currencyupdatelog/")
    request.user = django_user_model(is_staff=True, is_superuser=True)
    log_admin = admin.site._registry[CurrencyUpdateLog]

    list(log_admin.get_queryset(request)[:1])
    assert log_admin.get_queryset(request).query.select_related is False
    assert "updated_at" not in flattened_fields(log_admin)
    assert log_admin.get_actions(request) == {}
