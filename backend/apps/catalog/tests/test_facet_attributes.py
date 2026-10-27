from types import SimpleNamespace

import pytest
from django.contrib.contenttypes.models import ContentType
from django.http import QueryDict
from django.utils import translation

from apps.catalog.models import (
    AccessoryProduct,
    Category,
    CategoryType,
    GlobalAttributeKey,
    GlobalAttributeKeyTranslation,
    ProductAttributeValue,
)


def _build_request():
    query_dict = QueryDict("", mutable=True)
    return SimpleNamespace(query_params=query_dict, _request=SimpleNamespace(GET=query_dict.copy()))


@pytest.mark.django_db
def test_available_attributes_excludes_single_value_and_non_facet_dynamic_attributes():
    from apps.catalog.views import FacetedModelViewSetMixin

    # accessories может быть уже засеян миграциями
    category_type, _ = CategoryType.objects.get_or_create(slug="accessories", defaults={"name": "Accessories"})
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

    key_material, _ = GlobalAttributeKey.objects.get_or_create(slug="material")
    GlobalAttributeKeyTranslation.objects.get_or_create(key_obj=key_material, locale="ru", defaults={"name": "Материал"})
    key_case_material, _ = GlobalAttributeKey.objects.get_or_create(slug="case-material")
    GlobalAttributeKeyTranslation.objects.get_or_create(key_obj=key_case_material, locale="ru", defaults={"name": "Материал корпуса"})
    key_accessory_type, _ = GlobalAttributeKey.objects.get_or_create(slug="accessory-type")
    GlobalAttributeKeyTranslation.objects.get_or_create(key_obj=key_accessory_type, locale="ru", defaults={"name": "Тип аксессуара"})
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

    with translation.override("ru"):
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


@pytest.mark.django_db
def test_available_attributes_query_count_does_not_grow_with_products():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.catalog.views import FacetedModelViewSetMixin

    category_type, _ = CategoryType.objects.get_or_create(slug="accessories", defaults={"name": "Accessories"})
    category = Category.objects.create(
        name="Аксессуары",
        slug="test-accessories-facets-count",
        description="Аксессуары",
        category_type=category_type,
    )
    key_material, _ = GlobalAttributeKey.objects.get_or_create(slug="material")
    GlobalAttributeKeyTranslation.objects.get_or_create(key_obj=key_material, locale="ru", defaults={"name": "Материал"})
    content_type = ContentType.objects.get_for_model(AccessoryProduct)
    products = []
    for index in range(6):
        product = AccessoryProduct.objects.create(
            name=f"Аксессуар {index}",
            slug=f"test-accessory-count-{index}",
            description="Товар",
            category=category,
            price=100,
            currency="TRY",
            is_active=True,
        )
        ProductAttributeValue.objects.create(
            content_type=content_type,
            object_id=product.id,
            attribute_key=key_material,
            value="Кожа" if index % 2 else "Ткань",
            value_ru="Кожа" if index % 2 else "Ткань",
        )
        products.append(product)

    class _FacetView(FacetedModelViewSetMixin):
        pass

    view = _FacetView()
    view.request = _build_request()

    def run(items):
        with translation.override("ru"), CaptureQueriesContext(connection) as queries:
            available = view._calculate_available_attributes(
                AccessoryProduct.objects.filter(pk__in=[p.pk for p in items]).order_by("pk")
            )
        return available, len(queries.captured_queries)

    few, few_queries = run(products[:2])
    many, many_queries = run(products)

    expected = [{"key": "material", "name": "Материал", "values": ["Кожа", "Ткань"]}]
    assert few == expected
    assert many == expected
    assert many_queries == few_queries
