import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from apps.catalog.admin_perfumery import (
    PerfumeryCategoryFilter,
    PerfumeryProductAdmin,
    PerfumeryVariantAdmin,
)
from apps.catalog.models import (
    Category,
    CategoryType,
    PerfumeryProduct,
    PerfumeryVariant,
)


def _filter_request(value=None):
    params = {} if value is None else {"perfumery_category": str(value)}
    return RequestFactory().get("/admin/catalog/", params)


@pytest.mark.django_db
def test_perfumery_category_filter_only_lists_its_hierarchy():
    perfumery_type = CategoryType.objects.create(name="Парфюмерия", slug="perfumery")
    other_type, _ = CategoryType.objects.get_or_create(
        slug="tableware", defaults={"name": "Посуда тест"}
    )
    root = Category.objects.create(
        name="Парфюмерия", slug="admin-perfumery-root", category_type=perfumery_type
    )
    child = Category.objects.create(
        name="Мужская", slug="admin-perfumery-men", category_type=perfumery_type, parent=root
    )
    Category.objects.create(
        name="Чайники", slug="admin-tableware-kettles", category_type=other_type
    )
    model_admin = PerfumeryProductAdmin(PerfumeryProduct, AdminSite())

    category_filter = PerfumeryCategoryFilter(
        _filter_request(), {}, PerfumeryProduct, model_admin
    )

    assert list(category_filter.lookup_choices) == [
        (str(root.pk), "Парфюмерия"),
        (str(child.pk), "Парфюмерия › Мужская"),
    ]


@pytest.mark.django_db
def test_perfumery_category_filter_filters_products_and_variants():
    perfumery_type = CategoryType.objects.create(name="Парфюмерия", slug="perfumery")
    first_category = Category.objects.create(
        name="Мужская", slug="admin-perfumery-filter-men", category_type=perfumery_type
    )
    second_category = Category.objects.create(
        name="Женская", slug="admin-perfumery-filter-women", category_type=perfumery_type
    )
    first_product = PerfumeryProduct.objects.create(
        name="Первый аромат",
        slug="admin-first-perfume",
        category=first_category,
        gender="men",
    )
    second_product = PerfumeryProduct.objects.create(
        name="Второй аромат",
        slug="admin-second-perfume",
        category=second_category,
        gender="women",
    )
    first_variant = PerfumeryVariant.objects.create(product=first_product, name="50 мл")
    PerfumeryVariant.objects.create(product=second_product, name="100 мл")

    product_admin = PerfumeryProductAdmin(PerfumeryProduct, AdminSite())
    product_filter = PerfumeryCategoryFilter(
        _filter_request(first_category.pk),
        {"perfumery_category": [str(first_category.pk)]},
        PerfumeryProduct,
        product_admin,
    )
    assert list(product_filter.queryset(_filter_request(), PerfumeryProduct.objects.all())) == [
        first_product
    ]

    variant_admin = PerfumeryVariantAdmin(PerfumeryVariant, AdminSite())
    variant_filter = PerfumeryCategoryFilter(
        _filter_request(first_category.pk),
        {"perfumery_category": [str(first_category.pk)]},
        PerfumeryVariant,
        variant_admin,
    )
    assert list(variant_filter.queryset(_filter_request(), PerfumeryVariant.objects.all())) == [
        first_variant
    ]
