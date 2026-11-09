"""
Страница «Доставка и оплата»: заголовок и описание для поиска. Прежнее описание обещало
«банковский перевод, криптовалюту» — способ оплаты согласуется с менеджером, а сроки
не назывались (задача владельца 09.11.2026: конкретные факты для поиска и ИИ-ассистентов).

Меняется только дословно совпадающее прежнее значение (из 0006): если поле уже правили в
админке, миграция его не трогает. Без сети и R2.
"""
from django.db import migrations

FIELDS = {
    'meta_title_ru': (
        'Доставка и оплата — Mudaroba',
        'Доставка из Турции в Россию и СНГ: сроки и оплата — Mudaroba',
    ),
    'meta_title_en': (
        'Delivery & Payment — Mudaroba',
        'Delivery from Turkey to Russia and the CIS: Times and Payment — Mudaroba',
    ),
    'meta_description_ru': (
        'Условия доставки и оплаты заказов из Турции. Международная доставка по России и СНГ. '
        'Банковский перевод, криптовалюта и другие способы оплаты.',
        'Доставка из Турции в Россию, СНГ и по миру: товары и БАДы — 7–14 дней, от 5 $, лекарства — '
        '7–21 рабочий день, по Стамбулу — в течение дня. Оплата на сайте не нужна: способ согласуется '
        'с менеджером.',
    ),
    'meta_description_en': (
        'Delivery and payment terms for orders from Turkey. International delivery to Russia and CIS. '
        'Bank transfer, cryptocurrency and other payment methods.',
        'Delivery from Turkey to Russia, the CIS and worldwide: goods and supplements 7–14 days, from $5; '
        'medicines 7–21 business days; Istanbul same day. No payment on the site — agreed with a manager.',
    ),
}


def _replace(apps, forward):
    Page = apps.get_model('pages', 'Page')
    page = Page.objects.filter(slug='delivery').first()
    if page is None:
        return
    changed = []
    for field, (old, new) in FIELDS.items():
        source, target = (old, new) if forward else (new, old)
        if getattr(page, field) == source:
            setattr(page, field, target)
            changed.append(field)
    if changed:
        page.save(update_fields=changed)


def forwards(apps, schema_editor):
    _replace(apps, forward=True)


def backwards(apps, schema_editor):
    _replace(apps, forward=False)


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0007_delivery_payment_text'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
