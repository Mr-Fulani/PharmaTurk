from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.catalog import brand_counts
from apps.catalog.models import Brand, Product
from apps.catalog.tasks import refresh_brand_product_counts_task


@pytest.fixture
def inventory(db, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *a, **kw: None)
    brand = Brand.objects.create(
        name="Cached brand", slug="cached-brand",
        primary_category_slug="medicines", category_slugs=["medicines"],
    )
    rows = [
        {}, {"product_type": "uslugi"}, {"is_active": False},
        {"is_available": False}, {"external_data": {"is_stub": True}},
        {"external_data": {"source_variant_id": 1}},
        {"external_data": {"source_variant_slug": "hidden"}},
    ]
    for i, overrides in enumerate(rows):
        fields = dict(
            brand=brand, name=f"Product {i}", slug=f"cache-product-{i}",
            product_type="medicines", price=10, currency="TRY",
            is_active=True, is_available=True,
        )
        fields.update(overrides)
        Product.objects.create(**fields)
    return brand


def test_cold_cache_counts_visibility_then_serves_without_sql(inventory, django_assert_num_queries):
    assert brand_counts.get_brand_product_counts() == {inventory.id: 2}
    with django_assert_num_queries(0):
        assert brand_counts.get_brand_product_counts() == {inventory.id: 2}


def test_refresh_updates_snapshot_and_failed_refresh_preserves_it(inventory):
    brand_counts.refresh_brand_product_counts()
    Product.objects.filter(slug="cache-product-0").update(is_available=False)
    assert brand_counts.get_brand_product_counts() == {inventory.id: 2}
    assert brand_counts.refresh_brand_product_counts() == {inventory.id: 1}
    with patch.object(brand_counts, "calculate_brand_product_counts", side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            brand_counts.refresh_brand_product_counts()
    assert brand_counts.get_brand_product_counts() == {inventory.id: 1}


def test_empty_snapshot_is_a_cache_hit():
    cache.set(brand_counts.CACHE_KEY, {})
    with patch.object(brand_counts, "calculate_brand_product_counts") as calculate:
        assert brand_counts.get_brand_product_counts() == {}
    calculate.assert_not_called()


def test_cache_outage_falls_back_to_exact_counts(inventory):
    with patch.object(brand_counts.cache, "get", side_effect=ConnectionError):
        assert brand_counts.get_brand_product_counts() == {inventory.id: 2}
    with patch.object(brand_counts.cache, "set", side_effect=ConnectionError):
        assert brand_counts.get_brand_product_counts() == {inventory.id: 2}


def test_list_uses_snapshot_but_live_metadata_and_filtered_counts(inventory):
    brand_counts.refresh_brand_product_counts()
    Brand.objects.filter(pk=inventory.pk).update(name="New name", show_on_homepage=True)
    client = APIClient()
    with patch.object(brand_counts, "calculate_brand_product_counts", side_effect=AssertionError):
        response = client.get("/api/catalog/brands", {"page_size": 1000})
    assert response.status_code == 200
    row = next(row for row in response.data["results"] if row["slug"] == inventory.slug)
    assert row["products_count"] == 2
    assert row["name"] == "New name"
    assert row["show_on_homepage"] is True
    with patch.object(brand_counts, "get_brand_product_counts", side_effect=AssertionError):
        response = client.get("/api/catalog/brands", {
            "count_scope": "filtered", "product_type": "medicines",
        })
    assert response.status_code == 200
    row = next(row for row in response.data["results"] if row["slug"] == inventory.slug)
    assert row["products_count"] == 1


def test_periodic_refresh_coalesces_overlap_and_releases_lock():
    lock = "catalog:brand-product-counts:v1:refresh-lock"
    cache.add(lock, True, 60)
    with patch.object(brand_counts, "refresh_brand_product_counts") as refresh:
        assert refresh_brand_product_counts_task.run() == {"status": "already_running"}
        refresh.assert_not_called()
    cache.delete(lock)
    with patch.object(brand_counts, "refresh_brand_product_counts", side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            refresh_brand_product_counts_task.run()
    assert cache.get(lock) is None
    with patch.object(brand_counts, "refresh_brand_product_counts", return_value={1: 2}):
        assert refresh_brand_product_counts_task.run() == {"status": "refreshed", "brands": 1}
