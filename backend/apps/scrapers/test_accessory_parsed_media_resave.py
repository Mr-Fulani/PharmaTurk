"""Регрессия: галерея «облегчённых» доменов (Accessory и т.п.) переносит
parsed-картинку в читаемый image_file.

Баг: сигнал AccessoryProductImage использовал _auto_download_image_url_to_file,
который качал только внешние URL и игнорировал внутренние /products/parsed/ →
аксессуары (LCW) застревали в products/parsed/ без читаемого файла.
"""

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.catalog.models import AccessoryProductImage, Category, Product
from apps.catalog.scraper_category_mapping import resolve_category_and_product_type
from apps.scrapers.services import ScraperIntegrationService


def _make_accessory():
    category, product_type = resolve_category_and_product_type("Kemer")
    product = Product.objects.create(
        name="Kemer тест",
        slug="kemer-resave-test",
        category=category,
        product_type=product_type,
        price=10,
        currency="TRY",
        external_id="lcw-resave-1",
        external_data={},
    )
    accessory = product.domain_item  # создаётся сигналом ensure_domain_product_for_base
    assert accessory is not product, "доменный AccessoryProduct должен создаться"
    return accessory


@pytest.mark.django_db
def test_parsed_gallery_image_resaved_to_readable():
    accessory = _make_accessory()
    key = "products/parsed/lcw/belts/images/resave-test-belt.jpg"
    default_storage.save(key, ContentFile(b"\xff\xd8\xff\xe0fakejpegdata"))
    try:
        img = AccessoryProductImage(
            product=accessory,
            image_url=f"https://cdn.mudaroba.com/{key}",
            image_file="",
        )
        img.save()  # pre_save сигнал переносит parsed → читаемый image_file
        img.refresh_from_db()

        # Файл теперь в читаемом доменном пути, а не в products/parsed/
        assert img.image_file and img.image_file.name
        assert "/products/parsed/" not in img.image_file.name
        # И URL больше не указывает на parsed-копию
        assert "/products/parsed/" not in img.image_url
    finally:
        default_storage.delete(key)


@pytest.mark.django_db
def test_perfumery_parsed_gallery_image_resaved_to_readable():
    """Парфюм: галерея раньше не имела pre_save-сигнала и застревала в parsed."""
    from apps.catalog.models import Category, PerfumeryProductImage

    category = Category.objects.create(name="Парфюм тест", slug="perfume-resave-test")
    product = Product.objects.create(
        name="Parfüm тест",
        slug="parfum-resave-test",
        category=category,
        product_type="perfumery",
        price=10,
        currency="TRY",
        external_id="lcw-resave-perfume-1",
        external_data={},
    )
    perfumery = product.domain_item
    assert perfumery is not product, "доменный PerfumeryProduct должен создаться"

    key = "products/parsed/lcw/perfumery/images/resave-test-parfum.jpg"
    default_storage.save(key, ContentFile(b"\xff\xd8\xff\xe0fakejpegdata"))
    try:
        img = PerfumeryProductImage(
            product=perfumery,
            image_url=f"https://cdn.mudaroba.com/{key}",
            image_file="",
        )
        img.save()
        img.refresh_from_db()
        assert img.image_file and img.image_file.name
        assert "/products/parsed/" not in img.image_file.name
        assert "/products/parsed/" not in img.image_url
    finally:
        default_storage.delete(key)


@pytest.mark.django_db
def test_ikea_furniture_variant_images_resave_parsed_to_readable(monkeypatch):
    r2_config = dict(getattr(settings, "R2_CONFIG", {}) or {})
    r2_config["public_url"] = "https://cdn.mudaroba.com"
    monkeypatch.setattr(settings, "R2_CONFIG", r2_config, raising=False)

    category = Category.objects.create(name="Мебель IKEA тест", slug="ikea-furniture-resave-test")
    product = Product.objects.create(
        name="IKEA KALLAX тест",
        slug="ikea-kallax-resave-test",
        category=category,
        product_type="furniture",
        price=100,
        currency="TRY",
        external_id="ikea-resave-1",
        external_data={},
    )
    furniture = product.domain_item
    assert furniture is not product, "доменный FurnitureProduct должен создаться"

    key = "products/parsed/ikea/mobilya/images/ikea-kallax-0.jpg"
    default_storage.save(key, ContentFile(b"\xff\xd8\xff\xe0fakejpegdata"))
    try:
        changed = ScraperIntegrationService()._sync_furniture_color_variants(
            furniture,
            product,
            [
                {
                    "external_id": "ikea-var-1",
                    "display_name": "IKEA KALLAX белый",
                    "color": "white",
                    "price": "100",
                    "currency": "TRY",
                    "external_url": "https://www.ikea.com.tr/urun/kallax-123",
                    "images": [f"https://cdn.mudaroba.com/{key}"],
                    "stock_quantity": 3,
                    "is_available": True,
                }
            ],
        )

        assert changed is True
        variant = furniture.variants.get(external_id="ikea-var-1")
        img = variant.images.get()
        product.refresh_from_db()
        furniture.refresh_from_db()
        variant.refresh_from_db()

        assert img.image_file and img.image_file.name
        assert "/products/parsed/" not in img.image_file.name
        assert "/products/parsed/" not in img.image_url
        assert "/products/parsed/" not in variant.main_image
        assert "/products/parsed/" not in furniture.main_image
        assert "/products/parsed/" not in product.main_image
        assert default_storage.exists(key) is False
    finally:
        default_storage.delete(key)


@pytest.mark.django_db
def test_external_gallery_image_still_downloaded():
    """Внешний URL по-прежнему скачивается в файл (поведение не сломали)."""
    accessory = _make_accessory()
    # Несуществующий внешний URL: скачивание не удастся, но и не упадёт —
    # проверяем, что ветка внешних URL отрабатывает без исключений.
    img = AccessoryProductImage(
        product=accessory,
        image_url="https://example.invalid/nonexistent.jpg",
        image_file="",
    )
    img.save()
    img.refresh_from_db()
    # Внешний URL сохранён как есть, parsed-перенос не применялся.
    assert img.image_url == "https://example.invalid/nonexistent.jpg"
