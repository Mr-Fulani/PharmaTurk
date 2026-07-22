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
    Product,
    ShoeProduct,
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
