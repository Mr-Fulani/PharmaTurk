"""
Описания для поиска у разделов «Медикаменты» и «БАДы»: конкретные факты вместо общих слов
(задача владельца 09.11.2026 — у ИИ-поиска и конкурентов больше конкретики); сроки — «авиа 3–7,
наземная 7–14, морем 20–45 дней», как на /delivery (решение владельца 09.11.2026).

Меняется только дословно совпадающее прежнее описание (0222 у медикаментов, тексты раздела
БАДов от 27.10.2026): если его уже правили в админке, миграция поле не трогает. Без сети и R2.
"""
from django.db import migrations

# (slug раздела, язык): (прежнее описание, новое описание)
META_DESCRIPTIONS = {
    ('medicines', 'ru'): (
        'Оригинальные препараты из турецких аптек: около 13 тысяч позиций с действующим веществом и '
        'инструкцией. Заявка, проверка наличия и расчёт менеджером, доставка 7–21 рабочий день.',
        'Оригинальные препараты из турецких аптек: около 12 тысяч позиций с действующим веществом и '
        'инструкцией. Заявка без регистрации, доставка: авиа 3–7, наземная 7–14, морем 20–45 дней.',
    ),
    ('medicines', 'en'): (
        'Original medicines from Turkish pharmacies: about 13,000 items with active ingredient and leaflet. '
        'Send a request — we check availability and quote delivery in 7–21 business days.',
        'Original medicines from Turkish pharmacies: about 12,000 items with active ingredient and leaflet. '
        'No sign-up request; delivery: air 3–7, ground 7–14, sea 20–45 days.',
    ),
    ('supplements', 'ru'): (
        'БАДы из Турции: витамины, минералы, пробиотики, коллаген, омега, травяные добавки. Solgar, Vefa, '
        'Farmatek. Отправьте заявку — менеджер рассчитает стоимость с доставкой.',
        'БАДы из Турции: витамины, минералы, пробиотики, коллаген, омега — Solgar, Vefa, Farmatek, больше '
        '7 000 позиций. Заявка без регистрации, доставка: авиа 3–7, наземная 7–14, морем 20–45 дней.',
    ),
    ('supplements', 'en'): (
        'Supplements from Turkey: vitamins, minerals, probiotics, collagen, omega, herbal products. Brands '
        'include Solgar, Vefa, Farmatek. Send a request and a manager will quote the total cost.',
        'Supplements from Turkey: vitamins, minerals, probiotics, collagen, omega — Solgar, Vefa, Farmatek, '
        'over 7,000 items. No sign-up request; delivery: air 3–7, ground 7–14, sea 20–45 days.',
    ),
}


def _replace(apps, forward):
    CategoryTranslation = apps.get_model('catalog', 'CategoryTranslation')
    for (slug, locale), (old, new) in META_DESCRIPTIONS.items():
        source, target = (old, new) if forward else (new, old)
        CategoryTranslation.objects.filter(
            category__slug=slug, locale=locale, meta_description=source,
        ).update(meta_description=target)


def forwards(apps, schema_editor):
    _replace(apps, forward=True)


def backwards(apps, schema_editor):
    _replace(apps, forward=False)


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0237_product_search_index'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
