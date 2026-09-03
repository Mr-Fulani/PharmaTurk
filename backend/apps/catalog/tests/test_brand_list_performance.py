from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.catalog.models import Brand, Product


@pytest.mark.django_db
def test_brand_list_counts_are_bounded_and_exclude_non_public_rows(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    suffix = uuid4().hex[:10]
    brands = []

    for brand_index in range(8):
        brand = Brand.objects.create(
            name=f"Performance brand {brand_index} {suffix}",
            slug=f"performance-brand-{suffix}-{brand_index}",
            primary_category_slug="medicines",
            category_slugs=["medicines"],
        )
        brands.append(brand)
        for product_index in range(2):
            Product.objects.create(
                name=f"Public product {brand_index}-{product_index}",
                slug=f"public-product-{suffix}-{brand_index}-{product_index}",
                product_type="medicines",
                brand=brand,
                price=Decimal("10.00"),
                currency="TRY",
                is_active=True,
                is_available=True,
            )
        Product.objects.create(
            name=f"Hidden stub {brand_index}",
            slug=f"hidden-stub-{suffix}-{brand_index}",
            product_type="medicines",
            brand=brand,
            price=Decimal("10.00"),
            currency="TRY",
            is_active=True,
            is_available=True,
            external_data={"is_stub": True},
        )

    with CaptureQueriesContext(connection) as queries:
        response = APIClient().get(
            "/api/catalog/brands",
            {
                "product_type": "medicines",
                "primary_category_slug": "medicines",
                "count_scope": "filtered",
                "page_size": 500,
            },
        )

    assert response.status_code == 200
    rows_by_slug = {row["slug"]: row for row in response.data["results"]}
    assert all(rows_by_slug[brand.slug]["products_count"] == 2 for brand in brands)
    assert len(queries.captured_queries) <= 7
    assert not any(
        'COUNT(DISTINCT "catalog_product"."id")' in query["sql"]
        for query in queries.captured_queries
    )
