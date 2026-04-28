"""
Тесты единого resolve товара и зеркала canonical_path с frontend (urls.ts / product.ts).
Интеграционные тесты эндпоинта помечены django_db — в локали нужна доступная БД (Docker).
"""

import uuid
from unittest.mock import patch

import pytest
from django.test import RequestFactory
from rest_framework import status

from apps.catalog.models import Brand, Category, PerfumeryProduct
from apps.catalog.serializers import PerfumeryProductSerializer
from apps.catalog.services.product_resolve import (
    BASE_PRODUCT_TYPES,
    TYPES_NEEDING_PATH,
    build_canonical_path,
    build_resolve_response,
    deduplicate_slug,
    needs_type_in_path,
)


class TestDeduplicateSlug:
    def test_double_half(self):
        assert deduplicate_slug("foo-bar-foo-bar") == "foo-bar"

    def test_underscore_normalized(self):
        assert deduplicate_slug("a_b") == "a-b"


class TestCanonicalPath:
    def test_medicines_short(self):
        assert build_canonical_path("medicines", "x") == "/product/x"

    def test_clothing_strips_repeated_prefix(self):
        assert build_canonical_path("clothing", "clothing-shirt") == "/product/clothing/shirt"

    def test_uslugi_segment(self):
        assert build_canonical_path("uslugi", "svc") == "/product/uslugi/svc"

    def test_jewelry_long(self):
        assert build_canonical_path("jewelry", "ring") == "/product/jewelry/ring"

    def test_bags_base_short(self):
        assert build_canonical_path("bags", "my-bag") == "/product/my-bag"


class TestListsMatchFrontendProductTs:
    """Должно совпадать с frontend/src/lib/product.ts — при изменении обновить оба."""

    def test_types_needing_path(self):
        expected = frozenset(
            {
                "clothing",
                "shoes",
                "electronics",
                "jewelry",
                "uslugi",
                "headwear",
                "underwear",
                "islamic-clothing",
            }
        )
        assert TYPES_NEEDING_PATH == expected

    def test_base_product_types(self):
        expected = frozenset(
            {
                "medicines",
                "supplements",
                "medical-equipment",
                "furniture",
                "tableware",
                "accessories",
                "books",
                "perfumery",
                "sports",
                "auto-parts",
                "incense",
                "bags",
                "watches",
                "cosmetics",
                "toys",
                "home-textiles",
                "stationery",
                "pet-supplies",
            }
        )
        assert BASE_PRODUCT_TYPES == expected

    def test_base_disjoint_from_path_types(self):
        assert not (BASE_PRODUCT_TYPES & TYPES_NEEDING_PATH)

    def test_needs_type_in_path(self):
        assert needs_type_in_path("clothing") is True
        assert needs_type_in_path("medicines") is False
        assert needs_type_in_path("") is False


class TestBuildResolveResponse:
    def test_404_when_unresolved(self):
        req = RequestFactory().get("/")
        with patch(
            "apps.catalog.services.product_resolve.resolve_product_payload",
            return_value=None,
        ):
            resp = build_resolve_response(req, "nope")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_200_shape(self):
        req = RequestFactory().get("/")
        payload = {"id": 1, "slug": "item", "product_type": "medicines"}
        with patch(
            "apps.catalog.services.product_resolve.resolve_product_payload",
            return_value=(payload, "generic_product", "medicines"),
        ):
            resp = build_resolve_response(req, "item")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["product_type"] == "medicines"
        assert resp.data["canonical_path"] == "/product/item"
        assert resp.data["payload"] == payload
        assert resp.data["source"] == "generic_product"


@pytest.mark.django_db
def test_resolve_api_unknown_slug_404():
    """Полный путь API: без товара в БД — 404 (нужна PostgreSQL/SQLite из настроек)."""
    from rest_framework.test import APIClient

    client = APIClient()
    slug = f"___missing_resolve_{uuid.uuid4().hex}___"
    response = client.get(f"/api/catalog/products/resolve/{slug}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_perfumery_serializer_exposes_product_type_and_dynamic_attributes():
    category = Category.objects.create(name="Парфюмерия", slug=f"perfumery-{uuid.uuid4().hex[:8]}")
    brand = Brand.objects.create(name=f"LCW {uuid.uuid4().hex[:6]}", slug=f"lcw-{uuid.uuid4().hex[:8]}")
    product = PerfumeryProduct.objects.create(
        name="Parfum Test",
        slug=f"parfum-test-{uuid.uuid4().hex[:8]}",
        category=category,
        brand=brand,
        price=100,
        currency="TRY",
        gender="",
        is_active=True,
    )

    data = PerfumeryProductSerializer(product).data

    assert data["product_type"] == "perfumery"
    assert "dynamic_attributes" in data
