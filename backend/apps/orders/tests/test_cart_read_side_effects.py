from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.models import Session
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory

from apps.orders.models import Cart
from apps.orders.serializers import CartSerializer
from apps.orders.views import (
    CartViewSet,
    _empty_cart_payload,
    _get_existing_cart_for_read,
)


class _ReadOnlySession(dict):
    def __init__(self, session_key: str | None = None):
        super().__init__()
        self.session_key = session_key
        self.save = Mock()


def _anonymous_request(*, cart_session: str = "", django_session_key: str | None = None):
    session = _ReadOnlySession(django_session_key)
    return SimpleNamespace(
        user=AnonymousUser(),
        META={"HTTP_X_CART_SESSION": cart_session} if cart_session else {},
        headers={"X-Cart-Session": cart_session} if cart_session else {},
        COOKIES={},
        session=session,
        query_params={},
    )


def test_anonymous_cart_read_without_identifier_does_not_save_session_or_create_cart():
    request = _anonymous_request()

    with (
        patch("apps.orders.views.Cart.objects.filter") as find_cart,
        patch("apps.orders.views.Cart.objects.get_or_create") as get_or_create_cart,
        patch("apps.orders.views.Cart.objects.create") as create_cart,
    ):
        cart = _get_existing_cart_for_read(request)

    assert cart is None
    request.session.save.assert_not_called()
    find_cart.assert_not_called()
    get_or_create_cart.assert_not_called()
    create_cart.assert_not_called()


def test_anonymous_cart_read_returns_only_an_existing_cart_session_without_creation():
    request = _anonymous_request(cart_session="existing-secure-cart-session")
    existing_cart = object()
    queryset = Mock()
    queryset.first.return_value = existing_cart
    queryset.order_by.return_value.first.return_value = existing_cart

    with (
        patch("apps.orders.views.Cart.objects.filter", return_value=queryset) as find_cart,
        patch("apps.orders.views.Cart.objects.get_or_create") as get_or_create_cart,
        patch("apps.orders.views.Cart.objects.create") as create_cart,
    ):
        cart = _get_existing_cart_for_read(request)

    assert cart is existing_cart
    assert "existing-secure-cart-session" in str(find_cart.call_args)
    request.session.save.assert_not_called()
    get_or_create_cart.assert_not_called()
    create_cart.assert_not_called()


def test_cart_list_uses_empty_payload_without_mutating_anonymous_session():
    expected = {
        "id": 0,
        "user": None,
        "session_key": "",
        "currency": "RUB",
        "items": [],
        "items_count": 0,
        "total_amount": 0.0,
        "discount_amount": 0.0,
        "final_amount": 0.0,
        "shipping_options": {"air": 0.0, "sea": 0.0, "ground": 0.0},
        "shipping_requires_quote": False,
        "free_shipping_threshold": None,
        "promo_code": None,
        "created_at": None,
        "updated_at": None,
    }
    request = APIRequestFactory().get(reverse("cart-list"))
    request.session = _ReadOnlySession()

    with (
        patch("apps.orders.views._get_existing_cart_for_read", return_value=None) as find_cart,
        patch("apps.orders.views._empty_cart_payload", return_value=expected) as empty_payload,
        patch("apps.orders.views._get_or_create_cart") as get_or_create_cart,
        patch("apps.orders.views.Cart.objects.get_or_create") as model_get_or_create,
    ):
        response = CartViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200
    assert response.data == expected
    find_cart.assert_called_once()
    empty_payload.assert_called_once()
    get_or_create_cart.assert_not_called()
    model_get_or_create.assert_not_called()
    request.session.save.assert_not_called()


def test_empty_cart_payload_keeps_the_cart_serializer_response_shape_without_database_access():
    request = SimpleNamespace(
        headers={"X-Currency": "USD"},
        query_params={},
        user=AnonymousUser(),
    )

    global_settings = SimpleNamespace(free_shipping_min_subtotal_usd=None)
    with patch(
        "apps.catalog.currency_models.GlobalCurrencySettings.load",
        return_value=global_settings,
    ):
        payload = _empty_cart_payload(request)

    assert set(payload) == set(CartSerializer.Meta.fields)
    assert payload["id"] == 0
    assert payload["user"] is None
    assert payload["session_key"] == ""
    assert payload["currency"] == "USD"
    assert payload["items"] == []
    assert payload["items_count"] == 0
    assert payload["total_amount"] == 0.0
    assert payload["discount_amount"] == 0.0
    assert payload["final_amount"] == 0.0
    assert payload["promo_code"] is None
    assert payload["created_at"] is None
    assert payload["updated_at"] is None


@pytest.mark.django_db
def test_anonymous_empty_cart_get_preserves_shape_without_session_or_cart_rows():
    cart_count = Cart.objects.count()
    django_session_count = Session.objects.count()

    response = APIClient().get(reverse("cart-list"))

    assert response.status_code == 200
    assert set(response.json()) == set(CartSerializer.Meta.fields)
    assert response.json()["items"] == []
    assert response.json()["items_count"] == 0
    assert response.json()["total_amount"] == 0.0
    assert Cart.objects.count() == cart_count
    assert Session.objects.count() == django_session_count


@pytest.mark.django_db
def test_anonymous_cart_get_reuses_existing_cart_session_without_new_rows():
    cart = Cart.objects.create(
        session_key="existing-integration-cart-session",
        currency="RUB",
    )
    cart_count = Cart.objects.count()
    django_session_count = Session.objects.count()

    response = APIClient().get(
        reverse("cart-list"),
        HTTP_X_CART_SESSION=cart.session_key,
    )

    assert response.status_code == 200
    assert response.json()["id"] == cart.id
    assert response.json()["session_key"] == cart.session_key
    assert response.json()["items"] == []
    assert Cart.objects.count() == cart_count
    assert Session.objects.count() == django_session_count
