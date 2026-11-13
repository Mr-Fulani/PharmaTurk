"""Миграция 0242: подраздел «Термосы и термокружки» в «Посуде» (решение владельца 13.11.2026)."""

import importlib

import pytest
from django.apps import apps as django_apps

from apps.catalog.constants import TABLEWARE_SUBCATEGORIES
from apps.catalog.models import Category, CategoryTranslation, CategoryType
from apps.scrapers.parsers.spx import SPX_SUBGROUP_ROUTES
from apps.scrapers.parsers.superstep import SUPERSTEP_SUBGROUP_CATEGORIES

migration = importlib.import_module("apps.catalog.migrations.0242_thermoses_category")


@pytest.mark.django_db
def test_creates_section_under_drinkware_once():
    Category.objects.filter(slug=migration.SLUG).delete()
    migration.create_category(django_apps, None)
    assert not Category.objects.filter(slug=migration.SLUG).exists()  # нет «Стаканов и бокалов» — ничего

    tableware_type = CategoryType.objects.create(name="Посуда", slug="tableware")
    root = Category.objects.create(name="Посуда", slug="tableware", category_type=tableware_type)
    drinkware = Category.objects.create(name="Стаканы и бокалы", slug="drinkware", parent=root, category_type=tableware_type)
    migration.create_category(django_apps, None)

    section = Category.objects.get(slug="thermoses")
    assert (section.name, section.parent, section.category_type, section.is_active) == (
        "Термосы и термокружки", drinkware, tableware_type, True,
    )
    assert section.meta_title == "Термосы и термокружки | Стаканы и бокалы | Mudaroba"
    assert section.meta_keywords == "Термосы и термокружки, Стаканы и бокалы, Посуда, thermoses"
    # Наценка не задана — наследуется.
    assert section.margin_percent in (None, 0)
    names = dict(CategoryTranslation.objects.filter(category=section).values_list("locale", "name"))
    assert names == {"ru": "Термосы и термокружки", "en": "Thermoses & Travel Mugs"}

    section.name = "Правка руками"
    section.save()
    migration.create_category(django_apps, None)  # существующий раздел не трогается
    assert Category.objects.get(slug="thermoses").name == "Правка руками"


def test_seed_and_parsers_use_the_same_section():
    drinkware = next(item for item in TABLEWARE_SUBCATEGORIES if item[2] == migration.PARENT_SLUG)
    slugs = [child[2] for child in drinkware[5]]
    assert slugs.index(migration.SLUG) == migration.SORT_ORDER
    assert SUPERSTEP_SUBGROUP_CATEGORIES["termos"][0] == SPX_SUBGROUP_ROUTES["termos"][0] == migration.SLUG
