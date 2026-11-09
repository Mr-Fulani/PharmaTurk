"""
Страница «Доставка и оплата»: абзац «Оплата» обещал онлайн-оплату картами, а на сайте её нет —
заказ это заявка менеджеру, способ оплаты согласуется с ним (решение владельца 09.11.2026).

Меняется только дословно совпадающий старый абзац (из load_initial_pages): если текст уже правили
в админке, миграция его не трогает. Без сети и R2.
"""
from django.db import migrations

PAYMENT_PARAGRAPHS = {
    'content_ru': (
        '<p>Мы принимаем онлайн-платежи банковскими картами и через популярных платёжных провайдеров. '
        'Доступные способы оплаты зависят от вашей страны и указываются на странице оформления заказа.</p>',
        '<p>Оплата на сайте не требуется: заказ — это заявка менеджеру. Менеджер подтвердит наличие и '
        'итоговую сумму с доставкой, способ оплаты согласуется с ним. Платить нужно только после '
        'подтверждения заказа.</p>',
    ),
    'content_en': (
        '<p>We accept online payments via major credit cards and payment providers. For specific payment '
        'options available in your region, please check the checkout page.</p>',
        '<p>No payment is made on the site: an order is a request to a manager. The manager confirms '
        'availability and the total with delivery, and the payment method is agreed with the manager. '
        'You pay only after the order is confirmed.</p>',
    ),
}


def _replace(apps, forward):
    Page = apps.get_model('pages', 'Page')
    page = Page.objects.filter(slug='delivery').first()
    if page is None:
        return
    changed = []
    for field, (old, new) in PAYMENT_PARAGRAPHS.items():
        source, target = (old, new) if forward else (new, old)
        value = getattr(page, field) or ''
        if source in value:
            setattr(page, field, value.replace(source, target))
            changed.append(field)
    if changed:
        page.save(update_fields=changed)


def forwards(apps, schema_editor):
    _replace(apps, forward=True)


def backwards(apps, schema_editor):
    _replace(apps, forward=False)


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0006_populate_seo_fields'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
