"""Счётчик ре-скрейпа: «обновлено» только при реальном изменении полей, иначе «пропущено».

Раньше _update_existing_product всегда возвращал "updated" (из-за служебных
scraped_sources/last_synced_at). Теперь повторная встреча без изменений → "skipped".
"""

import pytest

from apps.catalog.models import Category, Product
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig, ScrapingSession
from apps.scrapers.services import ScraperIntegrationService


def _setup():
    cat = Category.objects.create(name="Тест", slug="rescrape-test")
    config = ScraperConfig.objects.create(
        name="rescrape-cfg", parser_class="lcw", base_url="https://e.com", default_category=cat
    )
    session = ScrapingSession.objects.create(
        scraper_config=config, start_url="https://e.com", max_pages=1, max_products=10, status="running"
    )
    product = Product.objects.create(
        name="Товар", slug="rescrape-product", category=cat, product_type="clothing",
        price=100, currency="TRY", external_id="lcw-rescrape-1", external_data={},
        is_available=True, stock_quantity=5,
    )
    return ScraperIntegrationService(), session, product


def _scraped(price=100, currency="TRY"):
    return ScrapedProduct(
        name="Товар", description="", price=price, currency=currency,
        url="https://e.com/p", external_id="lcw-rescrape-1", source="lcw",
        is_available=True, stock_quantity=5, attributes={},
    )


@pytest.mark.django_db
def test_unchanged_rescrape_is_skipped():
    svc, session, product = _setup()
    # Первый прогон стабилизирует external_data (attributes и т.п.)
    svc._update_existing_product(session, _scraped(), product)
    product.refresh_from_db()
    # Повторный идентичный прогон — изменений нет → skipped
    action, _ = svc._update_existing_product(session, _scraped(), product)
    assert action == "skipped"


@pytest.mark.django_db
def test_price_change_is_updated():
    svc, session, product = _setup()
    svc._update_existing_product(session, _scraped(), product)
    product.refresh_from_db()
    action, _ = svc._update_existing_product(session, _scraped(price=150), product)
    assert action == "updated"


@pytest.mark.django_db
def test_currency_change_is_updated_even_when_numeric_amount_is_equal():
    svc, session, product = _setup()
    action, updated = svc._update_existing_product(
        session, _scraped(price=100, currency="USD"), product
    )
    updated.refresh_from_db()
    assert action == "updated"
    assert updated.currency == "USD"
    assert updated.price == 100


@pytest.mark.django_db
def test_zero_source_price_is_not_treated_as_missing():
    svc, session, product = _setup()
    action, updated = svc._update_existing_product(session, _scraped(price=0), product)
    updated.refresh_from_db()
    assert action == "updated"
    assert updated.price == 0


@pytest.mark.django_db
def test_scraped_sources_is_upserted_instead_of_growing_forever():
    svc, session, product = _setup()
    for _ in range(3):
        svc._update_existing_product(session, _scraped(), product)
        product.refresh_from_db()
    assert len(product.external_data["scraped_sources"]) == 1
