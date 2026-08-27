from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.models import Product, ProductSourceOffer


@pytest.fixture
def historical_product(db):
    return Product.objects.create(
        name="Historical scraper product",
        slug="historical-scraper-product",
        price="199.90",
        currency="TRY",
        external_id="lcw-historical-1",
        external_url="https://www.lcw.com/historical-1",
        stock_quantity=1000,
        external_data={
            "source": "lcw",
            "scraped_sources": [
                {
                    "source": "lcw",
                    "url": "https://www.lcw.com/historical-1",
                    "price": 199.9,
                }
            ],
        },
    )


@pytest.mark.django_db
def test_backfill_source_offers_is_dry_run_by_default(historical_product):
    stdout = StringIO()

    call_command("backfill_source_offers", limit=10, batch_size=2, stdout=stdout)

    assert "mode=DRY-RUN" in stdout.getvalue()
    assert "offers=1" in stdout.getvalue()
    assert ProductSourceOffer.objects.count() == 0


@pytest.mark.django_db
def test_backfill_source_offers_apply_is_idempotent(historical_product):
    for _ in range(2):
        call_command(
            "backfill_source_offers",
            apply=True,
            source="lcw",
            limit=10,
            batch_size=2,
            stdout=StringIO(),
        )

    offer = ProductSourceOffer.objects.get(product=historical_product)
    assert offer.parser_key == "lcw"
    assert offer.stock_precision == ProductSourceOffer.StockPrecision.BOOLEAN
    assert offer.stock_quantity is None
