"""PostgreSQL integration checks for checkout locking and promo accounting."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
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
def test_crypto_checkout_commits_outbox_without_provider_call(checkout_state):
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
        HTTP_IDEMPOTENCY_KEY="crypto-checkout-0001",
    )
    force_authenticate(request, user=user)
    view = OrderViewSet.as_view({"post": "create_from_cart"})

    with patch(
        "apps.orders.views.CartSerializer",
        return_value=_cart_serializer(item.id),
    ), patch("apps.orders.views._create_crypto_invoice") as create_invoice, patch(
        "apps.payments.tasks.enqueue_crypto_invoice_request"
    ) as enqueue:
        response = view(request)

    from apps.payments.models import CryptoInvoiceRequest

    promo.refresh_from_db()
    assert response.status_code == 202
    assert response.data["payment_setup_status"] == "pending"
    assert promo.used_count == 1
    assert Order.objects.count() == 1
    invoice_request = CryptoInvoiceRequest.objects.get()
    assert CryptoInvoiceRequest.objects.count() == 1
    assert len(invoice_request.idempotency_key) == 64
    assert invoice_request.idempotency_key != "crypto-checkout-0001"
    assert CartItem.objects.filter(cart=cart).count() == 0
    create_invoice.assert_not_called()
    enqueue.assert_called_once_with(invoice_request.pk)

    detail_request = APIRequestFactory().get(
        f"/api/orders/orders/by-number/{invoice_request.order.number}/"
    )
    force_authenticate(detail_request, user=user)
    detail = OrderViewSet.as_view({"get": "by_number"})(
        detail_request,
        number=invoice_request.order.number,
    )
    assert detail.status_code == 200
    assert detail.data["payment_setup_status"] == "pending"
    assert "payment_data" not in detail.data


@pytest.mark.django_db(transaction=True)
def test_committed_crypto_checkout_retry_returns_same_order(checkout_state):
    user, _cart, item = checkout_state
    view = OrderViewSet.as_view({"post": "create_from_cart"})

    def submit():
        request = APIRequestFactory().post(
            "/api/orders/orders/create-from-cart/",
            _checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY="stable-crypto-checkout",
        )
        force_authenticate(request, user=user)
        return view(request)

    with patch(
        "apps.orders.views.CartSerializer",
        return_value=_cart_serializer(item.id),
    ), patch("apps.payments.tasks.enqueue_crypto_invoice_request") as enqueue:
        first = submit()
        second = submit()

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.data["number"] == second.data["number"]
    assert Order.objects.count() == 1
    enqueue.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_invalid_crypto_idempotency_key_is_rejected_before_checkout(checkout_state):
    user, _cart, _item = checkout_state
    request = APIRequestFactory().post(
        "/api/orders/orders/create-from-cart/",
        _checkout_payload(),
        format="json",
        HTTP_IDEMPOTENCY_KEY="contains spaces",
    )
    force_authenticate(request, user=user)

    response = OrderViewSet.as_view({"post": "create_from_cart"})(request)

    assert response.status_code == 400
    assert "idempotency_key" in response.data
    assert Order.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_checkout_creates_only_one_order(checkout_state):
    user, _cart, item = checkout_state
    entered_response = threading.Event()
    release_response = threading.Event()
    response_calls = 0
    response_lock = threading.Lock()

    from apps.orders import views as order_views

    real_checkout_response = order_views._crypto_checkout_response

    def slow_first_response(*args, **kwargs):
        nonlocal response_calls
        with response_lock:
            response_calls += 1
            is_first = response_calls == 1
        if is_first:
            entered_response.set()
            assert release_response.wait(timeout=5)
        return real_checkout_response(*args, **kwargs)

    def submit_checkout():
        request = APIRequestFactory().post(
            "/api/orders/orders/create-from-cart/",
            _checkout_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY="concurrent-crypto-checkout",
        )
        force_authenticate(request, user=user)
        response = OrderViewSet.as_view({"post": "create_from_cart"})(request)
        return response.status_code, response.data["number"]

    with patch(
        "apps.orders.views.CartSerializer",
        return_value=_cart_serializer(item.id),
    ), patch(
        "apps.orders.views._crypto_checkout_response",
        side_effect=slow_first_response,
    ), patch("apps.payments.tasks.enqueue_crypto_invoice_request") as enqueue:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(submit_checkout)
            assert entered_response.wait(timeout=5)
            second = executor.submit(submit_checkout)
            time.sleep(0.2)
            release_response.set()
            responses = [first.result(timeout=10), second.result(timeout=10)]

    assert sorted(status for status, _number in responses) == [202, 202]
    assert len({number for _status, number in responses}) == 1
    assert Order.objects.count() == 1
    enqueue.assert_called_once()
