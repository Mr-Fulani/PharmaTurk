"""Слаг нового товара из парсера открывается по адресу (`<slug:slug>` в URL)."""

import re

import pytest

from apps.catalog.models import Category, Product
from apps.catalog.services import CatalogNormalizer
from apps.vapi.client import ProductData

SLUG_RE = re.compile(r"^[-a-zA-Z0-9_]+$")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "external_id,suffix",
    [
        # Товары SuperStep без вариантов цвета (термос, рюкзак): код цвета с точкой.
        # С 05.11.2026 у SuperStep в слаге нет имени источника.
        ("superstep-13424.0195", "-13424-0195"),
        ("superstep-EK000043D0M1.-", "-ek000043d0m1"),
        ("flo-101792825", "-flo-101792825"),
    ],
)
def test_slug_contains_only_url_safe_part_of_external_id(external_id, suffix):
    """До 04.11.2026 точка из external_id попадала в слаг, и страница товара
    отвечала 404 (у трёх товаров пробного сбора SuperStep)."""
    product = CatalogNormalizer().normalize_product(
        ProductData(
            id=external_id,
            name="Stanley The IceFlow Flip Straw Termos",
            description="",
            price=3329,
            currency="TRY",
            category="tableware",
            brand="Stanley",
            images=[],
            url="https://www.superstep.com.tr/urun/x/13424/",
            availability=True,
            metadata={"source": "superstep", "attributes": {}},
        )
    )

    assert product.external_id == external_id  # сам идентификатор не меняется
    assert product.slug.endswith(suffix)
    assert SLUG_RE.match(product.slug)


def _superstep_sneaker(external_id="superstep-B75806"):
    return ProductData(
        id=external_id,
        name="adidas Samba OG Unisex Beyaz Spor Ayakkabı",
        description="",
        price=5299,
        currency="TRY",
        category="shoes",
        brand="adidas",
        images=[],
        url="https://www.superstep.com.tr/urun/adidas-samba-og/b75806/",
        availability=True,
        metadata={"source": "superstep", "attributes": {"gender": "unisex"}},
    )


@pytest.mark.django_db
def test_superstep_slug_is_russian_title_without_source_name():
    """Адрес — русское название по правилам SEO транслитом: «кроссовки», а не
    «spor-ayakkab-superstep» (решение 05.11.2026, docs/SEO_NONMEDICAL_PRODUCTS.md)."""
    Category.objects.get_or_create(slug="shoes", defaults={"name": "Обувь"})
    product = CatalogNormalizer().normalize_product(_superstep_sneaker())

    assert product.slug == "krossovki-uniseks-adidas-samba-og-b75806"
    assert product.external_id == "superstep-B75806"


@pytest.mark.django_db
def test_superstep_slug_keeps_source_prefix_when_ru_slug_is_taken_and_never_changes_on_update():
    Category.objects.get_or_create(slug="shoes", defaults={"name": "Обувь"})
    Product.objects.create(name="Кроссовки adidas Samba OG", slug="krossovki-uniseks-adidas-samba-og-b75806", product_type="shoes")

    product = CatalogNormalizer().normalize_product(_superstep_sneaker())
    assert product.slug.endswith("-superstep-B75806")

    again = CatalogNormalizer().normalize_product(_superstep_sneaker())
    assert again.pk == product.pk and again.slug == product.slug
