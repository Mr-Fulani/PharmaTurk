from types import SimpleNamespace

import pytest
from django.contrib.contenttypes.models import ContentType
from django.http import QueryDict

from apps.catalog.models import (
    AccessoryProduct,
    Category,
    CategoryType,
    GlobalAttributeKey,
    ProductAttributeValue,
)
from apps.catalog.views import FacetedModelViewSetMixin


def _build_request():
    query_dict = QueryDict("", mutable=True)
    return SimpleNamespace(query_params=query_dict, _request=SimpleNamespace(GET=query_dict.copy()))


@pytest.mark.django_db
def test_available_attributes_excludes_single_value_and_non_facet_dynamic_attributes():
    category_type = CategoryType.objects.create(slug="accessories", name="Accessories")
    category = Category.objects.create(
        name="Аксессуары",
        slug="test-accessories-facets",
        description="Аксессуары",
        category_type=category_type,
    )
    product_one = AccessoryProduct.objects.create(
        name="Аксессуар 1",
        slug="test-accessory-1",
        description="Товар",
        category=category,
        price=100,
        currency="TRY",
        is_active=True,
    )
    product_two = AccessoryProduct.objects.create(
        name="Аксессуар 2",
        slug="test-accessory-2",
        description="Товар",
        category=category,
        price=100,
        currency="TRY",
        is_active=True,
    )

    key_material = GlobalAttributeKey.objects.create(slug="material", name="Материал")
    key_case_material = GlobalAttributeKey.objects.create(slug="case-material", name="Материал корпуса")
    key_accessory_type = GlobalAttributeKey.objects.create(slug="accessory-type", name="Тип аксессуара")
    content_type = ContentType.objects.get_for_model(AccessoryProduct)

    ProductAttributeValue.objects.create(
        content_type=content_type,
        object_id=product_one.id,
        attribute_key=key_material,
        value="Кожа",
        value_ru="Кожа",
    )
    ProductAttributeValue.objects.create(
        content_type=content_type,
        object_id=product_two.id,
        attribute_key=key_material,
        value="Ткань",
        value_ru="Ткань",
    )
    ProductAttributeValue.objects.create(
        content_type=content_type,
        object_id=product_one.id,
        attribute_key=key_case_material,
        value="Сталь",
        value_ru="Сталь",
    )
    ProductAttributeValue.objects.create(
        content_type=content_type,
        object_id=product_two.id,
        attribute_key=key_case_material,
        value="Сталь",
        value_ru="Сталь",
    )
    ProductAttributeValue.objects.create(
        content_type=content_type,
        object_id=product_one.id,
        attribute_key=key_accessory_type,
        value="Сумка",
        value_ru="Сумка",
    )
    ProductAttributeValue.objects.create(
        content_type=content_type,
        object_id=product_two.id,
        attribute_key=key_accessory_type,
        value="Сумка",
        value_ru="Сумка",
    )

    class _FacetView(FacetedModelViewSetMixin):
        pass

    view = _FacetView()
    view.request = _build_request()

    available = view._calculate_available_attributes(
        AccessoryProduct.objects.filter(pk__in=[product_one.pk, product_two.pk]).order_by("pk")
    )

    assert available == [
        {
            "key": "material",
            "name": "Материал",
            "values": ["Кожа", "Ткань"],
        }
    ]
