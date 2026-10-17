"""SSR-перелинковка карточки: related_links в ответе resolve."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductTranslation
from apps.catalog.services.product_resolve import build_related_links


pytestmark = pytest.mark.django_db


def _product(slug, category, minutes_ago, product_type="supplements", **kwargs):
    product = Product.objects.create(
        name=slug.replace("-", " ").title(),
        slug=slug,
        category=category,
        product_type=product_type,
        **kwargs,
    )
    Product.objects.filter(pk=product.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))
    return product


def test_links_take_older_siblings_then_wrap_to_newest():
    category = Category.objects.create(name="Витамины", slug="related-links-vitamins")
    other = Category.objects.create(name="Другое", slug="related-links-other")
    _product("newest", category, 1)
    _product("current", category, 10)
    _product("older-1", category, 20)
    _product("older-2", category, 30)
    _product("foreign-category", other, 15)
    _product("foreign-type", category, 25, product_type="cosmetics")
    _product("inactive", category, 22, is_active=False)
    _product("shadow-variant", category, 23, external_data={"source_variant_id": 1})

    links = build_related_links("current", "ru", limit=3)

    assert [link["path"] for link in links] == [
        "/product/older-1",
        "/product/older-2",
        "/product/newest",
    ]
    assert links[0]["name"] == "Older 1"


def test_links_use_translation_for_non_default_locale():
    category = Category.objects.create(name="Витамины", slug="related-links-vitamins")
    _product("current", category, 10)
    sibling = _product("sibling", category, 20)
    ProductTranslation.objects.create(product=sibling, locale="en", name="Sibling EN")

    assert build_related_links("current", "en") == [{"name": "Sibling EN", "path": "/product/sibling"}]
    assert build_related_links("current", "ru")[0]["name"] == "Sibling"


def test_links_build_typed_paths_and_stay_two_queries(django_assert_num_queries):
    category = Category.objects.create(name="Платья", slug="related-links-dresses")
    _product("current", category, 10, product_type="clothing")
    for idx in range(10):
        _product(f"dress-{idx}", category, 20 + idx, product_type="clothing")

    with django_assert_num_queries(2):
        links = build_related_links("current", "en")

    assert len(links) == 8
    assert links[0]["path"] == "/product/clothing/dress-0"


def test_no_links_without_category():
    _product("current", None, 10)
    assert build_related_links("current", "ru") == []
