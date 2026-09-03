from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.catalog.models import Category, CategoryType, MedicineProduct, Product


@pytest.mark.django_db
def test_sitemap_entries_returns_all_active_categories_without_full_serializer(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    suffix = uuid4().hex[:10]
    root = Category.objects.create(name="Medicines", slug=f"sitemap-medicines-{suffix}")
    child = Category.objects.create(name="Tablets", slug=f"sitemap-tablets-{suffix}", parent=root)
    shoe_type, _ = CategoryType.objects.get_or_create(
        slug="shoes",
        defaults={"name": f"Sitemap shoes {suffix}"},
    )
    shoes = Category.objects.filter(slug="shoes").first()
    if shoes is None:
        shoes = Category.objects.create(name="Shoes", slug="shoes", category_type=shoe_type)
    sneakers = Category.objects.create(
        name="Sneakers",
        slug=f"sitemap-sneakers-{suffix}",
        parent=shoes,
        category_type=shoe_type,
    )
    hidden = Category.objects.create(
        name="Hidden",
        slug=f"sitemap-hidden-{suffix}",
        is_active=False,
    )

    response = APIClient().get(
        "/api/catalog/sitemap-entries",
        {"kind": "categories", "page_size": 500},
    )

    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    assert {root.slug, child.slug, shoes.slug}.issubset(slugs)
    assert sneakers.slug not in slugs
    assert hidden.slug not in slugs
    assert response.data["count"] >= len(response.data["results"])
    assert set(response.data["results"][0]) == {"slug", "updated_at"}


@pytest.mark.django_db
def test_product_sitemap_excludes_stubs_and_shadow_variants(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    suffix = uuid4().hex[:10]

    def create(slug, external_data):
        base = Product.objects.create(
            name=slug,
            slug=slug,
            product_type="medicines",
            price=Decimal("10.00"),
            currency="TRY",
            external_data=external_data,
            is_active=True,
        )
        medicine = MedicineProduct.objects.get(base_product=base)
        MedicineProduct.objects.filter(pk=medicine.pk).update(external_data=external_data)
        return medicine

    public = create(f"public-medicine-{suffix}", {})
    stub = create(f"stub-medicine-{suffix}", {"is_stub": True})
    variant = create(f"variant-medicine-{suffix}", {})
    variant_data = {"source_variant_id": f"variant-{suffix}"}
    Product.objects.filter(pk=variant.base_product_id).update(external_data=variant_data)
    MedicineProduct.objects.filter(pk=variant.pk).update(external_data=variant_data)

    response = APIClient().get(
        "/api/catalog/sitemap-products",
        {"domain": "medicines", "page_size": 500},
    )

    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    assert public.slug in slugs
    assert stub.slug not in slugs
    assert variant.slug not in slugs
    assert response.data["count"] >= len(response.data["results"])


@pytest.mark.django_db
def test_product_sitemap_cursor_paginates_without_count(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    suffix = uuid4().hex[:10]
    cursor = MedicineProduct.objects.order_by("-id").values_list("id", flat=True).first() or 0

    expected_slugs = []
    for index in range(3):
        product = Product.objects.create(
            name=f"Cursor medicine {index}",
            slug=f"cursor-medicine-{suffix}-{index}",
            product_type="medicines",
            price=Decimal("10.00"),
            currency="TRY",
            is_active=True,
        )
        expected_slugs.append(MedicineProduct.objects.get(base_product=product).slug)

    client = APIClient()
    with CaptureQueriesContext(connection) as queries:
        first = client.get(
            "/api/catalog/sitemap-products",
            {"domain": "medicines", "page_size": 2, "cursor": cursor},
        )

    assert first.status_code == 200
    assert "count" not in first.data
    assert first.data["next_cursor"] is not None
    assert len(first.data["results"]) == 2
    assert not any("COUNT(" in query["sql"].upper() for query in queries.captured_queries)

    second = client.get(
        "/api/catalog/sitemap-products",
        {
            "domain": "medicines",
            "page_size": 2,
            "cursor": first.data["next_cursor"],
        },
    )
    assert second.status_code == 200
    assert second.data["next_cursor"] is None
    returned_slugs = [
        row["slug"]
        for row in [*first.data["results"], *second.data["results"]]
    ]
    assert returned_slugs == expected_slugs


@pytest.mark.django_db
def test_sitemap_entries_rejects_unknown_kind():
    response = APIClient().get("/api/catalog/sitemap-entries", {"kind": "unknown"})

    assert response.status_code == 400
    assert "Unknown sitemap entry kind" in response.data["error"]
