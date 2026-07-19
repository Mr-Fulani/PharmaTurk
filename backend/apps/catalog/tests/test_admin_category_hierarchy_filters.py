import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from apps.catalog.admin import (
    AllCategoriesAdmin,
    CategoryPerfumeryAdmin,
    CategoryRootFilter,
    ScopedParentCategoryFilter,
)
from apps.catalog.models import Category, CategoryPerfumery, CategoryType


pytestmark = pytest.mark.django_db


def _request(**params):
    return RequestFactory().get("/admin/catalog/category/", params)


def _make_trees():
    perfume_type = CategoryType.objects.create(name="Парфюмерия", slug="perfumery")
    furniture_type = CategoryType.objects.create(
        name="Мебель для теста фильтра", slug="filter-furniture-type"
    )
    perfume = Category.objects.create(
        name="Парфюмерия", slug="filter-perfumery", category_type=perfume_type
    )
    fragrances = Category.objects.create(
        name="Духи", slug="filter-fragrances", parent=perfume, category_type=perfume_type
    )
    Category.objects.create(
        name="Женские", slug="filter-women-fragrances", parent=fragrances,
        category_type=perfume_type,
    )
    furniture = Category.objects.create(
        name="Мебель", slug="filter-furniture", category_type=furniture_type
    )
    bedroom = Category.objects.create(
        name="Спальня", slug="filter-bedroom", parent=furniture,
        category_type=furniture_type,
    )
    Category.objects.create(
        name="Кровати", slug="filter-beds", parent=bedroom, category_type=furniture_type
    )
    return perfume, fragrances, furniture, bedroom


def test_general_parent_filter_is_hidden_until_tree_is_selected():
    _make_trees()
    model_admin = AllCategoriesAdmin(Category, AdminSite())

    category_filter = ScopedParentCategoryFilter(
        _request(), {}, Category, model_admin
    )

    assert list(category_filter.lookup_choices) == []


def test_general_parent_filter_lists_only_selected_tree_as_breadcrumbs():
    perfume, fragrances, _furniture, _bedroom = _make_trees()
    model_admin = AllCategoriesAdmin(Category, AdminSite())
    request = _request(root_id=perfume.pk)

    category_filter = ScopedParentCategoryFilter(
        request, {}, Category, model_admin
    )

    assert list(category_filter.lookup_choices) == [
        (str(perfume.pk), "Парфюмерия"),
        (str(fragrances.pk), "Парфюмерия › Духи"),
    ]


def test_proxy_category_filters_are_scoped_to_their_type():
    perfume, fragrances, _furniture, _bedroom = _make_trees()
    model_admin = CategoryPerfumeryAdmin(CategoryPerfumery, AdminSite())

    root_filter = CategoryRootFilter(_request(), {}, CategoryPerfumery, model_admin)
    parent_filter = ScopedParentCategoryFilter(
        _request(), {}, CategoryPerfumery, model_admin
    )

    assert list(root_filter.lookup_choices) == [(str(perfume.pk), "Парфюмерия")]
    assert list(parent_filter.lookup_choices) == [
        (str(perfume.pk), "Парфюмерия"),
        (str(fragrances.pk), "Парфюмерия › Духи"),
    ]
