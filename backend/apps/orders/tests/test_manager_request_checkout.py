"""Оформление в режиме «заявка менеджеру»: онлайн-оплата выключена."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.catalog.models import Product
from apps.orders.models import Cart, CartItem, Order
from apps.orders.views import OrderViewSet
from apps.users.models import User


def _payload(**overrides):
    payload = {
        "contact_name": "Request Test",
        "contact_phone": "+905550000001",
        "contact_email": "request@example.com",
        "contact_channel": "telegram",
        "shipping_method": "ground",
        "locale": "ru",
    }
    payload.update(overrides)
    return payload


def _cart_serializer(item_id):
    serializer = MagicMock()
    serializer.get_currency.return_value = "RUB"
    serializer.get_total_amount.return_value = Decimal("100.00")
    serializer.get_shipping_options.return_value = {"air": 0, "sea": 0, "ground": 0}
    serializer.data = {"items": [{"id": item_id, "price": "100.00"}]}
    return serializer


@pytest.fixture
def request_state(settings):
    settings.ORDER_ONLINE_PAYMENTS_ENABLED = False
    user = User.objects.create_user(
        username="request-user",
        email="request@example.com",
        password="not-used-in-test",
    )
    product = Product.objects.create(
        name="Request Product",
        slug="request-product",
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
    return user, item


def _post(user, item, payload):
    request = APIRequestFactory().post(
        "/api/orders/orders/create-from-cart/",
        payload,
        format="json",
    )
    force_authenticate(request, user=user)
    view = OrderViewSet.as_view({"post": "create_from_cart"})
    with patch(
        "apps.orders.views.CartSerializer",
        return_value=_cart_serializer(item.id),
    ), patch("apps.orders.views._create_crypto_invoice") as create_invoice:
        response = view(request)
    create_invoice.assert_not_called()
    return response


@pytest.mark.django_db(transaction=True)
def test_request_checkout_creates_manager_order_with_contact_channel(request_state):
    user, item = request_state

    response = _post(user, item, _payload(payment_method="cod"))

    assert response.status_code == 201, response.data
    order = Order.objects.get()
    assert order.payment_method == "manager"
    assert order.status == Order.OrderStatus.NEW
    assert order.contact_channel == "telegram"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("method", ["crypto", "card"])
def test_online_payment_is_rejected_while_disabled(request_state, method):
    user, item = request_state

    response = _post(user, item, _payload(payment_method=method))

    assert response.status_code == 400
    assert "payment_method" in response.data
    assert Order.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_unknown_contact_channel_is_rejected(request_state):
    user, item = request_state

    response = _post(user, item, _payload(contact_channel="pigeon"))

    assert response.status_code == 400
    assert "contact_channel" in response.data
    assert Order.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_email_channel_requires_email(request_state):
    user, item = request_state

    response = _post(user, item, _payload(contact_channel="email", contact_email=""))

    assert response.status_code == 400
    assert "contact_email" in response.data
    assert Order.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_telegram_username_is_normalized_and_saved(request_state):
    user, item = request_state

    response = _post(user, item, _payload(contact_channel="telegram", contact_username=" @Ivan_Petrov "))

    assert response.status_code == 201, response.data
    assert Order.objects.get().contact_username == "Ivan_Petrov"


@pytest.mark.django_db(transaction=True)
def test_invalid_telegram_username_is_rejected(request_state):
    user, item = request_state

    response = _post(user, item, _payload(contact_username="no spaces!"))

    assert response.status_code == 400
    assert "contact_username" in response.data
    assert Order.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_whatsapp_username_is_saved(request_state):
    user, item = request_state

    response = _post(user, item, _payload(contact_channel="whatsapp", contact_username="@ivan.p"))

    assert response.status_code == 201, response.data
    assert Order.objects.get().contact_username == "ivan.p"


@pytest.mark.django_db(transaction=True)
def test_username_is_dropped_for_phone_channel(request_state):
    user, item = request_state

    response = _post(user, item, _payload(contact_channel="phone", contact_username="ivan_petrov"))

    assert response.status_code == 201, response.data
    assert Order.objects.get().contact_username == ""


@pytest.mark.django_db(transaction=True)
def test_whatsapp_phone_number_is_accepted_as_contact(request_state):
    user, item = request_state

    response = _post(user, item, _payload(contact_channel="whatsapp", contact_username="+79990001122"))

    assert response.status_code == 201, response.data
    assert Order.objects.get().contact_username == "+79990001122"


@pytest.fixture
def guest_cart(settings):
    settings.ORDER_ONLINE_PAYMENTS_ENABLED = False
    product = Product.objects.create(
        name="Guest Product",
        slug="guest-product",
        price=Decimal("100.00"),
        currency="RUB",
        stock_quantity=10,
    )
    cart = Cart.objects.create(user=None, session_key="guest-cart-session", currency="RUB")
    return CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("100.00"),
        currency="RUB",
    )


def _post_as_guest(item, payload, session_key="guest-cart-session"):
    request = APIRequestFactory().post(
        "/api/orders/orders/create-from-cart/",
        payload,
        format="json",
        HTTP_X_CART_SESSION=session_key,
    )
    view = OrderViewSet.as_view({"post": "create_from_cart"})
    with patch(
        "apps.orders.views.CartSerializer",
        return_value=_cart_serializer(item.id),
    ), patch("apps.orders.views._create_crypto_invoice") as create_invoice:
        response = view(request)
    create_invoice.assert_not_called()
    return response


@pytest.mark.django_db(transaction=True)
def test_guest_sends_request_from_own_cart_without_account(guest_cart):
    response = _post_as_guest(guest_cart, _payload(contact_email=""))

    assert response.status_code == 201, response.data
    order = Order.objects.get()
    assert order.user is None
    assert order.contact_name == "Request Test"
    assert order.contact_phone == "+905550000001"
    assert order.payment_method == "manager"
    assert order.status == Order.OrderStatus.NEW


@pytest.mark.django_db(transaction=True)
def test_guest_without_cart_session_gets_empty_cart(guest_cart):
    response = _post_as_guest(guest_cart, _payload(), session_key="someone-else")

    assert response.status_code == 400
    assert Order.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_guest_needs_name_and_phone(guest_cart):
    response = _post_as_guest(guest_cart, _payload(contact_name="", contact_phone=""))

    assert response.status_code == 400
    assert "contact_name" in response.data
    assert "contact_phone" in response.data
    assert Order.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_guest_cannot_use_saved_address_ids(guest_cart):
    response = _post_as_guest(guest_cart, _payload(shipping_address=1, shipping_address_text="Москва, Тверская 1"))

    assert response.status_code == 201, response.data
    order = Order.objects.get()
    assert order.shipping_address is None
    assert order.shipping_address_text == "Москва, Тверская 1"
