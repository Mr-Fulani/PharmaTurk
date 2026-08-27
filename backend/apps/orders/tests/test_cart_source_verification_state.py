from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import Product, ProductSourceOffer
from apps.orders.models import Cart, CartItem


@pytest.fixture
def cart_product(db):
    product = Product.objects.create(
        name="Cart verification product",
        slug=f"cart-verification-{uuid4().hex}",
        product_type="clothing",
    )
    cart = Cart.objects.create(session_key=f"cart-{uuid4().hex}")
    return cart, product


def _item(cart, product, **overrides):
    values = {
        "cart": cart,
        "product": product,
        "quantity": 1,
        "price": Decimal("100.00"),
        "currency": "TRY",
    }
    values.update(overrides)
    return CartItem(**values)


@pytest.mark.django_db
def test_legacy_cart_item_defaults_remain_payable_compatible(cart_product):
    cart, product = cart_product

    item = CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("100.00"),
        currency="TRY",
    )

    assert item.source_offer_id is None
    assert item.verification_status == CartItem.VerificationStatus.NOT_CHECKED
    assert item.verification_issues == []
    assert item.observed_stock_precision == CartItem.StockPrecision.UNKNOWN
    assert item.observed_stock_quantity is None
    assert item.observed_public_price is None
    assert item.observed_public_currency == ""
    assert item.price_change_state == CartItem.PriceChangeState.NONE


@pytest.mark.django_db
def test_cart_item_rejects_synthetic_quantity_for_non_exact_stock(cart_product):
    cart, product = cart_product
    item = _item(
        cart,
        product,
        observed_stock_precision=CartItem.StockPrecision.BOOLEAN,
        observed_stock_quantity=1000,
    )

    with pytest.raises(ValidationError, match="Количество допустимо только"):
        item.full_clean()

    with pytest.raises(IntegrityError), transaction.atomic():
        CartItem.objects.create(
            cart=cart,
            product=product,
            quantity=1,
            price=Decimal("100.00"),
            currency="TRY",
            observed_stock_precision=CartItem.StockPrecision.BOOLEAN,
            observed_stock_quantity=1000,
        )


@pytest.mark.django_db
def test_cart_item_exact_stock_requires_quantity(cart_product):
    cart, product = cart_product
    item = _item(
        cart,
        product,
        observed_stock_precision=CartItem.StockPrecision.EXACT,
    )

    with pytest.raises(ValidationError, match="Для точного остатка требуется"):
        item.full_clean()


@pytest.mark.django_db
def test_price_acknowledgement_is_bound_to_time_value_and_currency(cart_product):
    cart, product = cart_product
    item = _item(
        cart,
        product,
        price_change_state=CartItem.PriceChangeState.INCREASED,
        price_acknowledged_at=timezone.now(),
    )

    with pytest.raises(ValidationError, match="время, сумму и валюту"):
        item.full_clean()

    item.price_acknowledged_value = Decimal("110.00")
    item.price_acknowledged_currency = "TRY"
    item.full_clean()


@pytest.mark.django_db
def test_deleting_offer_preserves_cart_verification_snapshot(cart_product, settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True
    cart, product = cart_product
    checked_at = timezone.now() - timedelta(seconds=5)
    offer = ProductSourceOffer.objects.create(
        product=product,
        parser_key="zara",
        canonical_url="https://www.zara.com/tr/tr/product-p1.html",
        external_product_id="p1",
        source_price=Decimal("90.00"),
        source_currency="TRY",
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
    )
    item = CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("100.00"),
        currency="TRY",
        source_offer=offer,
        verification_status=CartItem.VerificationStatus.VERIFIED,
        source_checked_at=checked_at,
        source_availability_status="in_stock",
        observed_source_price=Decimal("90.00"),
        observed_source_currency="TRY",
        observed_public_price=Decimal("100.00"),
        observed_public_currency="TRY",
        observed_stock_precision=CartItem.StockPrecision.BOOLEAN,
        verified_quantity=1,
    )

    offer.delete()

    item.refresh_from_db()
    assert item.source_offer_id is None
    assert item.verification_status == CartItem.VerificationStatus.VERIFIED
    assert item.source_checked_at == checked_at
    assert item.observed_source_price == Decimal("90.00")
    assert item.observed_source_currency == "TRY"
    assert item.observed_public_price == Decimal("100.00")
    assert item.observed_public_currency == "TRY"
    assert item.is_payable is True


@pytest.mark.django_db
def test_deleting_offer_does_not_unblock_a_blocked_snapshot(cart_product, settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True
    cart, product = cart_product
    offer = ProductSourceOffer.objects.create(
        product=product,
        parser_key="zara",
        canonical_url="https://www.zara.com/tr/tr/product-p2.html",
        external_product_id="p2",
    )
    item = CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("100.00"),
        currency="TRY",
        source_offer=offer,
        verification_status=CartItem.VerificationStatus.BLOCKED,
        verification_issues=[CartItem.VerificationIssue.SOURCE_OUT_OF_STOCK],
    )

    offer.delete()

    item.refresh_from_db()
    assert item.source_offer_id is None
    assert item.is_payable is False
