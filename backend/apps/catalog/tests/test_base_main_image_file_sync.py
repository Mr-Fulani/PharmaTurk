"""Главное фото, загруженное в «Товарах» (Product), попадает и в карточку раздела.

17.11.2026 владелец заменил фото KADCYLA и PROPOFOL-PF в общей таблице товаров: витрина
(читает Product) показала новое фото, страница товара (читает MedicineProduct) — старое.
"""

from decimal import Decimal

import pytest

from apps.catalog.domain_sync import ensure_domain_product_for_base
from apps.catalog.models import Category, MedicineProduct, Product

pytestmark = pytest.mark.django_db

OLD = "products/medicines/kadcyla/kadcyla-main-old.jpg"
NEW = "products/medicines/kadcyla/kadcyla-roche-main-new.webp"


@pytest.fixture(autouse=True)
def no_currency_refresh(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)


@pytest.fixture
def medicine():
    category = Category.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})[0]
    item = MedicineProduct.objects.create(
        name="KADCYLA", slug="kadcyla-100", category=category, price=Decimal("120"), currency="TRY", is_active=True,
    )
    item.refresh_from_db()
    assert item.base_product_id
    return item


def _file_name(model, pk):
    return model.objects.filter(pk=pk).values_list("main_image_file", flat=True).get() or ""


def test_new_base_photo_replaces_domain_photo(medicine):
    MedicineProduct.objects.filter(pk=medicine.pk).update(main_image_file=OLD)
    Product.objects.filter(pk=medicine.base_product_id).update(main_image_file=NEW)

    ensure_domain_product_for_base(Product.objects.get(pk=medicine.base_product_id))

    assert _file_name(MedicineProduct, medicine.pk) == NEW


def test_base_without_photo_keeps_domain_photo(medicine):
    MedicineProduct.objects.filter(pk=medicine.pk).update(main_image_file=OLD)
    Product.objects.filter(pk=medicine.base_product_id).update(main_image_file="")

    ensure_domain_product_for_base(Product.objects.get(pk=medicine.base_product_id))

    assert _file_name(MedicineProduct, medicine.pk) == OLD
