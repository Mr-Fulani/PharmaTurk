from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.request import Request

from apps.catalog.models import Product, ProductSourceOffer
from apps.orders.cart_source_verification import CartOfferDecision
from apps.orders.models import Cart, CartItem, Order, OrderItem
from apps.orders.views import _checkout_source_preflight
from apps.scrapers.base.offers import (
    OfferAvailability,
    OfferCheckResult,
    OfferStockPrecision,
)
from apps.users.models import User


def _source_checkout_state(*, user=None):
    product = Product.objects.create(
        name="Checkout source product",
        slug=f"checkout-source-{uuid4().hex}",
        product_type="clothing",
        price=Decimal("100.00"),
        currency="TRY",
        stock_quantity=None,
    )
    offer = ProductSourceOffer.objects.create(
        product=product,
        parser_key="zara",
        canonical_url="https://www.zara.com/tr/tr/checkout-product-p1.html",
        external_product_id="supplier-product-1",
        external_sku="supplier-sku-1",
        variant_key="black",
        size_key="M",
        selected_options={"color": "black", "size": "M"},
        source_price=Decimal("90.00"),
        source_currency="TRY",
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.EXACT,
        stock_quantity=4,
    )
    cart = Cart.objects.create(
        user=user,
        session_key="" if user is not None else f"source-checkout-{uuid4().hex}",
        currency="TRY",
    )
    item = CartItem.objects.create(
        cart=cart,
        product=product,
        chosen_size="M",
        quantity=1,
        price=Decimal("100.00"),
        currency="TRY",
        source_offer=offer,
        verification_status=CartItem.VerificationStatus.VERIFIED,
        source_checked_at=timezone.now(),
        source_availability_status="in_stock",
        observed_source_price=Decimal("90.00"),
        observed_source_currency="TRY",
        observed_public_price=Decimal("100.00"),
        observed_public_currency="TRY",
        observed_stock_precision=CartItem.StockPrecision.EXACT,
        observed_stock_quantity=4,
        verified_quantity=1,
    )
    return product, offer, cart, item


def _decision(offer, *, source_price="90.00", public_price="100.00", issues=()):
    result = OfferCheckResult(
        availability_status=OfferAvailability.IN_STOCK,
        stock_precision=OfferStockPrecision.EXACT,
        stock_quantity=4,
        canonical_url=offer.canonical_url,
        source_price=Decimal(source_price),
        source_currency="TRY",
    )
    return CartOfferDecision(
        offer=offer,
        result=result,
        verification_status=CartItem.VerificationStatus.VERIFIED,
        issues=tuple(issues),
        payable=True,
        public_price=Decimal(public_price),
        public_currency="TRY",
        price_change_state=(
            CartItem.PriceChangeState.DECREASED
            if CartItem.VerificationIssue.SOURCE_PRICE_CHANGED in issues
            else CartItem.PriceChangeState.NONE
        ),
    )


def _checkout_payload():
    return {
        "contact_name": "Source Checkout",
        "contact_phone": "+905550000000",
        "contact_email": "source-checkout@example.test",
        "shipping_method": "ground",
        "payment_method": "cash",
        "locale": "ru",
    }


