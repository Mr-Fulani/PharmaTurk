from contextlib import nullcontext
from unittest.mock import patch

import pytest
from django.db import IntegrityError, models, transaction

from apps.orders.models import Cart
from apps.orders.views import _get_or_create_cart_record
from apps.users.models import User


def _unique_constraint_for(*fields):
    expected = tuple(fields)
    return next(
        (
            constraint
            for constraint in Cart._meta.constraints
            if isinstance(constraint, models.UniqueConstraint)
            and tuple(constraint.fields) == expected
        ),
        None,
    )


def test_cart_model_declares_partial_uniqueness_for_user_and_anonymous_session():
    user_constraint = _unique_constraint_for("user")
    session_constraint = _unique_constraint_for("session_key")

    assert user_constraint is not None
    assert user_constraint.condition == models.Q(user__isnull=False)
    assert session_constraint is not None
    assert session_constraint.condition == models.Q(user__isnull=True)


def test_cart_creation_recovers_the_row_created_by_a_concurrent_winner():
    concurrent_cart = object()

    with (
        patch("apps.orders.views.transaction.atomic", return_value=nullcontext()),
        patch(
            "apps.orders.views.Cart.objects.get_or_create",
            side_effect=IntegrityError("duplicate cart identity"),
        ),
        patch(
            "apps.orders.views.Cart.objects.get",
            return_value=concurrent_cart,
        ) as get_cart,
    ):
        cart, created = _get_or_create_cart_record(
            user=None,
            session_key="concurrent-cart-session",
            defaults={"currency": "RUB"},
        )

    assert cart is concurrent_cart
    assert created is False
    get_cart.assert_called_once_with(
        user=None,
        session_key="concurrent-cart-session",
    )


@pytest.mark.django_db
def test_database_allows_only_one_cart_per_authenticated_user():
    user = User.objects.create_user(
        username="cart-constraint-user",
        email="cart-constraint-user@example.test",
        password="not-used-in-this-test",
    )
    other_user = User.objects.create_user(
        username="cart-constraint-other-user",
        email="cart-constraint-other-user@example.test",
        password="not-used-in-this-test",
    )
    Cart.objects.create(user=user, session_key="")

    with pytest.raises(IntegrityError), transaction.atomic():
        Cart.objects.create(user=user, session_key="")

    other_cart = Cart.objects.create(user=other_user, session_key="")
    assert other_cart.pk is not None


@pytest.mark.django_db
def test_database_allows_only_one_anonymous_cart_per_session_key():
    Cart.objects.create(session_key="unique-anonymous-session")

    with pytest.raises(IntegrityError), transaction.atomic():
        Cart.objects.create(session_key="unique-anonymous-session")

    other_cart = Cart.objects.create(session_key="other-anonymous-session")
    assert other_cart.pk is not None
