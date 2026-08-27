from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
import xml.etree.ElementTree as ET

import pytest
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductSourceOffer
from apps.catalog.serializers import _LocalizedSeoMethodsMixin
from apps.catalog.services.source_offer_catalog_projection import (
    resolve_source_offer_catalog_availability,
)
from apps.catalog.views_yml import YMLExportView


class ProjectionProbeSerializer(_LocalizedSeoMethodsMixin, serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ("id", "availability_status", "is_available")


@pytest.fixture(autouse=True)
def projection_settings(settings):
    settings.SOURCE_OFFER_CATALOG_PROJECTION_ENABLED = True
    settings.SOURCE_OFFER_VERIFICATION_ENABLED = True
    settings.SOURCE_OFFER_VERIFICATION_SOURCES = []
    settings.SOURCE_OFFER_BACKGROUND_STALE_SECONDS = 900


def _product():
    return Product.objects.create(
        name="Projection product",
        slug=f"projection-product-{uuid4().hex}",
        product_type="clothing",
        availability_status="in_stock",
        is_available=True,
    )


def _offer(product, *, status, checked_at, parser_key="zara"):
    offer = ProductSourceOffer.objects.create(
        product=product,
        parser_key=parser_key,
        canonical_url=f"https://www.{parser_key}.com/product-{uuid4().hex}",
        external_product_id=uuid4().hex,
        availability_status=status,
    )
    ProductSourceOffer.objects.filter(pk=offer.pk).update(last_checked_at=checked_at)
    offer.last_checked_at = checked_at
    return offer


@pytest.mark.django_db
def test_projection_requires_every_offer_fresh_before_marking_product_unavailable():
    now = timezone.now()
    product = _product()
    _offer(
        product,
        status=ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK,
        checked_at=now,
    )
    _offer(
        product,
        status=ProductSourceOffer.AvailabilityStatus.UNKNOWN,
        checked_at=now - timedelta(hours=1),
        parser_key="flo",
    )

    assert resolve_source_offer_catalog_availability(product, now=now) is None


@pytest.mark.django_db
def test_projection_prefers_any_fresh_sellable_offer():
    now = timezone.now()
    product = _product()
    _offer(
        product,
        status=ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK,
        checked_at=now,
    )
    _offer(
        product,
        status=ProductSourceOffer.AvailabilityStatus.LIMITED,
        checked_at=now,
        parser_key="flo",
    )

    projection = resolve_source_offer_catalog_availability(product, now=now)

    assert projection.is_available is True
    assert projection.availability_status == "in_stock"


@pytest.mark.django_db
def test_detail_serializer_projects_out_of_stock_but_list_does_not(
    django_assert_num_queries,
):
    now = timezone.now()
    product = _product()
    _offer(
        product,
        status=ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK,
        checked_at=now,
    )

    detail = ProjectionProbeSerializer(
        product,
        context={"view": SimpleNamespace(action="retrieve")},
    ).data
    with django_assert_num_queries(0):
        listing = ProjectionProbeSerializer(
            product,
            context={"view": SimpleNamespace(action="list")},
        ).data

    assert detail["availability_status"] == "out_of_stock"
    assert detail["is_available"] is False
    assert listing["availability_status"] == "in_stock"
    assert listing["is_available"] is True


@pytest.mark.django_db
def test_sellable_supplier_never_overrides_manual_catalog_unavailable():
    now = timezone.now()
    product = _product()
    product.is_available = False
    product.save(update_fields=["is_available"])
    _offer(
        product,
        status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        checked_at=now,
    )

    detail = ProjectionProbeSerializer(
        product,
        context={"view": SimpleNamespace(action="retrieve")},
    ).data

    assert detail["is_available"] is False


@pytest.mark.django_db
def test_projection_source_allowlist_ignores_disabled_parser(settings):
    now = timezone.now()
    product = _product()
    _offer(
        product,
        status=ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK,
        checked_at=now,
        parser_key="flo",
    )
    settings.SOURCE_OFFER_VERIFICATION_SOURCES = ["zara"]

    assert resolve_source_offer_catalog_availability(product, now=now) is None


@pytest.mark.django_db
def test_feed_mode_never_falls_back_to_per_product_query(django_assert_num_queries):
    product = _product()

    with django_assert_num_queries(0):
        projection = resolve_source_offer_catalog_availability(
            product,
            allow_queries=False,
        )

    assert projection is None


@pytest.mark.django_db
def test_yml_uses_same_supplier_availability_projection():
    now = timezone.now()
    product = _product()
    product.price = "100.00"
    product.currency = "RUB"
    product.save(update_fields=["price", "currency"])
    _offer(
        product,
        status=ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK,
        checked_at=now,
    )
    product = Product.objects.prefetch_related("source_offers").get(pk=product.pk)
    offers = ET.Element("offers")

    YMLExportView()._create_offer(
        offers,
        product,
        "https://mudaroba.com",
        {},
    )

    assert offers.find("offer").attrib["available"] == "false"


@pytest.mark.django_db
def test_out_of_stock_product_detail_remains_200_with_projected_status():
    now = timezone.now()
    product = _product()
    _offer(
        product,
        status=ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK,
        checked_at=now,
    )

    response = APIClient().get(f"/api/catalog/products/resolve/{product.slug}")

    assert response.status_code == 200
    assert response.data["payload"]["availability_status"] == "out_of_stock"
    assert response.data["payload"]["is_available"] is False
