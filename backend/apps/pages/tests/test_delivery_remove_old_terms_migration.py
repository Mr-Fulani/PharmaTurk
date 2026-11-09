"""Миграция 0009: из абзаца «Доставка» на /delivery убрано предложение «3–7 … по стране и 7–21 …»."""
import importlib

import pytest
from django.apps import apps as django_apps

from apps.pages.models import Page

migration = importlib.import_module('apps.pages.migrations.0009_delivery_remove_old_terms')
OLD_RU, NEW_RU = migration.DELIVERY_PARAGRAPHS['content_ru']
OLD_EN, NEW_EN = migration.DELIVERY_PARAGRAPHS['content_en']


@pytest.mark.django_db
def test_old_terms_sentence_is_removed_and_restored():
    Page.objects.filter(slug='delivery').delete()
    page = Page.objects.create(
        slug='delivery',
        content_ru=f'<div><h2>Доставка</h2>{OLD_RU}<h2>Оплата</h2></div>',
        content_en=f'<div><h2>Delivery</h2>{OLD_EN}</div>',
    )

    migration.forwards(django_apps, None)
    page.refresh_from_db()
    assert NEW_RU in page.content_ru and '7–21' not in page.content_ru
    assert '<h2>Оплата</h2>' in page.content_ru
    assert NEW_EN in page.content_en and '7–21' not in page.content_en

    migration.backwards(django_apps, None)
    page.refresh_from_db()
    assert OLD_RU in page.content_ru and OLD_EN in page.content_en


@pytest.mark.django_db
def test_paragraph_edited_in_admin_is_not_touched():
    Page.objects.filter(slug='delivery').delete()
    edited = '<div><h2>Доставка</h2><p>Свой текст владельца, 7–21 день.</p></div>'
    page = Page.objects.create(slug='delivery', content_ru=edited, content_en='')

    migration.forwards(django_apps, None)
    page.refresh_from_db()
    assert page.content_ru == edited
