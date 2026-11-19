"""
Страница «О нас»: пункт «Безопасная оплата» обещал «банковские карты РФ, международные переводы и
криптовалюту». Оплаты на сайте нет — способ согласуется с менеджером, и относится это к товарам,
кроме лекарств (решение владельца 19.11.2026: лекарства — справочная информация).

Меняется только дословно совпадающий пункт: если его правили в админке, миграция его не трогает.
Без сети и R2.
"""
from django.db import migrations

ABOUT_PAYMENT = {
    'content_ru': (
        '<strong>Безопасная оплата.</strong> Мы предлагаем удобные и защищенные способы оплаты, включая '
        'банковские карты РФ, международные переводы и криптовалюту. Ваши средства и данные всегда в '
        'безопасности.',
        '<strong>Оплата по согласованию.</strong> Оплата на сайте не требуется: способ оплаты (в том числе '
        'перевод или криптовалюта) согласуется с менеджером после заявки. Это относится к товарам, кроме '
        'лекарств: сведения о лекарствах на сайте — справочные.',
    ),
    'content_en': (
        '<strong>Secure Payments.</strong> We offer convenient and protected payment methods, including bank '
        'cards, international transfers, and cryptocurrency. Your funds and data are always secure.',
        '<strong>Payment by arrangement.</strong> No payment is taken on the site: the payment method '
        '(including a transfer or cryptocurrency) is agreed with a manager after your request. This applies '
        'to goods other than medicines: medicine pages on the site are for reference only.',
    ),
}


def _replace(apps, forward):
    Page = apps.get_model('pages', 'Page')
    page = Page.objects.filter(slug='about-us').first()
    if page is None:
        return
    changed = []
    for field, (old, new) in ABOUT_PAYMENT.items():
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
        ('pages', '0009_delivery_remove_old_terms'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
