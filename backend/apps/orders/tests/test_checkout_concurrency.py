"""PostgreSQL integration checks for checkout locking and promo accounting."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.catalog.models import Product
from apps.orders.models import Cart, CartItem, Order, PromoCode
from apps.orders.views import OrderViewSet
from apps.users.models import User


def _checkout_payload(*, promo_code=""):
    return {
        "contact_name": "Checkout Test",
        "contact_phone": "+905550000000",
        "contact_email": "checkout@example.com",
        "shipping_method": "ground",
        "payment_method": "crypto",
        "promo_code": promo_code,
        "locale": "ru",
    }


def _cart_serializer(item_id):
    serializer = MagicMock()
    serializer.get_currency.return_value = "RUB"
    serializer.get_total_amount.return_value = Decimal("100.00")
    serializer.get_shipping_options.return_value = {"air": 0, "sea": 0, "ground": 0}
    serializer.data = {"items": [{"id": item_id, "price": "100.00"}]}
    return serializer


def _invoice():
    expires_at = timezone.now() + timezone.timedelta(minutes=30)
    return {
        "invoice_id": "invoice-checkout-lock",
        "address": "test-address",
        "amount": "10.0",
        "amount_usd": "100.0",
        "expires_at": expires_at,
        "qr_code": "",
        "invoice_url": "",
    }, {"address": "test-address"}


@pytest.fixture
def checkout_state():
    user = User.objects.create_user(
        username="checkout-user",
        email="checkout@example.com",
        password="not-used-in-test",
    )
    product = Product.objects.create(
        name="Checkout Product",
        slug="checkout-product",
        price=Decimal("100.00"),
        currency="RUB",
        stock_quantity=10,
    )
    cart = Cart.objects.create(user=user, currency="RUB")
    item = CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("100.00"),
        currency="RUB",
    )
    return user, cart, item


@pytest.mark.django_db(transaction=True)
def test_failed_crypto_invoice_does_not_consume_promo(checkout_state):
    user, cart, item = checkout_state
    promo = PromoCode.objects.create(
        code="SAFE10",
        discount_type=PromoCode.DiscountType.PERCENT,
        discount_value=Decimal("10"),
        max_uses=1,
    )
    request = APIRequestFactory().post(
        "/api/orders/orders/create-from-cart/",
        _checkout_payload(promo_code=promo.code),
        format="json",
    )
    force_authenticate(request, user=user)
    view = OrderViewSet.as_view({"post": "create_from_cart"})

    with patch(
        "apps.orders.serializers.CartSerializer",
        return_value=_cart_serializer(item.id),
    ), patch("apps.orders.views._create_crypto_invoice", return_value=(None, None)):
        response = view(request)

    promo.refresh_from_db()
    assert response.status_code == 503
    assert promo.used_count == 0
    assert Order.objects.count() == 0
    assert CartItem.objects.filter(cart=cart).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_checkout_creates_only_one_order(checkout_state):
    user, _cart, item = checkout_state
    entered_provider = threading.Event()
    release_provider = threading.Event()

    def slow_invoice(*args, **kwargs):
        entered_provider.set()
        assert release_provider.wait(timeout=5)
        return _invoice()

    def submit_checkout():
        request = APIRequestFactory().post(
            "/api/orders/orders/create-from-cart/",
            _checkout_payload(),
            format="json",
        )
        force_authenticate(request, user=user)
        return OrderViewSet.as_view({"post": "create_from_cart"})(request).status_code

    with patch(
        "apps.orders.serializers.CartSerializer",
        return_value=_cart_serializer(item.id),
    ), patch("apps.orders.views._create_crypto_invoice", side_effect=slow_invoice), patch(
        "apps.orders.views.OrderSerializer"
    ) as order_serializer:
        order_serializer.return_value.data = {"id": 1}
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(submit_checkout)
            assert entered_provider.wait(timeout=5)
            second = executor.submit(submit_checkout)
            time.sleep(0.2)
            release_provider.set()
            statuses = sorted([first.result(timeout=10), second.result(timeout=10)])

    assert statuses == [201, 400]
    assert Order.objects.count() == 1
