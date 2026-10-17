"""Порядок списков медикаментов и БАДов: ранг «Популярные» и устойчивые сортировки."""

import uuid

import pytest
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient

from apps.catalog.models import (
    Category,
    Favorite,
    MedicineProduct,
    ProductMarketCheck,
    SupplementProduct,
)
from apps.catalog.services.catalog_sort_rank import compute_sort_rank, recompute_sort_ranks

URL = "/api/catalog/medicines/products"
SUPPLEMENTS_URL = "/api/catalog/supplements/products"


def _rank(**overrides):
    params = dict(
        has_price=True, is_available=True, is_featured=False,
        interest=0, has_image=False, has_ru_description=False,
    )
    params.update(overrides)
    return compute_sort_rank(**params)


def test_rank_puts_price_before_demand_and_demand_before_card_quality():
    assert _rank() > _rank(is_available=False) > _rank(has_price=False)
    assert _rank(has_price=False, is_featured=True, interest=9_999) < _rank()
    assert _rank(is_featured=True) > _rank(interest=10_000, has_image=True)
    assert _rank(interest=1) > _rank(has_image=True, has_ru_description=True)


@pytest.fixture
def medicines(db):
    suffix = uuid.uuid4().hex[:8]
    category = Category.objects.create(name="Медикаменты", slug=f"medicines-{suffix}")

    def make(name, **fields):
        return MedicineProduct.objects.create(
            name=name, slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
            category=category, currency="TRY", is_active=True, **fields,
        )

    return category, make


def _names(category, ordering, url=URL):
    response = APIClient().get(
        url, {"category_slug": category.slug, "ordering": ordering, "view": "card"}
    )
    assert response.status_code == 200
    return [item["name"] for item in response.data["results"]]


def test_popular_order_follows_recomputed_rank(medicines):
    category, make = medicines
    make("Unpriced", price=None)
    plain = make("Plain", price=10)
    wanted = make("Wanted", price=10)
    favorite = make("Favorite", price=10)
    wanted.refresh_from_db()  # shadow-Product создаётся в save()
    ProductMarketCheck.objects.create(
        product=wanted.base_product, source="ilacfiyati",
        source_url="https://example.com/wanted", request_count=5,
    )
    Favorite.objects.create(
        session_key="rank-test",
        content_type=ContentType.objects.get_for_model(MedicineProduct),
        object_id=favorite.pk,
    )
    plain.refresh_from_db()  # save() пишет shadow-sync повторно
    updated_at = plain.updated_at

    assert recompute_sort_ranks(MedicineProduct) == 4
    assert _names(category, "popular") == ["Wanted", "Favorite", "Plain", "Unpriced"]

    plain.refresh_from_db()
    assert plain.updated_at == updated_at
    assert recompute_sort_ranks(MedicineProduct) == 0


def test_price_desc_keeps_unpriced_last_and_ties_are_stable(medicines):
    category, make = medicines
    make("Unpriced", price=None)
    first = make("Same", price=5)
    second = make("Same", price=5)
    make("Expensive", price=50)

    assert _names(category, "price_desc") == ["Expensive", "Same", "Same", "Unpriced"]
    assert _names(category, "price_asc")[-1] == "Unpriced"

    response = APIClient().get(
        URL, {"category_slug": category.slug, "ordering": "name_asc", "view": "card"}
    )
    same_ids = [item["id"] for item in response.data["results"] if item["name"] == "Same"]
    assert same_ids == [first.pk, second.pk]


def test_supplements_popular_order_follows_recomputed_rank(db):
    category = Category.objects.create(name="БАДы", slug=f"supplements-{uuid.uuid4().hex[:8]}")

    def make(name, price):
        return SupplementProduct.objects.create(
            name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}",
            category=category, currency="TRY", is_active=True, price=price,
        )

    make("Unpriced", None)
    make("Plain", 10)
    wanted = make("Wanted", 10)
    Favorite.objects.create(
        session_key="rank-test",
        content_type=ContentType.objects.get_for_model(SupplementProduct),
        object_id=wanted.pk,
    )

    assert recompute_sort_ranks(SupplementProduct) == 3
    assert _names(category, "popular", SUPPLEMENTS_URL) == ["Wanted", "Plain", "Unpriced"]
