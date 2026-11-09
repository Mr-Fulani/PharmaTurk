"""Миграция 0238: описания разделов «Медикаменты» и «БАДы» для поиска — конкретные факты."""
import importlib

import pytest
from django.apps import apps as django_apps

from apps.catalog.models import Category, CategoryTranslation

migration = importlib.import_module('apps.catalog.migrations.0238_medicines_supplements_meta_description')


def _translation(slug, locale, meta_description):
    category = Category.objects.update_or_create(slug=slug, defaults={'name': slug})[0]
    translation, _ = CategoryTranslation.objects.update_or_create(
        category=category, locale=locale,
        defaults={'name': f'{slug}-{locale}', 'meta_description': meta_description},
    )
    return translation


@pytest.mark.django_db
def test_old_descriptions_are_replaced_and_restored():
    rows = {key: _translation(*key, old) for key, (old, _new) in migration.META_DESCRIPTIONS.items()}

    migration.forwards(django_apps, None)
    for key, (_old, new) in migration.META_DESCRIPTIONS.items():
        rows[key].refresh_from_db()
        assert rows[key].meta_description == new

    migration.backwards(django_apps, None)
    for key, (old, _new) in migration.META_DESCRIPTIONS.items():
        rows[key].refresh_from_db()
        assert rows[key].meta_description == old


@pytest.mark.django_db
def test_description_edited_in_admin_is_not_touched():
    edited = _translation('supplements', 'ru', 'Своё описание владельца.')

    migration.forwards(django_apps, None)
    edited.refresh_from_db()
    assert edited.meta_description == 'Своё описание владельца.'


def test_new_descriptions_fit_length_rule():
    for _old, new in migration.META_DESCRIPTIONS.values():
        assert 100 <= len(new) <= 200
