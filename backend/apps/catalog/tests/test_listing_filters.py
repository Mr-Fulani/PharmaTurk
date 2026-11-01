"""Regression contract for the storefront price and availability list filters."""

from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

import pytest
from django.http import QueryDict
from rest_framework.test import APIClient

from apps.catalog import views as catalog_views
from apps.catalog.currency_models import ProductPrice
from apps.catalog.models import Category, ClothingProduct, Product
from apps.catalog.utils.currency_converter import currency_converter


def make_request(query="", headers=None):
    return SimpleNamespace(query_params=QueryDict(query), headers=headers or {})


def slugs(queryset):
    return set(queryset.values_list("slug", flat=True))


def make_product(slug, **fields):
    fields.setdefault("price", Decimal("100"))
    return Product.objects.create(
        name=slug,
        slug=slug,
        product_type="accessories",
        currency="TRY",
        is_active=True,
        **fields,
    )


def make_clothing(slug, **fields):
    fields.setdefault("price", Decimal("100"))
    return ClothingProduct.objects.create(name=slug, slug=slug, **fields)


@pytest.fixture
def frozen_price_snapshots(monkeypatch):
    """Only the snapshots written by a test take part in the filter."""
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)


@pytest.fixture
def stock_products(frozen_price_snapshots):
    make_product(
        "in-status",
        is_available=True,
        availability_status="in_stock",
        stock_quantity=None,
    )
    make_product(
        "in-quantity",
        is_available=True,
        availability_status="backorder",
        stock_quantity=5,
    )
    make_product(
        "sold-out",
        is_available=True,
        availability_status="out_of_stock",
        stock_quantity=0,
    )
    make_product(
        "unavailable",
        is_available=False,
        availability_status="in_stock",
        stock_quantity=5,
    )


@pytest.fixture
def snapshot_products(frozen_price_snapshots):
    """One product for every step of the storefront-price fallback."""
    make_product("final-price", final_price_usd=Decimal("10"), final_price_rub=Decimal("10"))
    with_snapshot = make_product("snapshot-price")
    ProductPrice.objects.create(
        product=with_snapshot,
        usd_price_with_margin=Decimal("20"),
        rub_price_with_margin=Decimal("20"),
        kzt_price_with_margin=Decimal("20"),
        eur_price_with_margin=Decimal("20"),
        try_price_with_margin=Decimal("20"),
    )
    make_product("discounted", price=Decimal("100"), old_price=Decimal("30"))


@pytest.fixture
def stub_converter(monkeypatch):
    """1 TRY = 0.1 USD; the TRY→USD pair carries a 10% margin."""
    rates = {"TRY": Decimal("0.1"), "EUR": Decimal("1")}

    def convert_price(amount, from_currency, to_currency, apply_margin=True):
        return amount, amount * rates[from_currency], amount * rates[from_currency]

    monkeypatch.setattr(currency_converter, "convert_price", convert_price)
    monkeypatch.setattr(
        currency_converter,
        "_get_margin_rate",
        lambda from_currency, to_currency: (
            Decimal("10") if from_currency == "TRY" else Decimal("0")
        ),
    )
    return rates


@pytest.mark.django_db
@pytest.mark.parametrize("value", ["true", "1", "YES"])
def test_in_stock_needs_availability_and_status_or_quantity(stock_products, value):
    result = catalog_views._apply_availability_filter(
        Product.objects.all(), make_request(f"in_stock={value}")
    )

    assert slugs(result) == {"in-status", "in-quantity"}


@pytest.mark.django_db
def test_negative_in_stock_keeps_everything_and_wins_over_is_available(stock_products):
    result = catalog_views._apply_availability_filter(
        Product.objects.all(), make_request("in_stock=false&is_available=false")
    )

    assert slugs(result) == {"in-status", "in-quantity", "sold-out", "unavailable"}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", {"in-status", "in-quantity", "sold-out"}),
        ("false", {"unavailable"}),
    ],
)
def test_is_available_filters_both_ways(stock_products, value, expected):
    result = catalog_views._apply_availability_filter(
        Product.objects.all(), make_request(f"is_available={value}")
    )

    assert slugs(result) == expected


