from types import SimpleNamespace

import pytest
from django.http import QueryDict

from apps.catalog.models import Category, Product
from apps.catalog.views import FacetedModelViewSetMixin, _apply_gender_filter


class _DummyFacetView(FacetedModelViewSetMixin):
    pass


def _build_request(query: str):
    return SimpleNamespace(query_params=QueryDict(query))


def _build_facet_request(query: str):
    query_dict = QueryDict(query, mutable=True)
    return SimpleNamespace(query_params=query_dict, _request=SimpleNamespace(GET=query_dict.copy()))


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


@pytest.mark.django_db
def test_gender_facet_queryset_falls_back_when_requested_category_slug_is_missing():
    category = Category.objects.create(
        name="Женские часы",
        slug="womens-watches",
        description="Женские часы",
    )
    product = Product.objects.create(
        name="Часы женские",
        slug="watch-women-3",
        description="Часы",
        category=category,
        product_type="accessories",
        price=2999,
        currency="TRY",
    )

    class _FallbackFacetView(FacetedModelViewSetMixin):
        def __init__(self, queryset):
            self._queryset = queryset

        def get_queryset(self):
            return self._queryset

        def filter_queryset(self, queryset):
            current_slug = (
                self.request._request.GET.get("category_slug")
                or self.request._request.GET.get("subcategory_slug")
            )
            if current_slug == "ghost-type":
                return queryset.none()
            return queryset

    view = _FallbackFacetView(Product.objects.filter(pk=product.pk))
    view.request = _build_facet_request("category_slug=ghost-type&brand_slug=brand-x")

    queryset = view._get_gender_facet_queryset()

    assert list(queryset) == [product]
    assert view._calculate_available_genders(queryset) == ["women"]
