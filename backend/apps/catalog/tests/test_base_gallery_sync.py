"""Дополнительные фото, изменённые в «Товарах» (Product), попадают в галерею карточки раздела.

17.11.2026 владелец добавил фото KADCYLA в общей таблице товаров (ProductImage 129): страница
товара читает галерею MedicineProduct и показывала прежнюю картинку.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib import admin

from apps.catalog.admin import ProductAdmin
from apps.catalog.domain_sync import base_gallery_snapshot, sync_base_gallery_to_domain
from apps.catalog.models import (
    Category,
    ClothingProduct,
    ClothingProductImage,
    ClothingVariant,
    ClothingVariantImage,
    MedicineProduct,
    MedicineProductImage,
    Product,
    ProductImage,
)

pytestmark = pytest.mark.django_db

PARSER = "products/medicines/kadcyla/kadcyla-gallery-de204911fe.jpg"
NEW = "products/medicines/kadcyla/kadcyla-roche-gallery-f2e062ed61.webp"
NEWER = "products/medicines/kadcyla/kadcyla-roche-gallery-2.webp"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.catalog.signals._download_url_to_file", lambda url: None)


@pytest.fixture
def medicine():
    """Лекарство после парсера: одно фото в галерее карточки раздела, в «Товарах» галерея пустая."""
    category = Category.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})[0]
    item = MedicineProduct.objects.create(
        name="KADCYLA", slug="kadcyla-100", category=category, price=Decimal("120"), currency="TRY", is_active=True,
    )
    item.refresh_from_db()
    MedicineProductImage.objects.create(product=item, image_file=PARSER, sort_order=0, is_main=True)
    return SimpleNamespace(item=item, product=Product.objects.get(pk=item.base_product_id))


def _gallery(item):
    return [
        (row.image_file.name or row.image_url, row.sort_order, row.is_main)
        for row in item.gallery_images.order_by("sort_order", "pk")
    ]


def _add(medicine, **values):
    """Строка, добавленная в форме «Товары» и уже перенесённая в карточку раздела."""
    before = base_gallery_snapshot(medicine.product)
    row = ProductImage.objects.create(product=medicine.product, **values)
    assert sync_base_gallery_to_domain(medicine.product, before) == ""
    return row


def test_new_photo_is_added_next_to_parser_photos(medicine):
    _add(medicine, image_file=NEW, alt_text="KADCYLA Roche", sort_order=1)

    assert _gallery(medicine.item) == [(PARSER, 0, True), (NEW, 1, False)]
    assert medicine.item.gallery_images.get(image_file=NEW).alt_text == "KADCYLA Roche"


def test_replaced_file_updates_the_same_row(medicine):
    row = _add(medicine, image_file=NEW, sort_order=1)
    pair_pk = medicine.item.gallery_images.get(image_file=NEW).pk

    before = base_gallery_snapshot(medicine.product)
    ProductImage.objects.filter(pk=row.pk).update(image_file=NEWER)
    sync_base_gallery_to_domain(medicine.product, before)

    assert _gallery(medicine.item) == [(PARSER, 0, True), (NEWER, 1, False)]
    assert medicine.item.gallery_images.get(image_file=NEWER).pk == pair_pk


def test_deleted_photo_removes_only_its_pair_and_keeps_files(
    medicine, monkeypatch, django_capture_on_commit_callbacks,
):
    row = _add(medicine, image_file=NEW, sort_order=1)
    storage_deletes = []
    monkeypatch.setattr(
        "apps.catalog.signals._delete_storage_key_if_unreferenced",
        lambda path, storage=None: storage_deletes.append(path),
    )

    before = base_gallery_snapshot(medicine.product)
    ProductImage.objects.filter(pk=row.pk)._raw_delete(ProductImage.objects.db)
    with django_capture_on_commit_callbacks(execute=True):
        sync_base_gallery_to_domain(medicine.product, before)

    assert _gallery(medicine.item) == [(PARSER, 0, True)]
    assert storage_deletes == []


def test_order_and_main_flag_follow_the_base_row(medicine):
    row = _add(medicine, image_file=NEW, sort_order=5)

    before = base_gallery_snapshot(medicine.product)
    ProductImage.objects.filter(pk=row.pk).update(sort_order=0, is_main=True)
    sync_base_gallery_to_domain(medicine.product, before)

    assert sorted(_gallery(medicine.item)) == [(PARSER, 0, False), (NEW, 0, True)]


def test_same_photo_is_not_duplicated(medicine):
    _add(medicine, image_file=PARSER, sort_order=3)

    assert _gallery(medicine.item) == [(PARSER, 3, False)]


def test_untouched_rows_are_not_copied(medicine):
    ProductImage.objects.create(product=medicine.product, image_file=NEW)

    before = base_gallery_snapshot(medicine.product)
    assert sync_base_gallery_to_domain(medicine.product, before) == ""

    assert _gallery(medicine.item) == [(PARSER, 0, True)]


def test_section_with_variant_photos_is_skipped():
    category = Category.objects.get_or_create(slug="clothing", defaults={"name": "Clothing"})[0]
    product = Product.objects.create(
        name="Elbise", slug="elbise-1", product_type="clothing", category=category, price=100, currency="TRY",
    )
    clothing = ClothingProduct.objects.get(base_product=product)
    variant = ClothingVariant.objects.create(product=clothing, name="Elbise - SİYAH", color="SİYAH")
    ClothingVariantImage.objects.create(variant=variant, image_file="products/clothing/variants/elbise/1.jpg")

    before = base_gallery_snapshot(product)
    ProductImage.objects.create(product=product, image_file="products/clothing/elbise/extra.jpg")

    assert sync_base_gallery_to_domain(product, before) == "variants"
    assert ClothingProductImage.objects.filter(product=clothing).count() == 0


def test_products_admin_form_passes_gallery_edits(medicine, monkeypatch):
    def save_formset(self, request, form, formset, change):
        ProductImage.objects.create(product=form.instance, image_file=NEW, sort_order=1)

    monkeypatch.setattr(admin.ModelAdmin, "save_formset", save_formset)

    ProductAdmin(Product, admin.site).save_formset(
        None, SimpleNamespace(instance=medicine.product), SimpleNamespace(model=ProductImage), True,
    )

    assert _gallery(medicine.item) == [(PARSER, 0, True), (NEW, 1, False)]
