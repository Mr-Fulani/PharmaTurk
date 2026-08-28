from decimal import Decimal
from uuid import uuid4

import pytest
from django.core.cache import cache

from apps.catalog.models import Category, Product, ProductSourceOffer, SupplementProduct
from apps.catalog.services.supplement_stock_discovery import (
    SupplementStockDiscoveryService,
)
from apps.scrapers.models import ScraperConfig
from apps.scrapers.parsers.akakce import (
    AkakceProductSnapshot,
    AkakceSearchCandidate,
    AkakceSellerOffer,
    AkakceParser,
)


PRODUCT_URL = (
    "https://www.akakce.com/vitamin-mineral/"
    "en-ucuz-imuplus-imuplus-7-24-150-ml-surup-fiyati,1325897213.html"
)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def supplement(settings):
    settings.SUPPLEMENT_STOCK_DISCOVERY_ENABLED = True
    settings.SOURCE_OFFER_VERIFICATION_ENABLED = True
    settings.SOURCE_OFFER_VERIFICATION_SOURCES = ["akakce"]
    settings.SUPPLEMENT_STOCK_ADAPTER_SOURCES = ["akakce"]
    category = Category.objects.create(
        name="Supplement discovery",
        slug=f"supplement-discovery-{uuid4().hex}",
    )
    base = Product.objects.create(
        name="IMUPLUS 7/24 150 ML SURUP",
        slug=f"imuplus-discovery-{uuid4().hex}",
        product_type="supplements",
        category=category,
        price=Decimal("500.00"),
        currency="TRY",
        is_available=False,
    )
    item = SupplementProduct.objects.get(base_product=base)
    ScraperConfig.objects.create(
        name=f"akakce-discovery-{uuid4().hex}",
        parser_class="akakce",
        base_url="https://www.akakce.com",
        default_category=category,
        status="active",
        is_enabled=True,
        use_proxy=True,
        sync_enabled=False,
    )
    return item


def _candidate():
    return AkakceSearchCandidate(
        name="İMUPLUS Imuplus 7/24 150 Ml Şurup",
        url=PRODUCT_URL,
        external_id="1325897213",
    )


def _snapshot(*, in_stock=True):
    offers = (
        (
            AkakceSellerOffer(
                seller_name="Dermoevim.com",
                seller_url="https://dermoevim.example/product",
                price=Decimal("545.99"),
                currency="TRY",
            ),
        )
        if in_stock
        else ()
    )
    return AkakceProductSnapshot(
        name="İMUPLUS Imuplus 7/24 150 Ml Şurup",
        canonical_url=PRODUCT_URL,
        external_id="1325897213",
        offers=offers,
    )


@pytest.mark.django_db
def test_discovery_persists_only_boolean_market_offer(supplement, monkeypatch):
    monkeypatch.setattr(AkakceParser, "search_products", lambda *_args, **_kwargs: [_candidate()])
    monkeypatch.setattr(AkakceParser, "inspect_offer", lambda *_args, **_kwargs: _snapshot())

    result = SupplementStockDiscoveryService().discover(supplement)

    assert result.status == "created"
    offer = ProductSourceOffer.objects.get(pk=result.offer.pk)
    assert offer.product_id == supplement.base_product_id
    assert offer.parser_key == "akakce"
    assert offer.external_product_id == "1325897213"
    assert offer.source_price == Decimal("545.99")
    assert offer.source_currency == "TRY"
    assert offer.availability_status == ProductSourceOffer.AvailabilityStatus.IN_STOCK
    assert offer.stock_precision == ProductSourceOffer.StockPrecision.BOOLEAN
    assert offer.stock_quantity is None
    assert offer.parser_config["expected_name"] == supplement.name
    assert offer.response_metadata["seller_name"] == "Dermoevim.com"
    assert offer.response_metadata["discovered_on_demand"] is True


@pytest.mark.django_db
def test_discovery_records_known_product_without_current_seller(supplement, monkeypatch):
    monkeypatch.setattr(AkakceParser, "search_products", lambda *_args, **_kwargs: [_candidate()])
    monkeypatch.setattr(
        AkakceParser,
        "inspect_offer",
        lambda *_args, **_kwargs: _snapshot(in_stock=False),
    )

    result = SupplementStockDiscoveryService().discover(supplement)

    offer = ProductSourceOffer.objects.get(pk=result.offer.pk)
    assert offer.availability_status == ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK
    assert offer.source_price is None
    assert offer.response_metadata["in_stock_seller_count"] == 0


@pytest.mark.django_db
def test_ambiguous_or_wrong_dosage_does_not_create_offer(supplement, monkeypatch):
    wrong = AkakceSearchCandidate(
        name="IMUPLUS 7/24 500 Ml Şurup",
        url=PRODUCT_URL,
        external_id="1325897213",
    )
    monkeypatch.setattr(AkakceParser, "search_products", lambda *_args, **_kwargs: [wrong])

    result = SupplementStockDiscoveryService().discover(supplement)

    assert result.status == "no_match"
    assert ProductSourceOffer.objects.filter(parser_key="akakce").count() == 0
    assert SupplementStockDiscoveryService().needs_discovery(supplement) is False


@pytest.mark.django_db
def test_discovery_is_idempotent_and_never_remaps_active_offer(supplement, monkeypatch):
    monkeypatch.setattr(AkakceParser, "search_products", lambda *_args, **_kwargs: [_candidate()])
    monkeypatch.setattr(AkakceParser, "inspect_offer", lambda *_args, **_kwargs: _snapshot())
    service = SupplementStockDiscoveryService()

    first = service.discover(supplement)
    second = service.discover(supplement)

    assert first.status == "created"
    assert second.status == "existing"
    assert second.offer.pk == first.offer.pk
    assert ProductSourceOffer.objects.filter(parser_key="akakce").count() == 1


@pytest.mark.django_db
def test_dry_run_does_not_write_offer_or_negative_cache(supplement, monkeypatch):
    monkeypatch.setattr(AkakceParser, "search_products", lambda *_args, **_kwargs: [])

    result = SupplementStockDiscoveryService().discover(
        supplement,
        persist=False,
        force=True,
    )

    assert result.status == "no_match"
    assert ProductSourceOffer.objects.filter(parser_key="akakce").count() == 0
    assert SupplementStockDiscoveryService().needs_discovery(supplement) is True
