from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Brand, Category, MedicineProduct, Product


@pytest.mark.django_db
def test_sitemap_entries_returns_all_active_categories_without_full_serializer(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    root = Category.objects.create(name="Medicines", slug="medicines")
    child = Category.objects.create(name="Tablets", slug="medicine-tablets", parent=root)
    shoes = Category.objects.create(name="Shoes", slug="shoes")
    Category.objects.create(name="Sneakers", slug="sneakers", parent=shoes)
    Category.objects.create(name="Hidden", slug="hidden-category", is_active=False)

    response = APIClient().get(
        "/api/catalog/sitemap-entries",
        {"kind": "categories", "page_size": 500},
    )

    assert response.status_code == 200
    assert response.data["count"] == 3
    assert {row["slug"] for row in response.data["results"]} == {
        root.slug, child.slug, shoes.slug,
    }
    assert set(response.data["results"][0]) == {"slug", "updated_at"}


@pytest.mark.django_db
def test_product_sitemap_excludes_stubs_and_shadow_variants(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)

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

    public = create("public-medicine", {})
    create("stub-medicine", {"is_stub": True})
    create("variant-medicine", {"source_variant_id": "variant-1"})

    response = APIClient().get(
        "/api/catalog/sitemap-products",
        {"domain": "medicines", "page_size": 500},
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert [row["slug"] for row in response.data["results"]] == [public.slug]


@pytest.mark.django_db
def test_sitemap_entries_rejects_unknown_kind():
    response = APIClient().get("/api/catalog/sitemap-entries", {"kind": "unknown"})

    assert response.status_code == 400
    assert "Unknown sitemap entry kind" in response.data["error"]