@pytest.mark.django_db(transaction=True)
def test_checkout_preflight_uses_saved_snapshot_without_supplier_call(settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True
    _product, offer, cart, _item = _source_checkout_state()
    request = APIRequestFactory().post("/api/orders/orders/create-from-cart/")

    with patch(
        "apps.orders.views.CartSourceOfferPolicy.evaluate",
    ) as evaluate:
        fingerprint, response = _checkout_source_preflight(request, cart)

    assert response is None
    assert fingerprint and len(fingerprint) == 64
    assert connection.in_atomic_block is False
    evaluate.assert_not_called()


@pytest.mark.django_db
def test_checkout_never_refreshes_a_saved_verified_price(settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True
    user = User.objects.create_user(
        username="source-price-drift-user",
        email="source-price-drift@example.test",
        password="not-used",
    )
    _product, offer, cart, item = _source_checkout_state(user=user)
    decision = _decision(
        offer,
        source_price="80.00",
        public_price="90.00",
        issues=[CartItem.VerificationIssue.SOURCE_PRICE_CHANGED],
    )
    client = APIClient()
    client.force_authenticate(user=user)

    with patch(
        "apps.orders.views.CartSourceOfferPolicy.evaluate",
        return_value=decision,
    ) as evaluate:
        response = client.post(
            reverse("orders-create-from-cart"),
            _checkout_payload(),
            format="json",
            HTTP_X_CURRENCY="TRY",
        )

    assert response.status_code == 201
    assert Order.objects.count() == 1
    assert not CartItem.objects.filter(cart=cart).exists()
    evaluate.assert_not_called()


@pytest.mark.django_db
def test_inconsistent_saved_stock_snapshot_stops_crypto_without_supplier_call(settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True
    user = User.objects.create_user(
        username="source-stock-drift-user",
        email="source-stock-drift@example.test",
        password="not-used",
    )
    _product, offer, _cart, item = _source_checkout_state(user=user)
    CartItem.objects.filter(pk=item.pk).update(quantity=5, verified_quantity=5)
    decision = _decision(
        offer,
        issues=[CartItem.VerificationIssue.SOURCE_QUANTITY_CHANGED],
    )
    client = APIClient()
    client.force_authenticate(user=user)
    payload = _checkout_payload()
    payload["payment_method"] = "crypto"

    with (
        patch(
            "apps.orders.views.CartSourceOfferPolicy.evaluate",
            return_value=decision,
        ) as evaluate,
        patch("apps.orders.views._create_crypto_invoice") as create_invoice,
    ):
        response = client.post(
            reverse("orders-create-from-cart"),
            payload,
            format="json",
            HTTP_X_CURRENCY="TRY",
        )

    assert response.status_code == 409
    assert response.json()["code"] == "cart_changed"
    create_invoice.assert_not_called()
    evaluate.assert_not_called()
    assert Order.objects.count() == 0
    item.refresh_from_db()
    assert item.quantity == 5


@pytest.mark.django_db
def test_locked_checkout_rejects_cart_change_after_preflight(settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = False
    user = User.objects.create_user(
        username="source-fingerprint-user",
        email="source-fingerprint@example.test",
        password="not-used",
    )
    _product, _offer, _cart, item = _source_checkout_state(user=user)
    client = APIClient()
    client.force_authenticate(user=user)

    from apps.orders import views as order_views

    real_preflight = order_views._checkout_source_preflight

    def mutate_after_preflight(request, cart):
        fingerprint, response = real_preflight(request, cart)
        CartItem.objects.filter(pk=item.pk).update(
            quantity=2,
            updated_at=timezone.now(),
        )
        return fingerprint, response

    with patch(
        "apps.orders.views._checkout_source_preflight",
        side_effect=mutate_after_preflight,
    ):
        response = client.post(
            reverse("orders-create-from-cart"),
            _checkout_payload(),
            format="json",
            HTTP_X_CURRENCY="TRY",
        )

    assert response.status_code == 409
    assert response.json()["operation_issues"][0]["code"] == "cart_changed"
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_order_item_keeps_immutable_source_snapshot(settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True
    settings.SOURCE_OFFER_RESERVATION_CAPABLE_SOURCES = []
    user = User.objects.create_user(
        username="source-snapshot-user",
        email="source-snapshot@example.test",
        password="not-used",
    )
    _product, offer, _cart, _item = _source_checkout_state(user=user)
    client = APIClient()
    client.force_authenticate(user=user)

    with patch(
        "apps.orders.views.CartSourceOfferPolicy.evaluate",
        return_value=_decision(offer),
    ) as evaluate:
        response = client.post(
            reverse("orders-create-from-cart"),
            _checkout_payload(),
            format="json",
            HTTP_X_CURRENCY="TRY",
        )

    assert response.status_code == 201
    order_item = OrderItem.objects.get()
    assert order_item.source_parser == "zara"
    assert order_item.source_url == offer.canonical_url
    assert order_item.source_external_sku == "supplier-sku-1"
    assert order_item.source_selected_options == {"color": "black", "size": "M"}
    assert order_item.source_price == Decimal("90.00")
    assert order_item.source_stock_precision == "exact"
    assert order_item.source_stock_quantity == 4
    assert order_item.supplier_confirmation_required is True
    evaluate.assert_not_called()

    ProductSourceOffer.objects.filter(pk=offer.pk).update(
        canonical_url="https://www.zara.com/tr/tr/changed-after-order.html",
        external_sku="changed-after-order",
    )
    order_item.refresh_from_db()
    assert order_item.source_url.endswith("checkout-product-p1.html")
    assert order_item.source_external_sku == "supplier-sku-1"


@pytest.mark.django_db
def test_akakce_order_snapshot_keeps_selected_procurement_seller(settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True
    settings.SOURCE_OFFER_RESERVATION_CAPABLE_SOURCES = []
    user = User.objects.create_user(
        username="akakce-source-snapshot-user",
        email="akakce-source-snapshot@example.test",
        password="not-used",
    )
    _product, offer, _cart, _item = _source_checkout_state(user=user)
    ProductSourceOffer.objects.filter(pk=offer.pk).update(
        parser_key="akakce",
        source_domain="www.akakce.com",
        canonical_url=(
            "https://www.akakce.com/vitamin-mineral/"
            "en-ucuz-supplement-fiyati,123.html"
        ),
        response_metadata={
            "seller_name": "Verified Seller",
            "seller_url": "https://seller.example/supplement",
            "market_product_name": "Matched supplement",
            "market_product_id": "123",
        },
    )
    offer.refresh_from_db()
    client = APIClient()
    client.force_authenticate(user=user)

    with patch(
        "apps.orders.views.CartSourceOfferPolicy.evaluate",
        return_value=_decision(offer),
    ) as evaluate:
        response = client.post(
            reverse("orders-create-from-cart"),
            _checkout_payload(),
            format="json",
            HTTP_X_CURRENCY="TRY",
        )

    assert response.status_code == 201
    procurement = OrderItem.objects.get().source_selected_options["procurement_offer"]
    assert procurement == {
        "seller_name": "Verified Seller",
        "seller_url": "https://seller.example/supplement",
        "market_product_name": "Matched supplement",
        "market_product_id": "123",
    }
    evaluate.assert_not_called()


@pytest.mark.django_db
def test_checkout_rejects_supplement_that_never_opened_cart(settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True
    settings.SOURCE_OFFER_CART_REQUIRED_PRODUCT_TYPES = ["supplements"]
    settings.SUPPLEMENT_STOCK_ADAPTER_SOURCES = []
    product = Product.objects.create(
        name="Legacy supplement",
        slug=f"legacy-supplement-{uuid4().hex}",
        product_type="supplements",
        price=Decimal("49.70"),
        currency="TRY",
        is_available=True,
        stock_quantity=3,
    )
    cart = Cart.objects.create(session_key=f"legacy-supplement-{uuid4().hex}", currency="TRY")
    item = CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("57.16"),
        currency="TRY",
    )
    request = Request(APIRequestFactory().post("/api/orders/orders/create-from-cart/"))

    fingerprint, response = _checkout_source_preflight(request, cart)

    assert fingerprint is None
    assert response.status_code == 409
    item.refresh_from_db()
    assert item.verification_status == CartItem.VerificationStatus.NOT_CHECKED
    assert item.verification_issues == []
    assert item.is_payable is False


@pytest.mark.django_db
def test_checkout_creates_manual_fulfilment_supplement_order_with_zero_stock(settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True
    settings.SOURCE_OFFER_CART_REQUIRED_PRODUCT_TYPES = ["supplements"]
    settings.SUPPLEMENT_STOCK_ADAPTER_SOURCES = []
    user = User.objects.create_user(
        username="availability-optional-supplement-user",
        email="availability-optional-supplement@example.test",
        password="not-used",
    )
    product = Product.objects.create(
        name="Zero-stock supplement",
        slug=f"zero-stock-supplement-{uuid4().hex}",
        product_type="supplements",
        price=Decimal("49.70"),
        currency="TRY",
        is_available=False,
        stock_quantity=0,
    )
    cart = Cart.objects.create(user=user, currency="TRY")
    CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=2,
        price=Decimal("57.16"),
        currency="TRY",
    )
    client = APIClient()
    client.force_authenticate(user=user)

    opened = client.post(
        reverse("cart-revalidate"),
        {},
        format="json",
        HTTP_X_CURRENCY="TRY",
    )
    assert opened.status_code == 200

    response = client.post(
        reverse("orders-create-from-cart"),
        _checkout_payload(),
        format="json",
        HTTP_X_CURRENCY="TRY",
    )

    assert response.status_code == 201
    order_item = OrderItem.objects.get()
    assert order_item.product == product
    assert order_item.quantity == 2
    assert order_item.supplier_confirmation_required is True
    product.refresh_from_db()
    assert product.stock_quantity == 0
    assert product.is_available is False
    assert not CartItem.objects.filter(cart=cart).exists()
