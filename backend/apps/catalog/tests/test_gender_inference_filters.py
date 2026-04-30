from types import SimpleNamespace

import pytest
from django.http import QueryDict

from apps.catalog.models import Category, Product
from apps.catalog.views import FacetedModelViewSetMixin, _apply_gender_filter


class _DummyFacetView(FacetedModelViewSetMixin):
    pass


def _build_request(query: str):
    return SimpleNamespace(query_params=QueryDict(query))


@pytest.mark.django_db
def test_gender_filter_matches_product_by_inferred_category_gender():
    category = Category.objects.create(
        name="Женские часы",
        slug="womens-watches",
        description="Женские часы",
    )
    product = Product.objects.create(
        name="Часы женские",
        slug="watch-women-1",
        description="Часы",
        category=category,
        product_type="accessories",
        price=1999,
        currency="TRY",
    )

    queryset = _apply_gender_filter(Product.objects.all(), _build_request("gender=women"))

    assert list(queryset) == [product]


@pytest.mark.django_db
def test_available_genders_infers_values_from_category_slug():
    category = Category.objects.create(
        name="Женские часы",
        slug="womens-watches",
        description="Женские часы",
    )
    product = Product.objects.create(
        name="Часы женские",
        slug="watch-women-2",
        description="Часы",
        category=category,
        product_type="accessories",
        price=2499,
        currency="TRY",
    )

    view = _DummyFacetView()
    genders = view._calculate_available_genders(Product.objects.filter(pk=product.pk))

    assert genders == ["women"]
