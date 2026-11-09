"""
Страница «Доставка и оплата»: из абзаца «Доставка» убрано предложение со сроками «3–7 рабочих дней
по стране и 7–21 рабочий день для международных отправлений» (решение владельца 09.11.2026: сроки —
в блоке «Способы доставки»: авиа 3–7, наземная 7–14, морем 20–45 дней). Остальная страница прежняя.

Меняется только дословно совпадающий абзац (из load_initial_pages): если его правили в админке,
миграция его не трогает. Без сети и R2.
"""
from django.db import migrations

DELIVERY_PARAGRAPHS = {
    'content_ru': (
        '<p>Мы доставляем заказы с помощью надёжных курьерских служб. Сроки доставки зависят от региона и '
        'выбранного способа доставки. Обычно это 3–7 рабочих дней по стране и 7–21 рабочий день для '
        'международных отправлений.</p>',
        '<p>Мы доставляем заказы с помощью надёжных курьерских служб. Сроки доставки зависят от региона и '
        'выбранного способа доставки.</p>',
    ),
    'content_en': (
        '<p>We deliver orders to customers using trusted courier services. Delivery times depend on the '
        'destination and selected shipping method. Typical delivery times are 3–7 business days within the '
        'country and 7–21 business days for international orders.</p>',
        '<p>We deliver orders to customers using trusted courier services. Delivery times depend on the '
        'destination and selected shipping method.</p>',
    ),
}


def _replace(apps, forward):
    Page = apps.get_model('pages', 'Page')
    page = Page.objects.filter(slug='delivery').first()
    if page is None:
        return
    changed = []
    for field, (old, new) in DELIVERY_PARAGRAPHS.items():
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
        ('pages', '0008_delivery_meta_texts'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
