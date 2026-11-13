"""Один товар у двух магазинов (Intersport, SuperStep, SPX): на сайте остаётся более дорогой.

Решение владельца 13.11.2026 — ``apps/scrapers/store_twins.py``.
"""

import pytest

from apps.catalog.models import Category, Product, ProductSlugHistory
from apps.scrapers import services as scraper_services
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScrapedProductLog, ScraperConfig, ScrapingSession
from apps.scrapers.services import SIBLING_STORE_SOURCES, ScraperIntegrationService
from apps.scrapers.store_twins import STORE_TWIN_OF_KEY, is_pricier

CODE = "EQYTG03218.6459"


def test_spx_is_a_sibling_of_intersport_and_superstep():
    assert set(SIBLING_STORE_SOURCES["spx"]) == {"intersport", "superstep"}
    assert "spx" in SIBLING_STORE_SOURCES["intersport"] and "spx" in SIBLING_STORE_SOURCES["superstep"]


@pytest.mark.parametrize(
    "new, old, expected",
    [(120, 100, True), (100, 100, False), (90, 100, False), (None, 100, False), (120, None, False)],
)
def test_is_pricier(new, old, expected):
    assert is_pricier(new, old) is expected


def _goggle(price):
    return ScrapedProduct(
        name="Quiksilver Storm Erkek Siyah Goggle",
        url="https://www.spx.com.tr/quiksilver-storm-erkek-siyah-goggle-eqytg03218-6459/",
        external_id=f"spx-{CODE}",
        source="spx",
        price=price,
        currency="TRY",
        images=["https://497ea4-spx.akinoncloudcdn.com/products/x.jpg"],
        attributes={"spx_subgroup": "GOGGLE", "spx_category_slugs": ["winter-goggles", "winter-sports", "sports"]},
    )


@pytest.fixture
def setup(monkeypatch):
    sports = Category.objects.create(name="Спорттовары", slug="sports")
    twin = Product.objects.create(
        name="Мужская горнолыжная маска Quiksilver Storm, черная", slug="muzhskaya-maska-quiksilver-storm",
        external_id=f"intersport-{CODE}", category=sports, product_type="sports", is_active=True, price=100,
    )
    ProductSlugHistory.objects.create(old_slug="quiksilver-storm-old", product_id=twin.pk, product_type="sports")
    config = ScraperConfig.objects.create(name="spx-test", parser_class="spx", base_url="https://www.spx.com.tr", default_category=sports)
    session = ScrapingSession.objects.create(scraper_config=config, status="running", start_url="https://www.spx.com.tr")
    service = ScraperIntegrationService()
    service._normalize_scraped_media = lambda *args, **kwargs: None
    service._record_source_offers = lambda *args, **kwargs: None
    monkeypatch.setattr(scraper_services, "record_listing_snapshot", lambda *args, **kwargs: None)
    created = []

    def fake_process(_session, scraped):
        product = Product.objects.create(
            name="Мужская горнолыжная маска Quiksilver Storm, черная", slug="muzhskaya-maska-quiksilver-storm-spx",
            external_id=scraped.external_id, category=sports, product_type="sports", is_active=True, price=scraped.price,
        )
        created.append(product)
        return "created", product

    service._process_single_product = fake_process
    return service, session, twin, created


@pytest.mark.django_db
def test_pricier_new_product_is_created_and_hides_the_sibling(setup):
    service, session, twin, created = setup

    results = service._process_scraped_products(session, [_goggle(120)])

    assert results["created"] == 1 and len(created) == 1
    twin.refresh_from_db()
    assert twin.is_active is False and twin.external_data[STORE_TWIN_OF_KEY] == created[0].pk
    # Текущий и прежний адреса скрытого ведут на оставленный.
    for slug in ("muzhskaya-maska-quiksilver-storm", "quiksilver-storm-old"):
        assert ProductSlugHistory.objects.get(old_slug=slug).product_id == created[0].pk


@pytest.mark.django_db
@pytest.mark.parametrize("price", [100, 90, None])
def test_new_product_not_pricier_is_not_created(setup, price):
    service, session, twin, created = setup

    results = service._process_scraped_products(session, [_goggle(price)])

    assert results["skipped"] == 1 and created == []
    twin.refresh_from_db()
    assert twin.is_active is True
    log = ScrapedProductLog.objects.get(session=session)
    assert log.action == "skipped" and f"intersport-{CODE}" in log.message
