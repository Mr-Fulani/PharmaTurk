from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.admin import ProductSourceOfferAdmin, SourceOfferFreshnessFilter
from apps.catalog.models import Product, ProductSourceOffer
from apps.catalog.services.source_offer_verification import SourceOfferVerificationService


@pytest.fixture(autouse=True)
def diagnostic_settings(settings):
    settings.SOURCE_OFFER_BACKGROUND_STALE_SECONDS = 900
    cache.clear()
    yield
    cache.clear()


def _offer(name: str, checked_at=None):
    product = Product.objects.create(
        name=name,
        slug=f"{name.casefold()}-{uuid4().hex}",
        product_type="clothing",
    )
    offer = ProductSourceOffer.objects.create(
        product=product,
        parser_key="zara",
        canonical_url=f"https://www.zara.com/product-{uuid4().hex}",
    )
    if checked_at is not None:
        ProductSourceOffer.objects.filter(pk=offer.pk).update(last_checked_at=checked_at)
        offer.last_checked_at = checked_at
    return offer


@pytest.mark.django_db
def test_admin_freshness_labels_and_filter_match_background_threshold():
    now = timezone.now()
    fresh = _offer("fresh", now)
    stale = _offer("stale", now - timedelta(hours=1))
    never = _offer("never")
    model_admin = ProductSourceOfferAdmin(ProductSourceOffer, AdminSite())

    assert str(model_admin.freshness_status(fresh)) == "Актуально"
    assert str(model_admin.freshness_status(stale)) == "Устарело"
    assert str(model_admin.freshness_status(never)) == "Не проверялось"

    request = RequestFactory().get("/admin/catalog/productsourceoffer/")
    freshness_filter = SourceOfferFreshnessFilter(
        request,
        {"source_freshness": ["stale"]},
        ProductSourceOffer,
        model_admin,
    )

    assert list(
        freshness_filter.queryset(request, ProductSourceOffer.objects.all()).values_list(
            "pk", flat=True
        )
    ) == [stale.pk]


@pytest.mark.django_db
def test_admin_reads_circuit_state_without_triggering_verification():
    offer = _offer("circuit")
    model_admin = ProductSourceOfferAdmin(ProductSourceOffer, AdminSite())
    service = SourceOfferVerificationService()
    cache.set(service._circuit_key("zara"), True, timeout=60)

    assert model_admin.circuit_open(offer) is True