@pytest.mark.django_db
def test_availability_status_combines_with_in_stock(stock_products):
    queryset = Product.objects.all()

    only_status = catalog_views._apply_availability_filter(
        queryset, make_request("availability_status=backorder")
    )
    combined = catalog_views._apply_availability_filter(
        queryset, make_request("in_stock=true&availability_status=in_stock")
    )

    assert slugs(only_status) == {"in-quantity"}
    assert slugs(combined) == {"in-status"}


@pytest.mark.django_db
def test_domain_model_without_status_uses_only_is_available():
    make_clothing("on-sale", is_available=True, stock_quantity=0)
    make_clothing("hidden", is_available=False, stock_quantity=5)

    result = catalog_views._apply_availability_filter(
        ClothingProduct.objects.all(),
        make_request("in_stock=true&availability_status=backorder"),
    )

    assert slugs(result) == {"on-sale"}


@pytest.mark.django_db
def test_price_filter_without_bounds_returns_queryset_untouched():
    queryset = Product.objects.all()

    assert catalog_views._apply_price_filter(queryset, make_request()) is queryset
    assert catalog_views._apply_price_filter(queryset, make_request("min_price=")) is queryset


@pytest.mark.django_db
def test_zero_lower_bound_alone_does_not_filter():
    queryset = Product.objects.all()

    assert catalog_views._apply_price_filter(queryset, make_request("min_price=0")) is queryset


@pytest.mark.django_db
def test_invalid_price_raises_today():
    # Known defect kept by the move: Decimal raises InvalidOperation, which
    # _parse_decimal does not catch. Fixing it must change this test on purpose.
    with pytest.raises(InvalidOperation):
        catalog_views._apply_price_filter(
            Product.objects.all(), make_request("min_price=abc")
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("min_price=50", {"expensive"}),
        ("price_min=50", {"expensive"}),
        ("max_price=50", {"cheap"}),
        ("price_max=50", {"cheap"}),
        ("min_price=50&price_min=5", {"expensive"}),
        ("max_price=50&price_max=500", {"cheap"}),
        ("min_price=0&max_price=50", {"cheap"}),
        ("min_price=10&max_price=100", {"cheap", "expensive"}),
    ],
)
def test_product_bounds_and_their_aliases(frozen_price_snapshots, query, expected):
    make_product("cheap", price=Decimal("10"))
    make_product("expensive", price=Decimal("100"))

    result = catalog_views._apply_price_filter(Product.objects.all(), make_request(query))

    assert slugs(result) == expected


@pytest.mark.django_db
def test_product_without_currency_ignores_snapshots_and_discount(snapshot_products):
    result = catalog_views._apply_price_filter(
        Product.objects.all(), make_request("max_price=50")
    )

    assert slugs(result) == set()


@pytest.mark.django_db
@pytest.mark.parametrize("currency", ["USD", "RUB"])
@pytest.mark.parametrize(
    ("bounds", "expected"),
    [
        ("min_price=5&max_price=15", "final-price"),
        ("min_price=15&max_price=25", "snapshot-price"),
        ("min_price=25&max_price=35", "discounted"),
    ],
)
def test_usd_and_rub_fall_back_from_final_to_snapshot_to_discount(
    snapshot_products, currency, bounds, expected
):
    result = catalog_views._apply_price_filter(
        Product.objects.all(), make_request(bounds, {"X-Currency": currency})
    )

    assert slugs(result) == {expected}


@pytest.mark.django_db
@pytest.mark.parametrize("currency", ["KZT", "EUR", "TRY"])
@pytest.mark.parametrize(
    ("bounds", "expected"),
    [
        ("min_price=5&max_price=15", set()),
        ("min_price=15&max_price=25", {"snapshot-price"}),
        ("min_price=25&max_price=35", {"discounted"}),
        ("min_price=90&max_price=110", {"final-price"}),
    ],
)
def test_other_currencies_skip_final_price_column(
    snapshot_products, currency, bounds, expected
):
    result = catalog_views._apply_price_filter(
        Product.objects.all(), make_request(bounds, {"X-Currency": currency})
    )

    assert slugs(result) == expected


