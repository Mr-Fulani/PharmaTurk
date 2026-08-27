from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.catalog.models import Product, ProductSourceOffer
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.source_offers import (
    build_source_offer_snapshots,
    record_scraped_product_offers,
)
from apps.scrapers.services import ScraperIntegrationService


@pytest.fixture
def product(db):
    return Product.objects.create(
        name="Dual write product",
        slug="dual-write-product",
        product_type="clothing",
    )


@pytest.mark.django_db
def test_boolean_source_does_not_record_synthetic_stock(product):
    scraped = ScrapedProduct(
        name="LCW product",
        price=Decimal("499.90"),
        currency="TRY",
        url="https://www.lcw.com/product-1",
        external_id="lcw-1",
        is_available=True,
        stock_quantity=1000,
        source="lcw",
    )

    offers = record_scraped_product_offers(product=product, scraped_product=scraped)

    assert len(offers) == 1
    offer = offers[0]
    assert offer.source_price == Decimal("499.90")
    assert offer.stock_precision == ProductSourceOffer.StockPrecision.BOOLEAN
    assert offer.stock_quantity is None
    assert offer.availability_status == ProductSourceOffer.AvailabilityStatus.IN_STOCK


@pytest.mark.django_db
def test_fashion_sizes_are_idempotent_and_missing_size_is_deactivated(product):
    scraped = ScrapedProduct(
        name="FLO product",
        price=Decimal("999.00"),
        currency="TRY",
        url="https://www.flo.com.tr/urun/product-1",
        external_id="flo-1",
        source="flo",
        attributes={
            "fashion_variants": [
                {
                    "external_id": "flo-variant-black",
                    "sku": "BLACK",
                    "color": "Siyah",
                    "price": "999.00",
                    "currency": "TRY",
                    "external_url": "https://www.flo.com.tr/urun/product-1",
                    "is_available": True,
                    "stock_quantity": 1000,
                    "sizes": [
                        {
                            "size": "M",
                            "sku": "BLACK-M",
                            "is_available": True,
                            "stock_quantity": 1000,
                        },
                        {
                            "size": "L",
                            "sku": "BLACK-L",
                            "is_available": False,
                            "stock_quantity": 0,
                        },
                    ],
                }
            ]
        },
    )

    first = record_scraped_product_offers(product=product, scraped_product=scraped)
    second = record_scraped_product_offers(product=product, scraped_product=scraped)

    assert len(first) == len(second) == 2
    assert ProductSourceOffer.objects.filter(product=product).count() == 2
    assert set(product.source_offers.values_list("size_key", flat=True)) == {"M", "L"}
    assert all(row.stock_quantity is None for row in second)

    scraped.attributes["fashion_variants"][0]["sizes"] = [
        {
            "size": "M",
            "sku": "BLACK-M",
            "is_available": True,
            "stock_quantity": 1000,
        }
    ]
    record_scraped_product_offers(product=product, scraped_product=scraped)

    assert product.source_offers.get(size_key="M").is_active is True
    assert product.source_offers.get(size_key="L").is_active is False


@pytest.mark.django_db
def test_ikea_records_exact_positive_stock_and_unknown_quantity_as_boolean(product):
    exact = ScrapedProduct(
        name="IKEA exact",
        price=Decimal("1299"),
        currency="TRY",
        url="https://www.ikea.com.tr/urun/123",
        external_id="123",
        source="ikea",
        is_available=True,
        stock_quantity=4,
    )
    unknown = ScrapedProduct(
        name="IKEA unknown",
        price=Decimal("1299"),
        currency="TRY",
        url="https://www.ikea.com.tr/urun/124",
        external_id="124",
        source="ikea",
        is_available=True,
        stock_quantity=None,
    )

    exact_snapshot = build_source_offer_snapshots(exact)[0]
    unknown_snapshot = build_source_offer_snapshots(unknown)[0]

    assert exact_snapshot.stock_precision == ProductSourceOffer.StockPrecision.EXACT
    assert exact_snapshot.stock_quantity == 4
    assert unknown_snapshot.stock_precision == ProductSourceOffer.StockPrecision.BOOLEAN
    assert unknown_snapshot.stock_quantity is None


@pytest.mark.django_db
def test_same_product_keeps_offers_from_multiple_sources(product):
    for source, url in (
        ("zara", "https://www.zara.com/product-p1.html"),
        ("flo", "https://www.flo.com.tr/urun/product-1"),
    ):
        record_scraped_product_offers(
            product=product,
            scraped_product=ScrapedProduct(
                name="Merged product",
                url=url,
                external_id=f"{source}-1",
                source=source,
                is_available=True,
                stock_quantity=1000,
            ),
        )

    assert set(product.source_offers.values_list("parser_key", flat=True)) == {
        "zara",
        "flo",
    }


@pytest.mark.django_db
def test_integration_writer_is_feature_flagged_and_best_effort(
    product,
    settings,
    monkeypatch,
    caplog,
):
    scraped = ScrapedProduct(
        name="Feature-flag product",
        url="https://www.lcw.com/feature-flag-product",
        external_id="lcw-feature-flag",
        source="lcw",
    )
    session = SimpleNamespace(scraper_config=None)
    service = ScraperIntegrationService()
    calls = []

    def failing_writer(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("isolated writer failure")

    monkeypatch.setattr(
        "apps.scrapers.source_offers.record_scraped_product_offers",
        failing_writer,
    )

    settings.SOURCE_OFFER_RECORDING_ENABLED = False
    service._record_source_offers(session, scraped, product)
    assert calls == []

    settings.SOURCE_OFFER_RECORDING_ENABLED = True
    service._record_source_offers(session, scraped, product)

    assert len(calls) == 1
    assert calls[0]["product"] == product
    assert "dual-write failed" in caplog.text
