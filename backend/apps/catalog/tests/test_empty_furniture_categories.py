"""Пустые разделы мебели не показываются в списках категорий (решение владельца 27.10.2026)."""

from decimal import Decimal

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product
from apps.catalog.views import EMPTY_FURNITURE_CATEGORIES_CACHE_KEY


@pytest.fixture
def furniture(monkeypatch):
    monkeypatch.setattr(Product, 'update_currency_prices', lambda *args, **kwargs: None)
    cache.delete(EMPTY_FURNITURE_CATEGORIES_CACHE_KEY)

    def category(slug, name, parent=None):
        return Category.objects.update_or_create(
            slug=slug, defaults={'name': name, 'parent': parent, 'is_active': True},
        )[0]

    root = category('furniture', 'Мебель')
    living = category('living-room', 'Гостиная', root)
    sofas = category('sofas', 'Диваны', living)
    category('pouffes', 'Пуфы', living)
    office = category('office', 'Офисная мебель', root)
    category('office-desks', 'Офисные столы', office)
    Product.objects.create(
        name='Диван KIVIK', slug='kivik-test', product_type='furniture', category=sofas,
        price=Decimal('100'), currency='TRY', is_active=True,
    )
    yield {'root': root, 'living': living, 'sofas': sofas, 'office': office}
    cache.delete(EMPTY_FURNITURE_CATEGORIES_CACHE_KEY)


def _slugs(response):
    payload = response.json()
    return {row['slug'] for row in payload.get('results', payload)}


@pytest.mark.django_db
def test_empty_furniture_sections_are_hidden_in_lists(furniture):
    client = APIClient()

    tree = _slugs(client.get('/api/catalog/categories', {'slug': 'furniture', 'page_size': 500}))
    assert {'furniture', 'living-room', 'sofas'} <= tree
    assert not {'pouffes', 'office', 'office-desks'} & tree

    children = _slugs(client.get('/api/catalog/categories', {'parent_slug': 'furniture', 'page_size': 200}))
    assert children == {'living-room'}

    everything = _slugs(client.get('/api/catalog/categories', {'all': 'true', 'page_size': 1000}))
    assert 'office' not in everything and 'sofas' in everything


@pytest.mark.django_db
def test_requested_empty_section_still_opens(furniture):
    client = APIClient()

    assert 'office' in _slugs(client.get('/api/catalog/categories', {'slug': 'office', 'page_size': 50}))
    assert client.get('/api/catalog/categories/office').status_code == 200


@pytest.mark.django_db
def test_section_appears_when_a_product_arrives(furniture):
    Product.objects.create(
        name='Стол BEKANT', slug='bekant-test', product_type='furniture',
        category=Category.objects.get(slug='office-desks'), price=Decimal('100'), currency='TRY', is_active=True,
    )
    cache.delete(EMPTY_FURNITURE_CATEGORIES_CACHE_KEY)

    children = _slugs(APIClient().get('/api/catalog/categories', {'parent_slug': 'furniture', 'page_size': 200}))
    assert children == {'living-room', 'office'}
