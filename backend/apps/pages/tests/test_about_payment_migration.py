"""Миграция 0010: пункт об оплате на «О нас» — без обещания карт РФ, оплата относится к товарам, кроме лекарств."""
import importlib

import pytest
from django.apps import apps as django_apps

from apps.pages.models import Page

migration = importlib.import_module('apps.pages.migrations.0010_about_payment_text')
OLD_RU, NEW_RU = migration.ABOUT_PAYMENT['content_ru']
OLD_EN, NEW_EN = migration.ABOUT_PAYMENT['content_en']


@pytest.mark.django_db
def test_payment_item_is_replaced_and_restored():
    Page.objects.filter(slug='about-us').delete()
    page = Page.objects.create(
        slug='about-us',
        content_ru=f'<ul><li>{OLD_RU}</li></ul><h3>Что мы помогаем привезти?</h3>',
        content_en=f'<ul><li>{OLD_EN}</li></ul>',
    )

    migration.forwards(django_apps, None)
    page.refresh_from_db()
    assert NEW_RU in page.content_ru and 'карты РФ' not in page.content_ru
    assert 'кроме лекарств' in page.content_ru
    assert '<h3>Что мы помогаем привезти?</h3>' in page.content_ru
    assert NEW_EN in page.content_en and 'bank cards' not in page.content_en

    migration.backwards(django_apps, None)
    page.refresh_from_db()
    assert OLD_RU in page.content_ru and OLD_EN in page.content_en


@pytest.mark.django_db
def test_item_edited_in_admin_is_not_touched():
    Page.objects.filter(slug='about-us').delete()
    edited = '<ul><li><strong>Оплата.</strong> Свой текст владельца.</li></ul>'
    page = Page.objects.create(slug='about-us', content_ru=edited, content_en='')

    migration.forwards(django_apps, None)
    page.refresh_from_db()
    assert page.content_ru == edited and page.content_en == ''
