from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Brand, Category, Product
from apps.catalog.views import ProductViewSet


@pytest.mark.django_db
def test_card_search_can_skip_facets_without_changing_card_contract(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    category = Category.objects.create(
        name="Search category",
        slug="search-card-category",
    )
    brand = Brand.objects.create(
        name="Search brand",
        slug="search-card-brand",
    )
    product = Product.objects.create(
        name="Cleocin card result",
        slug="cleocin-card-result",
        description="Search result",
        product_type="medicines",
        category=category,
        brand=brand,
        price=Decimal("100.00"),
        currency="TRY",
        is_active=True,
        is_available=True,
    )

    with patch.object(
        ProductViewSet,
        "_get_facet_queryset",
        side_effect=AssertionError("facets must not run for card search"),
    ):
        response = APIClient().get(
            "/api/catalog/products",
            {
                "search": "Cleocin",
                "page_size": 24,
                "view": "card",
                "include_facets": "false",
            },
            HTTP_X_CURRENCY="TRY",
        )

    assert response.status_code == 200
    assert "available_attributes" not in response.data
    assert "available_genders" not in response.data
    assert "available_fragrance_types" not in response.data
    row = next(item for item in response.data["results"] if item["id"] == product.pk)
    assert row["brand_id"] == brand.pk
    assert "brand" not in row
    assert "category" not in row
    assert row["currency"] == "TRY"
    assert row["price"] is not None


@pytest.mark.django_db
def test_facets_remain_enabled_by_default(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    Product.objects.create(
        name="Default facet result",
        slug="default-facet-result",
        product_type="medicines",
        price=Decimal("10.00"),
        currency="TRY",
        is_active=True,
        is_available=True,
    )

    with patch.object(ProductViewSet, "_calculate_available_attributes", return_value=[]), patch.object(
        ProductViewSet, "_calculate_available_genders", return_value=[]
    ), patch.object(ProductViewSet, "_calculate_available_fragrance_types", return_value=[]):
        response = APIClient().get(
            "/api/catalog/products",
            {"search": "Default facet", "page_size": 24, "view": "card"},
        )

    assert response.status_code == 200
    assert response.data["available_attributes"] == []
    assert response.data["available_genders"] == []
    assert response.data["available_fragrance_types"] == []
