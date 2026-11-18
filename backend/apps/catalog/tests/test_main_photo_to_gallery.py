"""Одна загрузка главного фото — одно фото и на витрине, и на странице товара.

Страница товара при непустой галерее главное фото отдельно не показывает: первым идёт кадр
галереи (у парсерных лекарств это копия главного). 17–18.11.2026 владелец менял главное фото
KADCYLA, а страница показывала прежний кадр, пока его не заменили и в галерее.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.urls import reverse

from apps.catalog.admin import ProductAdmin
from apps.catalog.admin_wave2 import MedicineProductAdmin
from apps.catalog.domain_sync import apply_main_photo_to_gallery
from apps.catalog.models import (
    Category,
    ClothingProduct,
    ClothingProductImage,
    ClothingVariant,
    ClothingVariantImage,
    MedicineProduct,
    MedicineProductImage,
    Product,
)

pytestmark = pytest.mark.django_db

OLD_URL = "https://cdn.mudaroba.com/products/medicines/kadcyla/kadcyla-gallery-de204911fe.jpg"
OLD = "products/medicines/kadcyla/kadcyla-gallery-de204911fe.jpg"
SIDE = "products/medicines/kadcyla/kadcyla-side.jpg"
NEW = "products/medicines/main/images/kadcyla-roche-main-new.webp"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.catalog.signals._download_url_to_file", lambda url: None)


@pytest.fixture
def medicine():
    """Лекарство, которому в админке только что заменили главное фото."""
    category = Category.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})[0]
    item = MedicineProduct.objects.create(
        name="KADCYLA", slug="kadcyla-100", category=category, price=Decimal("120"), currency="TRY", is_active=True,
    )
    MedicineProduct.objects.filter(pk=item.pk).update(main_image_file=NEW)
    item.refresh_from_db()
    Product.objects.filter(pk=item.base_product_id).update(main_image_file=NEW)
    return item


def _add(item, file_name, **values):
    return MedicineProductImage.objects.bulk_create(
        [MedicineProductImage(product=item, image_file=file_name, **values)]
    )[0]


def _gallery(item):
    return [(row.image_file.name, row.is_main) for row in item.gallery_images.order_by("-is_main", "sort_order", "pk")]


def test_main_row_gets_the_new_file_and_keeps_parser_url(medicine):
    main = _add(medicine, OLD, image_url=OLD_URL, is_main=True)
    _add(medicine, SIDE, sort_order=1)

    assert apply_main_photo_to_gallery(medicine) == ""

    assert _gallery(medicine) == [(NEW, True), (SIDE, False)]
    main.refresh_from_db()
    # По адресу парсер узнаёт уже загруженный кадр и не добавляет его повторно.
    assert main.image_url == OLD_URL


def test_single_photo_without_main_flag_is_replaced(medicine):
    _add(medicine, OLD)

    apply_main_photo_to_gallery(medicine)

    assert _gallery(medicine) == [(NEW, True)]


def test_several_photos_without_main_get_a_new_main_one(medicine):
    _add(medicine, OLD, sort_order=0)
    _add(medicine, SIDE, sort_order=1)

    apply_main_photo_to_gallery(medicine)

    assert _gallery(medicine) == [(NEW, True), (OLD, False), (SIDE, False)]


def test_empty_gallery_stays_empty(medicine):
    assert apply_main_photo_to_gallery(medicine) == ""

    assert _gallery(medicine) == []


def test_second_call_and_own_gallery_edit_do_not_duplicate(medicine):
    _add(medicine, OLD, sort_order=0)
    _add(medicine, SIDE, sort_order=1)

    apply_main_photo_to_gallery(medicine)
    apply_main_photo_to_gallery(medicine)
    # То же из «Товаров»: файл уже в галерее карточки раздела.
    apply_main_photo_to_gallery(Product.objects.get(pk=medicine.base_product_id))

    assert _gallery(medicine) == [(NEW, True), (OLD, False), (SIDE, False)]


def test_base_product_updates_gallery_of_its_section_card(medicine):
    _add(medicine, OLD, is_main=True)

    apply_main_photo_to_gallery(Product.objects.get(pk=medicine.base_product_id))

    assert _gallery(medicine) == [(NEW, True)]


def test_product_with_variant_photos_is_skipped():
    category = Category.objects.get_or_create(slug="clothing", defaults={"name": "Clothing"})[0]
    product = Product.objects.create(
        name="Elbise", slug="elbise-1", product_type="clothing", category=category, price=100, currency="TRY",
    )
    clothing = ClothingProduct.objects.get(base_product=product)
    variant = ClothingVariant.objects.create(product=clothing, name="Elbise - SİYAH", color="SİYAH")
    ClothingVariantImage.objects.create(variant=variant, image_file="products/clothing/variants/elbise/1.jpg")
    shared = ClothingProductImage.objects.bulk_create(
        [ClothingProductImage(product=clothing, image_file="products/clothing/elbise/old.jpg", is_main=True)]
    )[0]
    ClothingProduct.objects.filter(pk=clothing.pk).update(main_image_file="products/clothing/main/new.webp")
    clothing.refresh_from_db()

    assert apply_main_photo_to_gallery(clothing) == "variants"

    shared.refresh_from_db()
    assert shared.image_file.name == "products/clothing/elbise/old.jpg"


@pytest.mark.parametrize("admin_class, model", [(MedicineProductAdmin, MedicineProduct), (ProductAdmin, Product)])
def test_admin_form_applies_rule_only_when_main_photo_changed(medicine, monkeypatch, admin_class, model):
    _add(medicine, OLD, is_main=True)
    monkeypatch.setattr(admin.ModelAdmin, "save_related", lambda *args, **kwargs: None)
    instance = medicine if model is MedicineProduct else Product.objects.get(pk=medicine.base_product_id)
    model_admin = admin_class(model, admin.site)

    model_admin.save_related(None, SimpleNamespace(instance=instance, changed_data=["name"]), [], True)
    assert _gallery(medicine) == [(OLD, True)]

    model_admin.save_related(None, SimpleNamespace(instance=instance, changed_data=["main_image_file"]), [], True)
    assert _gallery(medicine) == [(NEW, True)]


def test_medicine_form_shows_main_photo_and_gallery_previews(medicine, admin_client):
    _add(medicine, SIDE)

    html = admin_client.get(reverse("admin:catalog_medicineproduct_change", args=[medicine.pk])).content.decode()

    assert "proxy-media/?path=products%2Fmedicines%2Fmain%2Fimages%2Fkadcyla-roche-main-new.webp" in html
    assert "proxy-media/?path=products%2Fmedicines%2Fkadcyla%2Fkadcyla-side.jpg" in html
