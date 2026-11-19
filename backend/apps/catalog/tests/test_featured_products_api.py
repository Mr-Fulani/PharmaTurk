import uuid

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import (
    Category,
    ClothingProduct,
    ElectronicsProduct,
    FurnitureProduct,
    JewelryProduct,
    MedicineProduct,
    Product,
    ShoeProduct,
    SupplementProduct,
)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("model_class", "product_type"),
    [
        (ClothingProduct, "clothing"),
        (ShoeProduct, "shoes"),
        (ElectronicsProduct, "electronics"),
        (FurnitureProduct, "furniture"),
        (JewelryProduct, "jewelry"),
    ],
)
def test_featured_endpoint_returns_one_canonical_product_per_domain_item(model_class, product_type):
    suffix = uuid.uuid4().hex[:8]
    category = Category.objects.create(name=f"Featured {suffix}", slug=f"featured-{suffix}")
    domain_product = model_class.objects.create(
        name=f"Featured product {suffix}",
        slug=f"featured-product-{suffix}",
        category=category,
        price=100,
        currency="TRY",
        is_active=True,
        is_featured=True,
    )
    domain_product.refresh_from_db(fields=["base_product"])

    assert domain_product.base_product_id is not None

    response = APIClient().get("/api/catalog/products/featured", {"limit": 20})

    assert response.status_code == status.HTTP_200_OK
    matches = [row for row in response.json() if row["slug"] == domain_product.slug]
    assert len(matches) == 1
    assert matches[0]["id"] == domain_product.base_product_id
    assert matches[0]["product_type"].replace("_", "-") == product_type


@pytest.mark.django_db
def test_featured_endpoint_excludes_variant_shadows_for_every_product_type():
    product = Product.objects.create(
        name="Variant shadow",
        slug=f"variant-shadow-{uuid.uuid4().hex[:8]}",
        product_type="jewelry",
        is_active=True,
        is_featured=True,
        external_data={"source_variant_slug": "variant-red"},
    )

    response = APIClient().get("/api/catalog/products/featured", {"limit": 20})

    assert response.status_code == status.HTTP_200_OK
    assert product.id not in {row["id"] for row in response.json()}


@pytest.mark.django_db
def test_featured_endpoint_caps_requested_limit_at_twenty():
    suffix = uuid.uuid4().hex[:8]
    category = Category.objects.create(name=f"Limit {suffix}", slug=f"limit-{suffix}")
    for index in range(25):
        JewelryProduct.objects.create(
            name=f"Featured {index}",
            slug=f"featured-limit-{index}-{uuid.uuid4().hex[:8]}",
            category=category,
            price=100 + index,
            currency="TRY",
            is_active=True,
            is_featured=True,
        )

    response = APIClient().get("/api/catalog/products/featured", {"limit": 1000})

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 20


def _featured_pharmacy_item(model_class, slug):
    root = "medicines" if model_class is MedicineProduct else "supplements"
    category = Category.objects.get_or_create(slug=root, defaults={"name": root})[0]
    item = model_class.objects.create(
        name=slug.upper(), slug=slug, category=category, price=100, currency="TRY",
        is_active=True, is_featured=True,
    )
    item.refresh_from_db()
    return item


@pytest.mark.django_db
def test_medicines_are_not_bestsellers_but_fill_the_reference_block():
    medicine = _featured_pharmacy_item(MedicineProduct, "hit-parol")
    supplement = _featured_pharmacy_item(SupplementProduct, "hit-omega")
    client = APIClient()

    for params in ({"limit": 20}, {"limit": 20, "view": "card"}):
        featured = {row["slug"]: row for row in client.get("/api/catalog/products/featured", params).json()}
        assert supplement.slug in featured and medicine.slug not in featured
        assert featured[supplement.slug]["is_featured"] is True

        reference = client.get("/api/catalog/products/medicine-reference", params).json()
        assert [row["slug"] for row in reference] == [medicine.slug]
        assert reference[0]["product_type"] == "medicines"
        # Флажок в базе остаётся, но наружу лекарство не «хит».
        assert not reference[0].get("is_featured")

    assert MedicineProduct.objects.get(pk=medicine.pk).is_featured is True


@pytest.mark.django_db
def test_medicine_is_never_served_as_featured():
    medicine = _featured_pharmacy_item(MedicineProduct, "hit-nurofen")
    supplement = _featured_pharmacy_item(SupplementProduct, "hit-magnesium")
    client = APIClient()

    def flags(url, params=None):
        payload = client.get(url, params or {}).json()
        rows = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
        rows = rows if isinstance(rows, list) else [rows]
        return {row["slug"]: bool(row.get("is_featured")) for row in rows}

    assert flags(f"/api/catalog/medicines/products/{medicine.slug}") == {medicine.slug: False}
    assert flags(f"/api/catalog/products/{medicine.slug}") == {medicine.slug: False}
    assert flags("/api/catalog/medicines/products")[medicine.slug] is False
    assert flags("/api/catalog/medicines/products", {"view": "card"})[medicine.slug] is False
    assert flags("/api/catalog/products", {"view": "card", "limit": 50})[medicine.slug] is False
    # БАДы остаются хитами.
    assert flags(f"/api/catalog/supplements/products/{supplement.slug}") == {supplement.slug: True}
    assert flags("/api/catalog/supplements/products", {"view": "card"})[supplement.slug] is True