@pytest.mark.django_db
def test_product_with_unsupported_currency_uses_base_price(snapshot_products):
    result = catalog_views._apply_price_filter(
        Product.objects.all(),
        make_request("max_price=50", {"X-Currency": "GBP"}),
    )

    assert slugs(result) == set()


@pytest.mark.django_db
def test_currency_header_wins_and_query_currency_is_case_insensitive(snapshot_products):
    queryset = Product.objects.all()
    bounds = "min_price=5&max_price=15"

    from_header = catalog_views._apply_price_filter(
        queryset, make_request(f"{bounds}&currency=GBP", {"X-Currency": "usd"})
    )
    from_query = catalog_views._apply_price_filter(
        queryset, make_request(f"{bounds}&currency=usd")
    )

    assert slugs(from_header) == {"final-price"}
    assert slugs(from_query) == {"final-price"}


@pytest.mark.django_db
def test_domain_model_without_currency_compares_raw_price():
    make_clothing("lira", price=Decimal("100"), currency="TRY")
    make_clothing("dollar", price=Decimal("500"), currency="USD")

    result = catalog_views._apply_price_filter(
        ClothingProduct.objects.all(), make_request("max_price=200")
    )

    assert slugs(result) == {"lira"}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # 1000 TRY is 110 USD with the margin, so the bound moves the raw price.
        ("max_price=109", {"dollar"}),
        ("max_price=111", {"dollar", "lira"}),
        ("min_price=105&max_price=111", {"dollar", "lira"}),
        ("min_price=111", {"euro"}),
    ],
)
def test_domain_model_converts_each_currency_with_margin(stub_converter, query, expected):
    make_clothing("lira", price=Decimal("1000"), currency="TRY")
    make_clothing("dollar", price=Decimal("108"), currency="USD")
    make_clothing("euro", price=Decimal("150"), currency="EUR")

    result = catalog_views._apply_price_filter(
        ClothingProduct.objects.all(),
        make_request(query, {"X-Currency": "USD"}),
    )

    assert slugs(result) == expected


@pytest.mark.django_db
def test_domain_currency_with_failed_conversion_drops_out(stub_converter):
    del stub_converter["TRY"]
    make_clothing("lira", price=Decimal("10"), currency="TRY")
    make_clothing("dollar", price=Decimal("10"), currency="USD")

    result = catalog_views._apply_price_filter(
        ClothingProduct.objects.all(),
        make_request("max_price=100", {"X-Currency": "USD"}),
    )

    assert slugs(result) == {"dollar"}


@pytest.mark.django_db
def test_domain_currency_with_zero_rate_drops_out(stub_converter):
    stub_converter["TRY"] = Decimal("0")
    make_clothing("lira", price=Decimal("10"), currency="TRY")
    make_clothing("dollar", price=Decimal("10"), currency="USD")

    result = catalog_views._apply_price_filter(
        ClothingProduct.objects.all(),
        make_request("max_price=100", {"X-Currency": "USD"}),
    )

    assert slugs(result) == {"dollar"}


@pytest.mark.django_db
def test_product_list_api_applies_both_filters(frozen_price_snapshots):
    category = Category.objects.create(name="Filters", slug="filters")
    make_product("match", category=category, price=Decimal("10"), is_available=True)
    make_product("too-expensive", category=category, price=Decimal("100"), is_available=True)
    make_product("not-available", category=category, price=Decimal("10"), is_available=False)

    response = APIClient().get(
        "/api/catalog/products", {"max_price": "50", "in_stock": "true"}
    )

    assert response.status_code == 200
    assert {row["slug"] for row in response.json()["results"]} == {"match"}


@pytest.mark.django_db
def test_domain_list_api_applies_both_filters():
    make_clothing("match", price=Decimal("10"), is_available=True)
    make_clothing("too-expensive", price=Decimal("100"), is_available=True)
    make_clothing("not-available", price=Decimal("10"), is_available=False)

    response = APIClient().get(
        "/api/catalog/clothing/products", {"max_price": "50", "in_stock": "true"}
    )

    assert response.status_code == 200
    assert {row["slug"] for row in response.json()["results"]} == {"match"}
