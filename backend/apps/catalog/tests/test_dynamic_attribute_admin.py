import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from apps.catalog.admin import ProductAttributeValueAdmin
from apps.catalog.models import (
    AccessoryProduct,
    GlobalAttributeKey,
    GlobalAttributeKeyTranslation,
    ProductAttributeValue,
)


pytestmark = pytest.mark.django_db


def test_dynamic_attribute_admin_exposes_product_identity_without_row_n_plus_one(
    django_assert_num_queries,
):
    key = GlobalAttributeKey.objects.create(slug="admin-material", sort_order=1)
    GlobalAttributeKeyTranslation.objects.create(
        key_obj=key,
        locale="ru",
        name="Материал",
    )
    product = AccessoryProduct.objects.create(
        name="Ремень",
        slug="admin-attribute-belt",
        external_id="belt-123",
        external_url="https://example.com/belt-123",
    )
    product.refresh_from_db()
    ProductAttributeValue.objects.create(
        content_object=product,
        attribute_key=key,
        value="Кожа",
        value_ru="Кожа",
    )
    model_admin = ProductAttributeValueAdmin(ProductAttributeValue, AdminSite())
    request = RequestFactory().get("/admin/catalog/productattributevalue/")
    row = model_admin.get_queryset(request).get()

    with django_assert_num_queries(0):
        assert model_admin.attribute_label(row) == "Материал"
        assert model_admin.product_label(row) == "Ремень"
        identity = str(model_admin.product_identity(row))

    assert f"accessoryproduct #{product.pk}" in identity
    assert f"base #{product.base_product_id}" in identity
    assert "ext: belt-123" in identity
    assert "https://example.com/belt-123" in identity
