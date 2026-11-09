"""Миграция 0008: заголовок и описание /delivery для поиска — сроки вместо обещаний способов оплаты."""
import importlib

import pytest
from django.apps import apps as django_apps

from apps.pages.models import Page

migration = importlib.import_module('apps.pages.migrations.0008_delivery_meta_texts')
OLD = {field: old for field, (old, _new) in migration.FIELDS.items()}
NEW = {field: new for field, (_old, new) in migration.FIELDS.items()}


@pytest.mark.django_db
def test_old_meta_is_replaced_and_restored():
    Page.objects.filter(slug='delivery').delete()
    page = Page.objects.create(slug='delivery', **OLD)

    migration.forwards(django_apps, None)
    page.refresh_from_db()
    for field, value in NEW.items():
        assert getattr(page, field) == value
    assert 'криптовалют' not in page.meta_description_ru

    migration.backwards(django_apps, None)
    page.refresh_from_db()
    for field, value in OLD.items():
        assert getattr(page, field) == value


@pytest.mark.django_db
def test_meta_edited_in_admin_is_not_touched():
    Page.objects.filter(slug='delivery').delete()
    page = Page.objects.create(
        slug='delivery',
        meta_title_ru='Свой заголовок владельца',
        meta_description_ru='Своё описание владельца.',
        meta_title_en=OLD['meta_title_en'],
    )

    migration.forwards(django_apps, None)
    page.refresh_from_db()
    assert page.meta_title_ru == 'Свой заголовок владельца'
    assert page.meta_description_ru == 'Своё описание владельца.'
    assert page.meta_title_en == NEW['meta_title_en']


def test_new_meta_fits_length_rules():
    for field, value in NEW.items():
        limit = 80 if field.startswith('meta_title') else 200
        assert len(value) <= limit, field
