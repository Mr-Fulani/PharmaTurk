"""Слаг нового товара из парсера открывается по адресу (`<slug:slug>` в URL)."""

import re

import pytest

from apps.catalog.services import CatalogNormalizer
from apps.vapi.client import ProductData

SLUG_RE = re.compile(r"^[-a-zA-Z0-9_]+$")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "external_id,suffix",
    [
        # Товары SuperStep без вариантов цвета (термос, рюкзак): код цвета с точкой.
        ("superstep-13424.0195", "-superstep-13424-0195"),
        ("superstep-EK000043D0M1.-", "-superstep-EK000043D0M1"),
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
