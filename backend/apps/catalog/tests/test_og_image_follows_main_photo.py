"""Превью ссылки (og:image) показывает загруженное главное фото, а не сохранённый снимок.

18.11.2026: после замены фото лекарства в админке в превью при отправке ссылки оставалась
старая картинка — og_image_url записан при генерации карточки и был главнее нового фото.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Category, MedicineProduct, Product

pytestmark = pytest.mark.django_db

STALE = "https://cdn.mudaroba.com/products/medicines/kadcyla/kadcyla-gallery-old.jpg"
NEW = "products/medicines/kadcyla/kadcyla-roche-main-new.webp"


@pytest.fixture(autouse=True)
def no_currency_refresh(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)


def _card(slug, **fields):
    category = Category.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})[0]
    item = MedicineProduct.objects.create(
        name=slug.upper(), slug=slug, category=category, price=Decimal("120"), currency="TRY", is_active=True,
    )
    MedicineProduct.objects.filter(pk=item.pk).update(**fields)
    return APIClient().get(f"/api/catalog/medicines/products/{slug}").json()


def test_uploaded_main_photo_wins_over_saved_og_image():
    card = _card("kadcyla-new", og_image_url=STALE, main_image_file=NEW)

    assert "kadcyla-roche-main-new.webp" in card["og_image_url"]
    assert card["og_image_url"] == card["main_image_url"]


def test_saved_og_image_is_kept_without_uploaded_photo():
    card = _card("kadcyla-old", og_image_url=STALE)

    assert "kadcyla-gallery-old.jpg" in card["og_image_url"]
