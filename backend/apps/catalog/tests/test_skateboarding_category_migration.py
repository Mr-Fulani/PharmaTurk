"""Миграция 0240: подраздел «Скейтбординг и ролики» в «Спорттоварах» (решение владельца 13.11.2026)."""

import importlib

import pytest
from django.apps import apps as django_apps

from apps.catalog.constants import SPORTS_SUBCATEGORIES
from apps.catalog.models import Category, CategoryTranslation, CategoryType

migration = importlib.import_module("apps.catalog.migrations.0240_skateboarding_roller_category")


@pytest.mark.django_db
def test_creates_section_under_sports_once():
    Category.objects.filter(slug=migration.SLUG).delete()
    migration.create_category(django_apps, None)
    assert not Category.objects.filter(slug=migration.SLUG).exists()  # нет «Спорттоваров» — ничего

    sports_type = CategoryType.objects.create(name="Спорттовары", slug="sports")
    sports = Category.objects.create(name="Спорттовары", slug="sports", category_type=sports_type)
    migration.create_category(django_apps, None)

    section = Category.objects.get(slug="skateboarding-roller")
    assert (section.name, section.parent, section.category_type, section.is_active) == (
        "Скейтбординг и ролики", sports, sports_type, True,
    )
    assert section.meta_title == "Скейтбординг и ролики | Спорттовары | Mudaroba"
    # Наценка не задана — наследуется от «Спорттоваров».
    assert section.margin_percent in (None, 0)
    names = dict(CategoryTranslation.objects.filter(category=section).values_list("locale", "name"))
    assert names == {"ru": "Скейтбординг и ролики", "en": "Skateboarding & Roller"}

    section.name = "Правка руками"
    section.save()
    migration.create_category(django_apps, None)  # существующий раздел не трогается
    assert Category.objects.get(slug="skateboarding-roller").name == "Правка руками"


def test_seed_has_the_same_section_and_order():
    slugs = [item[2] for item in SPORTS_SUBCATEGORIES]
    assert slugs.index(migration.SLUG) == migration.SORT_ORDER
