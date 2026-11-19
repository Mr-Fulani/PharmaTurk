"""Блок аналогов показывает то же главное фото, что и карточка лекарства.

18.11.2026: владелец заменил фото PROPOFOL-PF в админке — карточка показала новое, блок
аналогов у соседних препаратов — прежнее (брал ссылку main_image или первую картинку галереи).
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Category, MedicineProduct, MedicineProductImage, Product

pytestmark = pytest.mark.django_db

NEW = "products/medicines/propofol/propofol-polifarma-main-new.webp"


@pytest.fixture(autouse=True)
def no_currency_refresh(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)


def _medicine(slug, **extra):
    category = Category.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})[0]
    return MedicineProduct.objects.create(
        name=slug.upper(), slug=slug, category=category, active_ingredient="Propofol",
        atc_code="N01AX10", price=Decimal("120"), currency="TRY", is_active=True, **extra,
    )


def test_analog_block_uses_uploaded_main_photo():
    _medicine("propofol-a")
    analog = _medicine("propofol-b", main_image="https://example.com/old-placeholder.jpg")
    MedicineProduct.objects.filter(pk=analog.pk).update(main_image_file=NEW)
    client = APIClient()

    payload = client.get("/api/catalog/medicines/products/propofol-a/analogs").json()
    card = client.get("/api/catalog/medicines/products/propofol-b").json()

    row = next(item for item in payload["results"] if item["slug"] == "propofol-b")
    assert "propofol-polifarma-main-new.webp" in row["main_image_url"]
    assert row["main_image_url"] == card["main_image_url"]


def test_analog_block_uses_gallery_file_over_stale_link():
    """19.11.2026: главное фото из админки встаёт файлом в кадр галереи, ссылка кадра прежняя."""
    _medicine("propofol-a")
    analog = _medicine("propofol-b")
    MedicineProductImage.objects.create(
        product=analog, image_url="https://example.com/old-gallery.jpg", image_file=NEW, is_main=True,
    )

    payload = APIClient().get("/api/catalog/medicines/products/propofol-a/analogs").json()

    row = next(item for item in payload["results"] if item["slug"] == "propofol-b")
    assert "propofol-polifarma-main-new.webp" in row["main_image_url"]
