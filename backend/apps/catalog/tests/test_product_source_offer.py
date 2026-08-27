from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.catalog.models import Product, ProductSourceOffer


@pytest.fixture
def product(db):
    return Product.objects.create(
        name="Source offer product",
        slug="source-offer-product",
        product_type="clothing",
    )


@pytest.mark.django_db
def test_source_offer_normalizes_identity_and_preserves_exact_stock(product):
    offer = ProductSourceOffer.objects.create(
        product=product,
        parser_key=" ZARA ",
        canonical_url="https://www.zara.com/tr/en/product-p012345.html",
        external_product_id="012345",
        external_sku="012345-M",
        variant_key="black",
        size_key="M",
        selected_options={"color": "Black", "size": "M"},
        source_price=Decimal("1299.90"),
        source_currency="try",
        availability_status=ProductSourceOffer.AvailabilityStatus.LIMITED,
        stock_precision=ProductSourceOffer.StockPrecision.EXACT,
        stock_quantity=2,
    )

    assert offer.parser_key == "zara"
    assert offer.source_domain == "www.zara.com"
    assert offer.source_currency == "TRY"
    assert len(offer.offer_key) == 64
    assert offer.stock_quantity == 2
    assert product.source_offers.get() == offer


@pytest.mark.django_db
def test_source_offer_identity_is_stable_but_size_specific(product):
    common = {
        "product": product,
        "parser_key": "flo",
        "canonical_url": "https://www.flo.com.tr/urun/example",
        "external_product_id": "flo-100",
        "variant_key": "black",
        "availability_status": ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        "stock_precision": ProductSourceOffer.StockPrecision.BOOLEAN,
    }
    medium = ProductSourceOffer.objects.create(**common, size_key="M")
    large = ProductSourceOffer.objects.create(**common, size_key="L")

    assert medium.offer_key != large.offer_key

    with pytest.raises(IntegrityError), transaction.atomic():
        ProductSourceOffer.objects.create(**common, size_key="M")


@pytest.mark.django_db
def test_source_offer_rejects_synthetic_quantity_for_boolean_stock(product):
    offer = ProductSourceOffer(
        product=product,
        parser_key="lcw",
        canonical_url="https://www.lcw.com/example",
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
        stock_quantity=1000,
    )

    with pytest.raises(ValidationError, match="Количество допустимо только"):
        offer.full_clean()


@pytest.mark.django_db
def test_source_offer_requires_zero_exact_stock_when_out_of_stock(product):
    offer = ProductSourceOffer(
        product=product,
        parser_key="ikea",
        canonical_url="https://www.ikea.com.tr/urun/example",
        availability_status=ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.EXACT,
        stock_quantity=1,
    )

    with pytest.raises(ValidationError, match="должен быть нулевым"):
        offer.full_clean()
