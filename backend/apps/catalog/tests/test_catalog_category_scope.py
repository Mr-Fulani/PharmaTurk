from decimal import Decimal

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.catalog.models import Category, MedicineProduct, Product
from apps.catalog.views import MedicineProductViewSet, ProductViewSet


def _queryset_for(view_class, **params):
    view = view_class()
    view.request = Request(APIRequestFactory().get('/api/catalog/products', params))
    return view.get_queryset()


@pytest.fixture
def medicine_catalog(monkeypatch):
    monkeypatch.setattr(Product, 'update_currency_prices', lambda *args, **kwargs: None)

    root = Category.objects.create(name='Medicines', slug='medicines')
    child = Category.objects.create(name='Tablets', slug='medicine-tablets', parent=root)
    unrelated_root = Category.objects.create(name='Clearance', slug='clearance')

    def create(slug, category):
        base = Product.objects.create(
            name=slug,
            slug=slug,
            product_type='medicines',
            category=category,
            price=Decimal('10.00'),
            currency='TRY',
            is_active=True,
        )
        return base, MedicineProduct.objects.get(base_product=base)

    root_product = create('root-medicine', root)
    child_product = create('child-medicine', child)
    uncategorized_product = create('uncategorized-medicine', None)
    unrelated_product = create('unrelated-medicine', unrelated_root)

    return {
        'root': root,
        'child': child,
        'root_product': root_product,
        'child_product': child_product,
        'uncategorized_product': uncategorized_product,
        'unrelated_product': unrelated_product,
    }


@pytest.mark.django_db
def test_generic_root_category_does_not_pull_same_type_from_another_tree(medicine_catalog):
    rows = set(
        _queryset_for(ProductViewSet, category_slug='medicines')
        .values_list('slug', flat=True)
    )

    assert rows == {
        'root-medicine',
        'child-medicine',
        'uncategorized-medicine',
    }


@pytest.mark.django_db
def test_generic_subcategory_does_not_include_uncategorized_domain_items(medicine_catalog):
    rows = set(
        _queryset_for(ProductViewSet, category_slug='medicine-tablets')
        .values_list('slug', flat=True)
    )

    assert rows == {'child-medicine'}


@pytest.mark.django_db
def test_domain_category_scope_matches_root_and_subcategory_contract(medicine_catalog):
    root_rows = set(
        _queryset_for(MedicineProductViewSet, category_slug='medicines')
        .values_list('slug', flat=True)
    )
    child_rows = set(
        _queryset_for(MedicineProductViewSet, category_slug='medicine-tablets')
        .values_list('slug', flat=True)
    )

    assert root_rows == {
        'root-medicine',
        'child-medicine',
        'uncategorized-medicine',
    }
    assert child_rows == {'child-medicine'}


@pytest.mark.django_db
def test_unknown_domain_category_never_returns_the_whole_catalog(medicine_catalog):
    queryset = _queryset_for(
        MedicineProductViewSet,
        category_slug='definitely-not-a-real-category',
    )

    assert not queryset.exists()
