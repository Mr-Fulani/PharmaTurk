"""
История slug товаров: смена slug пишет старый в ProductSlugHistory, resolve по
старому slug отдаёт товар с canonical_path на новый URL (фронт → 301, §5.4).
"""

import uuid

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import (
    Category,
    ClothingProduct,
    MedicineProduct,
    Product,
    ProductSlugHistory,
)


def _suffix():
    return uuid.uuid4().hex[:8]


def _medicine(slug):
    category = Category.objects.create(name=f"Cat {slug}", slug=f"cat-{slug}")
    return MedicineProduct.objects.create(
        name="Solian 400 mg 30 film tablet",
        slug=slug,
        category=category,
        price=100,
        currency="TRY",
        is_active=True,
    )


def _resolve(slug):
    return APIClient().get(f"/api/catalog/products/resolve/{slug}")


@pytest.mark.django_db
def test_domain_rename_like_ai_applier_redirects_old_slug():
    s = _suffix()
    old_slug, new_slug = f"solian-400-mg-30-film-tablet-{s}", f"solian-400-mg-30-film-tabletki-{s}"
    medicine = _medicine(old_slug)
    medicine.refresh_from_db()
    assert medicine.base_product.slug == old_slug

    # Как result_applier: name+slug через update_fields
    medicine.name = "Солиан 400 мг 30 таблеток"
    medicine.slug = new_slug
    medicine.save(update_fields=["name", "slug"])

    row = ProductSlugHistory.objects.get(old_slug=old_slug)
    assert row.product_id == medicine.base_product_id
    assert row.product_type == "medicines"

    response = _resolve(old_slug)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["payload"]["slug"] == new_slug
    assert response.data["canonical_path"] == f"/product/{new_slug}"


@pytest.mark.django_db
def test_type_in_path_rename_canonical_keeps_type_segment():
    s = _suffix()
    category = Category.objects.create(name=f"Cat {s}", slug=f"cat-{s}")
    item = ClothingProduct.objects.create(
        name="Shirt", slug=f"shirt-old-{s}", category=category, price=10, currency="TRY", is_active=True
    )
    item.refresh_from_db()  # create() не видит base_product, проставленный сигналом
    item.slug = f"shirt-new-{s}"
    item.save()

    response = _resolve(f"shirt-old-{s}")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["canonical_path"] == f"/product/clothing/shirt-new-{s}"


@pytest.mark.django_db
def test_generic_product_rename_redirects_old_slug():
    s = _suffix()
    product = Product.objects.create(
        name="Bag", slug=f"bag-old-{s}", product_type="bags", price=10, currency="TRY", is_active=True
    )
    product.slug = f"bag-new-{s}"
    product.save()

    assert ProductSlugHistory.objects.filter(old_slug=f"bag-old-{s}", product=product).exists()
    response = _resolve(f"bag-old-{s}")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["canonical_path"] == f"/product/bag-new-{s}"


@pytest.mark.django_db
def test_chain_of_renames_points_to_current_slug():
    s = _suffix()
    product = Product.objects.create(name="Bag", slug=f"a-{s}", product_type="bags", is_active=True)
    for slug in (f"b-{s}", f"c-{s}"):
        product.slug = slug
        product.save()

    for old in (f"a-{s}", f"b-{s}"):
        assert _resolve(old).data["canonical_path"] == f"/product/c-{s}"


@pytest.mark.django_db
def test_slug_taken_again_removes_history_and_live_product_wins():
    s = _suffix()
    first = Product.objects.create(name="First", slug=f"x-{s}", product_type="bags", is_active=True)
    first.slug = f"x-renamed-{s}"
    first.save()
    assert ProductSlugHistory.objects.filter(old_slug=f"x-{s}").exists()

    second = Product.objects.create(name="Second", slug=f"x-{s}", product_type="bags", is_active=True)
    assert not ProductSlugHistory.objects.filter(old_slug=f"x-{s}").exists()
    assert _resolve(f"x-{s}").data["payload"]["id"] == second.id

    # Возврат прежнего slug тоже убирает его из истории
    first.slug = f"y-{s}"
    first.save()
    first.slug = f"x-renamed-{s}"
    first.save()
    assert not ProductSlugHistory.objects.filter(old_slug=f"x-renamed-{s}").exists()


@pytest.mark.django_db
def test_save_without_slug_change_writes_nothing():
    s = _suffix()
    medicine = _medicine(f"keep-{s}")
    medicine.refresh_from_db()
    medicine.name = "Renamed only"
    medicine.save()
    medicine.price = 200
    medicine.save(update_fields=["price"])
    assert not ProductSlugHistory.objects.filter(product=medicine.base_product).exists()


@pytest.mark.django_db
def test_deleted_product_old_slug_is_404():
    s = _suffix()
    product = Product.objects.create(name="Bag", slug=f"gone-{s}", product_type="bags", is_active=True)
    product.slug = f"gone-new-{s}"
    product.save()
    product.delete()

    assert not ProductSlugHistory.objects.filter(old_slug=f"gone-{s}").exists()
    assert _resolve(f"gone-{s}").status_code == status.HTTP_404_NOT_FOUND
