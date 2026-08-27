from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.urls import reverse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView

from apps.orders.models import Cart, PromoCode
from apps.orders.throttles import CART_MUTATION_THROTTLES
from apps.orders.views import CartViewSet


class _ReadOnlySession(dict):
    def __init__(self, session_key: str | None = None):
        super().__init__()
        self.session_key = session_key
        self.save = Mock()


class _MutationThrottleProbe(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = CART_MUTATION_THROTTLES

    def post(self, request):
        return Response({"status": "ok"})


def _raw_post(
    url_name: str,
    data=None,
    *,
    cart_session: str = "",
    url_kwargs=None,
):
    request = APIRequestFactory().post(
        reverse(url_name, kwargs=url_kwargs),
        data or {},
        format="json",
        REMOTE_ADDR="203.0.113.70",
        HTTP_X_CART_SESSION=cart_session,
    )
    request.session = _ReadOnlySession()
    return request


def _throttle_request(*, user, real_ip: str, remote_addr: str, forwarded_for: str):
    return SimpleNamespace(
        user=user,
        META={
            "HTTP_X_REAL_IP": real_ip,
            "REMOTE_ADDR": remote_addr,
            "HTTP_X_FORWARDED_FOR": forwarded_for,
        },
    )


def test_every_cart_mutation_action_uses_the_explicit_throttle_set():
    assert {throttle.rate for throttle in CART_MUTATION_THROTTLES} == {
        "60/min",
        "1000/day",
    }
    for action_name in (
        "add",
        "update_item",
        "acknowledge_price",
        "revalidate",
        "remove_item",
        "clear",
        "apply_promo",
        "remove_promo",
    ):
        action = getattr(CartViewSet, action_name)
        assert action.kwargs["throttle_classes"] == CART_MUTATION_THROTTLES


def test_cart_mutation_throttles_use_trusted_ip_for_anonymous_and_user_for_authenticated():
    throttle = CART_MUTATION_THROTTLES[0]()
    anonymous = AnonymousUser()
    first_anonymous_key = throttle.get_cache_key(
        _throttle_request(
            user=anonymous,
            real_ip="203.0.113.71",
            remote_addr="172.18.0.2",
            forwarded_for="198.51.100.1",
        ),
        None,
    )
    rotated_xff_key = throttle.get_cache_key(
        _throttle_request(
            user=anonymous,
            real_ip="203.0.113.71",
            remote_addr="172.18.0.2",
            forwarded_for="198.51.100.250",
        ),
        None,
    )

    assert first_anonymous_key == rotated_xff_key
    assert "203.0.113.71" in first_anonymous_key
    assert "198.51.100" not in first_anonymous_key

    authenticated = SimpleNamespace(is_authenticated=True, pk=4242)
    first_user_key = throttle.get_cache_key(
        _throttle_request(
            user=authenticated,
            real_ip="203.0.113.72",
            remote_addr="172.18.0.2",
            forwarded_for="198.51.100.2",
        ),
        None,
    )
    changed_ip_user_key = throttle.get_cache_key(
        _throttle_request(
            user=authenticated,
            real_ip="203.0.113.73",
            remote_addr="172.18.0.3",
            forwarded_for="198.51.100.3",
        ),
        None,
    )

    assert first_user_key == changed_ip_user_key
    assert "4242" in first_user_key
    assert "203.0.113" not in first_user_key


def test_cart_mutation_burst_limit_returns_real_429_and_xff_rotation_does_not_bypass_it():
    burst_class = next(
        throttle for throttle in CART_MUTATION_THROTTLES if throttle.rate.endswith("/min")
    )
    request_limit, _ = burst_class().parse_rate(burst_class.rate)
    factory = APIRequestFactory()
    view = _MutationThrottleProbe.as_view()
    cache.clear()

    responses = [
        view(
            factory.post(
                "/cart-mutation-throttle-probe/",
                {},
                format="json",
                HTTP_X_REAL_IP="203.0.113.74",
                HTTP_X_FORWARDED_FOR=f"198.51.100.{index + 1}",
                REMOTE_ADDR="172.18.0.2",
            )
        )
        for index in range(request_limit + 1)
    ]

    assert all(response.status_code == 200 for response in responses[:-1])
    assert responses[-1].status_code == 429


@pytest.mark.parametrize(
    ("action_name", "url_name"),
    (("clear", "cart-clear"), ("remove_promo", "cart-remove-promo")),
)
def test_idempotent_cart_mutation_without_existing_cart_does_not_create_rows(
    action_name,
    url_name,
):
    request = _raw_post(url_name, cart_session="definitely-not-an-existing-cart")
    empty_payload = {"id": 0, "items": [], "items_count": 0}

    with (
        patch("apps.orders.views._get_existing_cart_for_mutation", return_value=None),
        patch("apps.orders.views._empty_cart_payload", return_value=empty_payload),
        patch("apps.orders.views._get_or_create_cart") as get_or_create_cart,
        patch("apps.orders.views.Cart.objects.get_or_create") as model_get_or_create,
        patch("apps.orders.views.Cart.objects.create") as model_create,
    ):
        response = CartViewSet.as_view({"post": action_name})(request)

    assert response.status_code == 200
    assert response.data == empty_payload
    get_or_create_cart.assert_not_called()
    model_get_or_create.assert_not_called()
    model_create.assert_not_called()
    request.session.save.assert_not_called()


@pytest.mark.parametrize(
    ("action_name", "url_name", "data", "url_kwargs"),
    (
        ("add", "cart-add", {}, None),
        ("update_item", "cart-update-item", {"quantity": 0}, {"pk": 999}),
    ),
)
def test_invalid_item_mutation_is_rejected_before_cart_or_session_creation(
    action_name,
    url_name,
    data,
    url_kwargs,
):
    request = _raw_post(url_name, data=data, url_kwargs=url_kwargs)

    with (
        patch("apps.orders.views._get_existing_cart_for_mutation") as find_cart,
        patch("apps.orders.views._get_or_create_cart") as get_or_create_cart,
        patch("apps.orders.views.Cart.objects.get_or_create") as model_get_or_create,
        patch("apps.orders.views.Cart.objects.create") as model_create,
    ):
        response = CartViewSet.as_view({"post": action_name})(
            request,
            **(url_kwargs or {}),
        )

    assert response.status_code == 400
    find_cart.assert_not_called()
    get_or_create_cart.assert_not_called()
    model_get_or_create.assert_not_called()
    model_create.assert_not_called()
    request.session.save.assert_not_called()


def test_apply_promo_rejects_invalid_payload_before_cart_creation_or_lookup():
    request = _raw_post("cart-apply-promo", data={})

    with (
        patch("apps.orders.views._get_existing_cart_for_mutation") as find_cart,
        patch("apps.orders.views._get_or_create_cart") as get_or_create_cart,
        patch("apps.orders.views.Cart.objects.get_or_create") as model_get_or_create,
        patch("apps.orders.views.Cart.objects.create") as model_create,
    ):
        response = CartViewSet.as_view({"post": "apply_promo"})(request)

    assert response.status_code == 400
    find_cart.assert_not_called()
    get_or_create_cart.assert_not_called()
    model_get_or_create.assert_not_called()
    model_create.assert_not_called()
    request.session.save.assert_not_called()


def test_apply_valid_promo_without_existing_cart_returns_404_without_creation():
    request = _raw_post("cart-apply-promo", data={"code": "VALID"})
    serializer = Mock()
    serializer.is_valid.return_value = True
    serializer.validated_data = {"code": "VALID"}

    with (
        patch("apps.orders.views.ApplyPromoCodeSerializer", return_value=serializer),
        patch("apps.orders.views._get_existing_cart_for_mutation", return_value=None),
        patch("apps.orders.views._get_or_create_cart") as get_or_create_cart,
        patch("apps.orders.views.PromoCode.objects.get") as get_promo,
        patch("apps.orders.views.Cart.objects.get_or_create") as model_get_or_create,
        patch("apps.orders.views.Cart.objects.create") as model_create,
    ):
        response = CartViewSet.as_view({"post": "apply_promo"})(request)

    assert response.status_code == 404
    get_promo.assert_not_called()
    get_or_create_cart.assert_not_called()
    model_get_or_create.assert_not_called()
    model_create.assert_not_called()
    request.session.save.assert_not_called()


@pytest.mark.django_db
def test_noop_clear_and_remove_promo_do_not_create_cart_or_django_session_rows():
    cart_count = Cart.objects.count()
    django_session_count = Session.objects.count()
    client = APIClient()

    clear_response = client.post(
        reverse("cart-clear"),
        {},
        format="json",
        HTTP_X_CART_SESSION="missing-clear-cart",
        HTTP_X_REAL_IP="203.0.113.75",
    )
    remove_response = client.post(
        reverse("cart-remove-promo"),
        {},
        format="json",
        HTTP_X_CART_SESSION="missing-remove-promo-cart",
        HTTP_X_REAL_IP="203.0.113.76",
    )

    assert clear_response.status_code == 200
    assert remove_response.status_code == 200
    assert Cart.objects.count() == cart_count
    assert Session.objects.count() == django_session_count


@pytest.mark.django_db
def test_invalid_or_cartless_apply_promo_does_not_create_cart_or_django_session_rows():
    promo = PromoCode.objects.create(code="SAFE-NO-CART", discount_value=10)
    cart_count = Cart.objects.count()
    django_session_count = Session.objects.count()
    client = APIClient()

    invalid_response = client.post(
        reverse("cart-apply-promo"),
        {},
        format="json",
        HTTP_X_REAL_IP="203.0.113.77",
    )
    cartless_response = client.post(
        reverse("cart-apply-promo"),
        {"code": promo.code},
        format="json",
        HTTP_X_CART_SESSION="missing-apply-promo-cart",
        HTTP_X_REAL_IP="203.0.113.78",
    )

    assert invalid_response.status_code == 400
    assert cartless_response.status_code == 404
    assert Cart.objects.count() == cart_count
    assert Session.objects.count() == django_session_count
