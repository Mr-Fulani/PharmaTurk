"""old_price — только зачёркнутая цена источника, а не прежняя цена товара."""

from decimal import Decimal

import pytest

from apps.catalog.models import Category, Product
from apps.catalog.utils.old_price import source_old_price
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig, ScrapingSession
from apps.scrapers.services import ScraperIntegrationService


def _setup(**product_overrides):
    cat = Category.objects.create(name="Old price", slug="old-price-test")
    config = ScraperConfig.objects.create(
        name="old-price-cfg", parser_class="lcw", base_url="https://e.com", default_category=cat
    )
    session = ScrapingSession.objects.create(
        scraper_config=config, start_url="https://e.com", max_pages=1, max_products=10, status="running"
    )
    values = dict(
        name="Товар", slug="old-price-product", category=cat, product_type="clothing",
        price=100, currency="TRY", external_id="lcw-old-price-1", external_data={},
        is_available=True, stock_quantity=5,
    )
    values.update(product_overrides)
    return ScraperIntegrationService(), session, Product.objects.create(**values)


def _scraped(price=100, old_price=None):
    return ScrapedProduct(
        name="Товар", description="", price=price, old_price=old_price, currency="TRY",
        url="https://e.com/p", external_id="lcw-old-price-1", source="lcw",
        is_available=True, stock_quantity=5, attributes={},
    )


@pytest.mark.parametrize("old,price,expected", [
    (120, 100, Decimal("120")),
    (100, 100, None),
    (80, 100, None),
    (None, 100, None),
    (120, None, None),
    ("", 100, None),
])
def test_source_old_price_only_when_above_price(old, price, expected):
    assert source_old_price(old, price) == expected


@pytest.mark.django_db
def test_price_drop_without_source_old_price_is_not_a_discount():
    svc, session, product = _setup()
    _, updated = svc._update_existing_product(session, _scraped(price=80), product)
    updated.refresh_from_db()
    assert updated.price == 80
    assert updated.old_price is None


@pytest.mark.django_db
def test_rescrape_clears_stale_heuristic_old_price():
    svc, session, product = _setup(old_price=150)
    _, updated = svc._update_existing_product(session, _scraped(price=100), product)
    updated.refresh_from_db()
    assert updated.old_price is None


@pytest.mark.django_db
def test_source_strikethrough_price_is_kept():
    svc, session, product = _setup()
    _, updated = svc._update_existing_product(session, _scraped(price=80, old_price=120), product)
    updated.refresh_from_db()
    assert (updated.price, updated.old_price) == (80, 120)


@pytest.mark.django_db
def test_new_product_gets_source_old_price():
    svc, session, _ = _setup()
    Product.objects.all().delete()
    item = _scraped(price=80, old_price=120)
    item.external_id = "lcw-old-price-new"
    status, product = svc._create_new_product(session, item)
    product.refresh_from_db()
    assert status == "created"
    assert (product.price, product.old_price) == (80, 120)
