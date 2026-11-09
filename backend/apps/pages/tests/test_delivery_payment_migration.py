"""Миграция 0007: абзац «Оплата» на /delivery без обещания онлайн-оплаты картами."""
import importlib

import pytest
from django.apps import apps as django_apps

from apps.pages.models import Page

migration = importlib.import_module('apps.pages.migrations.0007_delivery_payment_text')
OLD_RU, NEW_RU = migration.PAYMENT_PARAGRAPHS['content_ru']
OLD_EN, NEW_EN = migration.PAYMENT_PARAGRAPHS['content_en']


@pytest.mark.django_db
def test_old_payment_paragraph_is_replaced_and_restored():
    Page.objects.filter(slug='delivery').delete()
    page = Page.objects.create(
        slug='delivery',
        content_ru=f'<div><h2>Оплата</h2>{OLD_RU}<h3>Стоимость доставки</h3></div>',
        content_en=f'<div><h2>Payment</h2>{OLD_EN}</div>',
    )

    migration.forwards(django_apps, None)
    page.refresh_from_db()
    assert NEW_RU in page.content_ru and OLD_RU not in page.content_ru
    assert '<h3>Стоимость доставки</h3>' in page.content_ru
    assert NEW_EN in page.content_en and OLD_EN not in page.content_en

    migration.backwards(django_apps, None)
    page.refresh_from_db()
    assert OLD_RU in page.content_ru and OLD_EN in page.content_en


@pytest.mark.django_db
def test_text_edited_in_admin_is_not_touched():
    Page.objects.filter(slug='delivery').delete()
    edited = '<div><h2>Оплата</h2><p>Свой текст владельца.</p></div>'
    page = Page.objects.create(slug='delivery', content_ru=edited, content_en='')

    migration.forwards(django_apps, None)
    page.refresh_from_db()
    assert page.content_ru == edited
