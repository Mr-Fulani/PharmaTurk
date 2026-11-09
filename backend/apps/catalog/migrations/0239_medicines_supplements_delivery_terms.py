"""
Сроки доставки в текстах разделов лекарств и БАДов, подборок и страниц препаратов (/drugs):
«авиа 3–7, наземная 7–14, морем 20–45 дней», как на /delivery (решение владельца 09.11.2026).

Прежние сроки: лекарства «7–21 рабочий день» (миграция 0222 и правки в админке), БАДы «7–14 дней»
(тексты разделов от 27.10.2026, «Доставка занимает 7–14 дней»). Меняются только эти формулировки
срока — дословно, остальной текст как был: «доставка 7–21 рабочий день» → «доставка 3–45 дней (авиа 3–7,
наземная 7–14, морем 20–45)»; в описании для поиска (до 200 знаков) — «доставка 3–45 дней».
Правила — копия ``apps/catalog/services/delivery_terms.py`` на 09.11.2026 (миграция не зависит от кода).
Баннер «Доставка из Турции» на главной: «7–21 рабочий день: авиа, авто или морем» → «авиа 3–7, наземная
7–14, морем 20–45 дней» (только дословно совпадающая строка).
Без сети и R2. Обратно не возвращает: прежние тексты медикаментов — в 0222.
"""
import re

from django.db import migrations

SEO_FIELDS = ('h1', 'meta_title', 'meta_description', 'seo_text')
SPAN = {
    'ru': '3–45 дней (авиа 3–7, наземная 7–14, морем 20–45)',
    'en': '3–45 days (air 3–7, ground 7–14, sea 20–45)',
}
SPAN_SHORT = {'ru': '3–45 дней', 'en': '3–45 days'}
MEDICINE_PATTERNS = (
    ('ru', re.compile(r'7[–-]21 рабоч(?:ий|их) д(?:ень|ня|ней)')),
    ('en', re.compile(r'7[–-]21 (?:business|working) days')),
)
SUPPLEMENT_PATTERNS = (
    ('ru', re.compile(r'7[–-]14 (?:дней|дня)(?:, от 5 \$)?')),
    ('en', re.compile(r'7[–-]14 days(?:, from \$5)?')),
)


BANNER_TEXTS = (
    ('7–21 рабочий день: авиа, авто или морем', 'авиа 3–7, наземная 7–14, морем 20–45 дней'),
    ('7–21 business days by air, road or sea', 'air 3–7, ground 7–14, sea 20–45 days'),
)
BANNER_MODELS = ('Banner', 'BannerTranslation', 'BannerMedia', 'BannerMediaTranslation')
BANNER_FIELDS = ('title', 'description', 'link_text')


def replace_terms(text, supplements=False, short=False):
    if not text:
        return text
    spans = SPAN_SHORT if short else SPAN
    for locale, pattern in MEDICINE_PATTERNS + (SUPPLEMENT_PATTERNS if supplements else ()):
        text = pattern.sub(spans[locale], text)
    return text


def _tree(Category, root_slug):
    ids = set(Category.objects.filter(slug=root_slug).values_list('id', flat=True))
    frontier = set(ids)
    while frontier:
        frontier = set(Category.objects.filter(parent_id__in=frontier).values_list('id', flat=True)) - ids
        ids |= frontier
    return ids


def _update(queryset, supplements):
    for row in queryset.iterator():
        changed = []
        for field in SEO_FIELDS:
            value = getattr(row, field) or ''
            new = replace_terms(value, supplements=supplements, short=field == 'meta_description')
            if new != value:
                setattr(row, field, new)
                changed.append(field)
        if changed:
            row.save(update_fields=changed)


def forwards(apps, schema_editor):
    Category = apps.get_model('catalog', 'Category')
    CategoryTranslation = apps.get_model('catalog', 'CategoryTranslation')
    CategoryCollectionTranslation = apps.get_model('catalog', 'CategoryCollectionTranslation')
    MedicineGroupTranslation = apps.get_model('catalog', 'MedicineGroupTranslation')

    for root, supplements in (('medicines', False), ('supplements', True)):
        ids = _tree(Category, root)
        if not ids:
            continue
        _update(CategoryTranslation.objects.filter(category_id__in=ids), supplements)
        _update(CategoryCollectionTranslation.objects.filter(collection__parent_id__in=ids), supplements)
    _update(MedicineGroupTranslation.objects.all(), False)

    for name in BANNER_MODELS:
        Model = apps.get_model('catalog', name)
        for old, new in BANNER_TEXTS:
            for field in BANNER_FIELDS:
                for row in Model.objects.filter(**{f'{field}__contains': old}):
                    setattr(row, field, getattr(row, field).replace(old, new))
                    row.save(update_fields=[field])


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0238_medicines_supplements_meta_description'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
