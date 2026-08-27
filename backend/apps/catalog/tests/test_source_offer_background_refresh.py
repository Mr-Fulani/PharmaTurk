from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from django.core.cache import cache
from django.utils import timezone

from apps.catalog.models import Product, ProductSourceOffer
from apps.catalog.services.source_offer_background_refresh import (
    BACKGROUND_REFRESH_LOCK_KEY,
    refresh_stale_source_offers,
)
from apps.orders.models import Cart, CartItem


@pytest.fixture(autouse=True)
def background_settings(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": f"source-offer-background-{uuid4().hex}",
        }
    }
    settings.SOURCE_OFFER_BACKGROUND_REFRESH_ENABLED = True
    settings.SOURCE_OFFER_VERIFICATION_ENABLED = True
    settings.SOURCE_OFFER_VERIFICATION_SOURCES = []
    settings.SOURCE_OFFER_BACKGROUND_REFRESH_BATCH_SIZE = 2
    settings.SOURCE_OFFER_BACKGROUND_STALE_SECONDS = 900
    settings.SOURCE_OFFER_BACKGROUND_POPULAR_CART_DAYS = 7
    settings.SOURCE_OFFER_BACKGROUND_LOCK_SECONDS = 330
    cache.clear()
    yield
    cache.clear()


def _offer(*, name: str, parser_key: str = "zara", is_active: bool = True):
    product = Product.objects.create(
        name=name,
        slug=f"{name.casefold().replace(' ', '-')}-{uuid4().hex}",
        product_type="clothing",
    )
    offer = ProductSourceOffer.objects.create(
        product=product,
        parser_key=parser_key,
        canonical_url=f"https://www.{parser_key}.com/product-{uuid4().hex}",
        external_product_id=uuid4().hex,
        is_active=is_active,
    )
    return product, offer


@pytest.mark.django_db
def test_refresh_is_bounded_and_prioritises_recent_cart_offer(monkeypatch):
    now = timezone.now()
    popular_product, popular = _offer(name="Popular stale")
    _, never_checked = _offer(name="Never checked")
    _, fresh = _offer(name="Fresh")
    _, inactive = _offer(name="Inactive", is_active=False)

    ProductSourceOffer.objects.filter(pk=popular.pk).update(last_checked_at=now - timedelta(days=2))
    ProductSourceOffer.objects.filter(pk=fresh.pk).update(last_checked_at=now)
    cart = Cart.objects.create(session_key=uuid4().hex)
    cart_item = CartItem.objects.create(
        cart=cart,
        product=popular_product,
        source_offer=popular,
        quantity=1,
        price=Decimal("100.00"),
        currency="TRY",
    )
    CartItem.objects.filter(pk=cart_item.pk).update(updated_at=now)

    checked = []

    def fake_verify(self, offer, *, force=False):
        checked.append((offer.pk, force))
        return SimpleNamespace(is_success=True, error=None)

    monkeypatch.setattr(
        "apps.catalog.services.source_offer_background_refresh."
        "SourceOfferVerificationService.verify",
        fake_verify,
    )

    result = refresh_stale_source_offers(now=now)

    assert result["status"] == "completed"
    assert result["stale_total"] == 2
    assert result["selected"] == 2
    assert result["successful"] == 2
    assert checked == [(popular.pk, True), (never_checked.pk, True)]
    assert fresh.pk not in {pk for pk, _ in checked}
    assert inactive.pk not in {pk for pk, _ in checked}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("setting_name", "reason"),
    [
        ("SOURCE_OFFER_BACKGROUND_REFRESH_ENABLED", "background_refresh_disabled"),
        ("SOURCE_OFFER_VERIFICATION_ENABLED", "live_verification_disabled"),
    ],
)
def test_refresh_flags_exit_before_query_or_verification(
    settings,
    monkeypatch,
    django_assert_num_queries,
    setting_name,
    reason,
):
    setattr(settings, setting_name, False)
    verify = monkeypatch.setattr(
        "apps.catalog.services.source_offer_background_refresh."
        "SourceOfferVerificationService.verify",
        lambda *args, **kwargs: pytest.fail("verification must not run"),
    )

    with django_assert_num_queries(0):
        result = refresh_stale_source_offers()

    assert verify is None
    assert result["status"] == "disabled"
    assert result["reason"] == reason


@pytest.mark.django_db
def test_refresh_honours_source_allowlist(monkeypatch):
    _, zara = _offer(name="Allowed", parser_key="zara")
    _offer(name="Not allowed", parser_key="flo")
    from django.conf import settings

    settings.SOURCE_OFFER_VERIFICATION_SOURCES = [" ZARA "]
    checked = []

    def fake_verify(self, offer, *, force=False):
        checked.append(offer.pk)
        return SimpleNamespace(is_success=True, error=None)

    monkeypatch.setattr(
        "apps.catalog.services.source_offer_background_refresh."
        "SourceOfferVerificationService.verify",
        fake_verify,
    )

    result = refresh_stale_source_offers()

    assert result["stale_total"] == 1
    assert checked == [zara.pk]


@pytest.mark.django_db
def test_overlapping_refresh_exits_without_database_work(django_assert_num_queries):
    cache.set(BACKGROUND_REFRESH_LOCK_KEY, "another-worker", timeout=60)

    with django_assert_num_queries(0):
        result = refresh_stale_source_offers()

    assert result["status"] == "already_running"
    assert result["checked"] == 0


@pytest.mark.django_db
def test_soft_time_limit_stops_batch_and_releases_lock(monkeypatch):
    _offer(name="Timeout candidate")

    def stop_worker(*args, **kwargs):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(
        "apps.catalog.services.source_offer_background_refresh."
        "SourceOfferVerificationService.verify",
        stop_worker,
    )

    with pytest.raises(SoftTimeLimitExceeded):
        refresh_stale_source_offers()

    assert cache.get(BACKGROUND_REFRESH_LOCK_KEY) is None
