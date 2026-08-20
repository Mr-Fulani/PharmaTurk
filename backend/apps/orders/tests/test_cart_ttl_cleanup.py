from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.catalog.models import Product
from apps.orders.models import Cart, CartItem
from apps.orders.tasks import _stale_anonymous_carts, cleanup_stale_anonymous_carts
from apps.users.models import User


def _run_cleanup(**kwargs):
    return cleanup_stale_anonymous_carts.run(**kwargs)


def test_anonymous_cart_cleanup_has_bounded_defaults():
    assert settings.ANONYMOUS_CART_TTL_DAYS == 30
    assert settings.ANONYMOUS_CART_CLEANUP_BATCH_SIZE == 500
    beat_entry = settings.CELERY_BEAT_SCHEDULE["orders-cleanup-stale-anonymous-carts"]
    assert beat_entry["task"] == "orders.cleanup_stale_anonymous_carts"
    assert beat_entry["kwargs"] == {"days": 30, "batch_size": 500}


def test_stale_cart_query_is_anonymous_only_and_excludes_recent_item_activity():
    queryset = _stale_anonymous_carts(timezone.now() - timedelta(days=30))
    sql = str(queryset.query).lower()

    assert queryset.model is Cart
    assert "orders_cart" in sql
    assert "user_id" in sql and "is null" in sql
    assert "not exists" in sql
    assert "orders_cartitem" in sql
    assert "updated_at" in sql


@pytest.mark.parametrize(
    "kwargs",
    (
        {"days": 0},
        {"days": -1},
        {"batch_size": 0},
        {"batch_size": -1},
        {"batch_size": 10_001},
    ),
)
def test_anonymous_cart_cleanup_rejects_invalid_bounds_before_database_access(kwargs):
    with pytest.raises(ValueError):
        _run_cleanup(**kwargs)


@pytest.mark.django_db
def test_cleanup_deletes_only_inactive_anonymous_carts_and_honors_recent_item_activity():
    now = timezone.now()
    stale_at = now - timedelta(days=31)
    recent_at = now - timedelta(days=1)

    stale_anonymous = Cart.objects.create(session_key="ttl-stale-anonymous")
    recent_anonymous = Cart.objects.create(session_key="ttl-recent-anonymous")
    active_item_cart = Cart.objects.create(session_key="ttl-recent-item")
    authenticated_user = User.objects.create_user(
        username="ttl-authenticated-user",
        email="ttl-authenticated-user@example.test",
        password="not-used-in-this-test",
    )
    stale_authenticated = Cart.objects.create(user=authenticated_user, session_key="")
    product = Product.objects.create(
        name="TTL activity product",
        slug="ttl-activity-product",
        price=10,
        currency="RUB",
    )
    recent_item = CartItem.objects.create(
        cart=active_item_cart,
        product=product,
        quantity=1,
        price=10,
        currency="RUB",
    )

    Cart.objects.filter(
        pk__in=[stale_anonymous.pk, active_item_cart.pk, stale_authenticated.pk]
    ).update(updated_at=stale_at)
    Cart.objects.filter(pk=recent_anonymous.pk).update(updated_at=recent_at)
    CartItem.objects.filter(pk=recent_item.pk).update(updated_at=recent_at)

    result = _run_cleanup(days=30, batch_size=500, dry_run=False)

    assert result == {
        "matched": 1,
        "deleted": 1,
        "dry_run": False,
        "retention_days": 30,
    }
    assert not Cart.objects.filter(pk=stale_anonymous.pk).exists()
    assert Cart.objects.filter(pk=recent_anonymous.pk).exists()
    assert Cart.objects.filter(pk=active_item_cart.pk).exists()
    assert CartItem.objects.filter(pk=recent_item.pk).exists()
    assert Cart.objects.filter(pk=stale_authenticated.pk).exists()


@pytest.mark.django_db
def test_cleanup_dry_run_reports_stale_carts_without_deleting_them():
    stale_cart = Cart.objects.create(session_key="ttl-dry-run-cart")
    Cart.objects.filter(pk=stale_cart.pk).update(
        updated_at=timezone.now() - timedelta(days=31)
    )

    result = _run_cleanup(days=30, batch_size=1, dry_run=True)

    assert result == {
        "matched": 1,
        "deleted": 0,
        "dry_run": True,
        "retention_days": 30,
    }
    assert Cart.objects.filter(pk=stale_cart.pk).exists()
