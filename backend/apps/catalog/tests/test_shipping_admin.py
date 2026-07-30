from django.contrib import admin
from decimal import Decimal
from types import SimpleNamespace

from apps.catalog.currency_models import (
    CurrencyUpdateLog,
    GlobalCurrencySettings,
    GlobalShippingSettings,
    ProductPrice,
    ProductVariantPrice,
    ServicePrice,
)
from apps.catalog.admin import ServicePriceInline
from apps.catalog.models import Category, ClothingVariant, Service


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


def test_product_price_admin_shows_effective_product_markup_separately(monkeypatch):
    from apps.catalog.utils.currency_converter import currency_converter

    monkeypatch.setattr(
        currency_converter,
        "get_margin_rate",
        lambda from_currency, to_currency: Decimal("0"),
    )
    product_admin = admin.site._registry[ProductPrice]
    product = SimpleNamespace(
        brand=None,
        category=SimpleNamespace(margin_percent=Decimal("10")),
    )
    price = SimpleNamespace(
        product=product,
        base_currency="TRY",
        base_price=Decimal("100"),
        rub_price=Decimal("200"),
        rub_price_with_margin=Decimal("200"),
        usd_price=Decimal("5"),
        usd_price_with_margin=Decimal("5"),
        kzt_price=None,
        kzt_price_with_margin=None,
        eur_price=None,
        eur_price_with_margin=None,
        try_price=Decimal("100"),
        try_price_with_margin=Decimal("100"),
        usdt_price=None,
        usdt_price_with_margin=None,
    )

    assert product_admin.effective_product_markup_display(price) == "10% (категория)"
    assert product_admin.public_rub_price(price) == Decimal("220.00")
    assert product_admin.public_try_price(price) == Decimal("110.00")


def test_service_price_admin_and_inline_show_total_public_margin(monkeypatch):
    from apps.catalog.utils.currency_converter import currency_converter

    monkeypatch.setattr(
        currency_converter,
        "get_margin_rate",
        lambda from_currency, to_currency: Decimal("0"),
    )
    service_admin = admin.site._registry[ServicePrice]
    service = SimpleNamespace(
        brand=None,
        category=SimpleNamespace(margin_percent=Decimal("15")),
    )
    price = SimpleNamespace(
        service=service,
        base_currency="TRY",
        base_price=Decimal("100"),
        rub_price=Decimal("200"),
        rub_price_with_margin=Decimal("200"),
        usd_price=Decimal("5"),
        usd_price_with_margin=Decimal("5"),
        kzt_price=None,
        kzt_price_with_margin=None,
        eur_price=None,
        eur_price_with_margin=None,
        try_price=Decimal("100"),
        try_price_with_margin=Decimal("100"),
        usdt_price=None,
        usdt_price_with_margin=None,
    )

    assert service_admin.effective_product_markup_display(price) == "15% (категория)"
    assert service_admin.public_rub_price(price) == Decimal("230.00")
    assert service_admin.public_try_price(price) == Decimal("115.00")

    inline = ServicePriceInline(Service, admin.site)
    assert inline.effective_product_markup_display(price) == "15% (категория)"
    assert inline.public_rub_price(price) == Decimal("230.00")
    assert "public_rub_price" in flattened_fields(inline)
    assert "currency_pair_margin_display" in flattened_fields(inline)
    assert "usdt_markup_display" in flattened_fields(inline)
    assert "rub_price_with_margin" not in flattened_fields(inline)
    assert str(inline.verbose_name) == (
        "Итоговые цены с маржой"
    )
    assert str(inline.verbose_name_plural) == (
        "Итоговые цены по валютам — маржа категории/глобальная + маржа валютной пары"
    )


def test_service_price_inline_title_shows_dynamic_margin_source(monkeypatch):
    from apps.catalog.utils import product_markup

    monkeypatch.setattr(
        product_markup,
        "get_effective_product_markup",
        lambda service: (Decimal("25.00"), "global"),
    )
    inline = ServicePriceInline(Service, admin.site)
    monkeypatch.setattr(
        inline,
        "_currency_pair_margin_summary_for_base",
        lambda base_currency: "валютная пара TRY→RUB 10.00%",
    )
    monkeypatch.setattr(
        inline,
        "_usdt_markup_summary",
        lambda: "наценка USDT 5.00%",
    )

    inline._set_dynamic_margin_titles(SimpleNamespace(currency="TRY"))

    assert str(inline.verbose_name) == (
        "Итоговые цены — маржа услуги 25.00% (глобальная настройка); "
        "валютная пара TRY→RUB 10.00%; наценка USDT 5.00%"
    )
    assert str(inline.verbose_name_plural) == (
        "Итоговые цены по валютам — маржа услуги 25.00% "
        "(глобальная настройка); валютная пара TRY→RUB 10.00%; "
        "наценка USDT 5.00%"
    )


def test_service_admin_uses_current_pair_margin_without_waiting_for_snapshot(monkeypatch):
    from apps.catalog.utils.currency_converter import currency_converter

    monkeypatch.setattr(
        currency_converter,
        "get_margin_rate",
        lambda from_currency, to_currency: (
            Decimal("10") if (from_currency, to_currency) == ("TRY", "RUB")
            else Decimal("0")
        ),
    )
    service_admin = admin.site._registry[ServicePrice]
    price = SimpleNamespace(
        service=SimpleNamespace(
            brand=None,
            category=SimpleNamespace(margin_percent=Decimal("15")),
        ),
        base_currency="TRY",
        base_price=Decimal("100"),
        rub_price=Decimal("200"),
        # Намеренно устаревший snapshot: админка не должна брать это значение.
        rub_price_with_margin=Decimal("200"),
    )

    assert service_admin.public_rub_price(price) == Decimal("253.00")


def test_service_admin_uses_current_usdt_markup_without_waiting_for_snapshot(monkeypatch):
    from apps.catalog.utils.currency_converter import currency_converter

    monkeypatch.setattr(
        currency_converter,
        "convert_price",
        lambda amount, from_currency, to_currency, apply_margin: (
            Decimal("10000"),
            Decimal("221.83"),
            Decimal("221.83"),
        ),
    )
    service_admin = admin.site._registry[ServicePrice]
    price = SimpleNamespace(
        service=SimpleNamespace(
            brand=None,
            category=SimpleNamespace(margin_percent=Decimal("15")),
        ),
        base_currency="TRY",
        base_price=Decimal("10000"),
        # Намеренно устаревшее значение, рассчитанное при USDT-наценке 3%.
        usdt_price=Decimal("217.61"),
        usdt_price_with_margin=Decimal("250.25"),
    )

    assert service_admin.public_usdt_price(price) == Decimal("255.10")


def test_variant_admin_currency_columns_include_product_markup(monkeypatch):
    from apps.catalog.utils.currency_converter import currency_converter

    monkeypatch.setattr(
        currency_converter,
        "convert_to_multiple_currencies",
        lambda *args, **kwargs: {
            "RUB": {"price_with_margin": Decimal("200.00")}
        },
    )
    variant_admin = admin.site._registry[ClothingVariant]
    variant = SimpleNamespace(
        price=Decimal("100"),
        currency="TRY",
        product=SimpleNamespace(
            price=Decimal("100"),
            currency="TRY",
            brand=None,
            category=SimpleNamespace(margin_percent=Decimal("10")),
        ),
    )

    assert variant_admin._converted_with_margin(variant, "RUB") == Decimal("220.00")
