"""Галерея страницы товара читает ``image_url`` — его отдают фото всех разделов."""

import inspect

import pytest
from rest_framework import serializers as drf_serializers
from rest_framework.test import APIClient

from apps.catalog import serializers
from apps.catalog.models import (
    AutoPartProduct,
    AutoPartProductImage,
    Category,
    SportsProduct,
    SportsProductImage,
)


def test_every_image_serializer_returns_image_url():
    """У спорттоваров и автозапчастей поле называлось ``image`` — на странице оставалось одно фото."""
    image_serializers = [
        cls
        for name, cls in inspect.getmembers(serializers, inspect.isclass)
        if name.endswith("ImageSerializer") and issubclass(cls, drf_serializers.ModelSerializer)
    ]

    assert len(image_serializers) > 20
    assert [cls.__name__ for cls in image_serializers if "image_url" not in cls.Meta.fields] == []


@pytest.mark.parametrize(
    ("url", "model", "image_model"),
    [
        ("/api/catalog/auto-parts/products/item-1", AutoPartProduct, AutoPartProductImage),
        ("/api/catalog/sports/products/item-1", SportsProduct, SportsProductImage),
    ],
)
def test_card_gallery_has_urls(db, url, model, image_model):
    category = Category.objects.create(name="Раздел", slug="section")
    product = model.objects.create(name="Товар", slug="item-1", category=category, price=100, currency="TRY")
    image_model.objects.create(product=product, image_file="products/section/item-1/gallery-1.webp")
    image_model.objects.create(product=product, image_url="https://cdn.example.com/gallery-2.webp")

    images = APIClient().get(url).json()["images"]

    assert len(images) == 2
    assert all(image["image_url"] for image in images)
