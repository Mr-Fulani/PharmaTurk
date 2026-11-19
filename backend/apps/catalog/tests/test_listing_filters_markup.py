"""Фильтр «цена от — до» сравнивает с ценой покупателя: с товарной наценкой и шкалой."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.http import QueryDict

from apps.catalog.currency_models import GlobalCurrencySettings, MarkupScale
from apps.catalog.listing_filters import apply_price_filter
from apps.catalog.models import Brand, Category, ClothingProduct, Product
from apps.catalog.utils.markup_scale import apply_scale, scale_floors
from apps.catalog.utils.product_markup import apply_product_markup
from apps.catalog.utils.product_markup_sql import annotate_markup_factor

STEPS = [(0, 100), (5000, 50), (10000, 20)]


def request(query, currency="TRY"):
    headers = {"X-Currency": currency} if currency else {}
    return SimpleNamespace(query_params=QueryDict(query), headers=headers)


def found(query, queryset=None, currency="TRY"):
    queryset = Product.objects.all() if queryset is None else queryset
    return set(apply_price_filter(queryset, request(query, currency)).values_list("slug", flat=True))


def make_scale():
    scale = MarkupScale.objects.create(name="Фильтр")
    for price_from, percent in STEPS:
        scale.steps.create(price_from=price_from, percent=percent)
    return scale


def make_product(slug, price, **fields):
    return Product.objects.create(
        name=slug, slug=slug, product_type="accessories", currency="TRY",
        price=Decimal(str(price)), is_active=True, **fields,
    )


@pytest.fixture(autouse=True)
def frozen_price_snapshots(monkeypatch):
    # без снимков цен фильтр считает от цены источника: в лирах она равна цене без наценки
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)


@pytest.fixture
def global_percent(db):
    settings = GlobalCurrencySettings.load()
    settings.default_margin_percentage = Decimal("15")
    settings.markup_scale = None
    settings.save()
    return settings


def test_scale_floors_table_matches_apply_scale():
    for start, percent, floor in scale_floors(STEPS):
        for price in (start + 1, start + 2000):
            expected = apply_scale(STEPS, price).price_with_markup
            assert max(price * (1 + percent / 100), floor) == expected


def test_filter_uses_category_brand_and_global_percent(global_percent):
    fifty = Category.objects.create(name="Fifty", slug="fifty", margin_percent=Decimal("50"))
    child = Category.objects.create(name="Fifty child", slug="fifty-child", parent=fifty)
    brand = Brand.objects.create(name="Twenty", slug="twenty", margin_percent=Decimal("20"))
    make_product("in-category", 100, category=fifty)       # 150
    make_product("in-child", 100, category=child)           # 150 — наценка родителя
    make_product("branded", 100, category=fifty, brand=brand)  # 120 — бренд сильнее
    make_product("global", 100)                             # 115

    assert found("min_price=140&max_price=160") == {"in-category", "in-child"}
    assert found("min_price=118&max_price=122") == {"branded"}
    assert found("max_price=116") == {"global"}
    assert found("min_price=121") == {"in-category", "in-child"}


def test_filter_follows_category_scale_with_floor(global_percent):
    scaled = Category.objects.create(name="Scaled", slug="scaled-filter", markup_scale=make_scale())
    make_product("p4990", 4990, category=scaled)   # 9 980
    make_product("p5010", 5010, category=scaled)   # 10 000 — не дешевле предыдущей ступени
    make_product("p8000", 8000, category=scaled)   # 12 000
    make_product("p20000", 20000, category=scaled)  # 24 000

    assert found("max_price=9985") == {"p4990"}
    assert found("min_price=9990&max_price=10010") == {"p5010"}
    assert found("min_price=11000&max_price=13000") == {"p8000"}
    assert found("min_price=23000") == {"p20000"}


def test_sql_factor_equals_python_markup(global_percent):
    scaled = Category.objects.create(name="Scaled", slug="scaled-equal", markup_scale=make_scale())
    brand = Brand.objects.create(name="Thirty", slug="thirty", margin_percent=Decimal("30"))
    for price in (100, 4990, 5010, 6000, 9990, 10010, 12400, 12600, 50000):
        make_product(f"s{price}", price, category=scaled)
    make_product("branded", 6000, category=scaled, brand=brand)
    make_product("plain", 6000)

    factors = dict(annotate_markup_factor(Product.objects.all()).values_list("pk", "_markup_factor"))
    for product in Product.objects.select_related("brand", "category"):
        in_sql = (product.price * factors[product.pk]).quantize(Decimal("0.01"))
        assert in_sql == apply_product_markup(product.price, product), product.slug


def test_global_scale_skips_medicines(global_percent):
    global_percent.markup_scale = make_scale()
    global_percent.save()
    make_product("accessory", 100)  # 200 — первая ступень
    Product.objects.bulk_create([
        Product(name="medicine", slug="medicine", product_type="medicines", currency="TRY",
                price=Decimal("100"), is_active=True),  # 115 — глобальный процент
    ])

    assert found("min_price=190&max_price=210") == {"accessory"}
    assert found("min_price=110&max_price=120") == {"medicine"}


def test_domain_model_filter_includes_markup(global_percent):
    fifty = Category.objects.create(name="Fifty", slug="fifty-domain", margin_percent=Decimal("50"))
    ClothingProduct.objects.create(name="marked", slug="marked", price=Decimal("100"), category=fifty)
    ClothingProduct.objects.create(name="plain", slug="plain", price=Decimal("100"))

    clothing = ClothingProduct.objects.all()
    assert found("min_price=140&max_price=160", clothing, currency=None) == {"marked"}
    assert found("min_price=110&max_price=120", clothing, currency=None) == {"plain"}
