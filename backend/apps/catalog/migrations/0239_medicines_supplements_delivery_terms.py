"""
Сроки доставки в текстах разделов лекарств и БАДов, подборок и страниц препаратов (/drugs):
«авиа 3–7, наземная 7–14, морем 20–45 дней», как на /delivery (решение владельца 09.11.2026).

Прежние сроки: лекарства «7–21 рабочий день» (миграция 0222 и правки в админке), БАДы «7–14 дней»
(тексты разделов от 27.10.2026, «Доставка занимает 7–14 дней»). Меняются только эти формулировки
срока — дословно, остальной текст как был: «доставка 7–21 рабочий день» → «доставка: авиа 3–7, наземная
7–14, морем 20–45 дней»; в описании для поиска (до 200 знаков) — «доставка 3–14 дней».
Правила — копия ``apps/catalog/services/delivery_terms.py`` на 09.11.2026 (миграция не зависит от кода).
Баннер «Доставка из Турции» на главной: «7–21 рабочий день: авиа, авто или морем» → «авиа 3–7, наземная
7–14, морем 20–45 дней» (только дословно совпадающая строка).
Без сети и R2. Обратно не возвращает: прежние тексты медикаментов — в 0222.
"""
import re

from django.db import migrations

SEO_FIELDS = ('h1', 'meta_title', 'meta_description', 'seo_text')
TERMS = {
    "ru": "авиа 3–7, наземная 7–14, морем 20–45 дней",
    "en": "air 3–7, ground 7–14, sea 20–45 days",
}
SHORT = {"ru": "3–14 дней", "en": "3–14 days"}
# Прежний срок: лекарства — всегда, БАДы — ещё и «7–14 дней» (только срок доставки; «от 5 $» у БАДов не пишем)
_MEDICINE_RANGE = {"ru": r"7[–-]21 рабоч(?:ий|их) д(?:ень|ня|ней)", "en": r"7[–-]21 (?:business|working) days"}
_SUPPLEMENT_RANGE = {"ru": r"7[–-]14 (?:дней|дня)(?:, от 5 \$)?", "en": r"7[–-]14 days(?:, from \$5)?"}
# Полная форма без диапазона впереди: «доставка 7–21 рабочий день» → «доставка: авиа 3–7, …»,
# «посылка идёт 7–21 рабочий день» → «посылка: авиа 3–7, …»; после тире — просто фраза.
_VERBS = {
    "ru": r"занимает|займёт|длится|идёт|идут|приходит|доставляются|находится|будет в пути",
    "en": r"takes|take|arrive|arrives|is in transit for|is",
}
_PREPOSITIONS = {"ru": r"за|в течение", "en": r"in|within"}


def _full(locale, range_re):
    terms = TERMS[locale]
    return [
        # «Parcels take 7–21 business days to arrive», «the parcel spends 7–21 working days in transit»
        (re.compile(rf"\s+takes?\s+{range_re}\s+to arrive"), f": {terms}"),
        (re.compile(rf"\bspends\s+{range_re}\s+in transit"), f"is in transit: {terms}"),
        # «Срок доставки — 7–21 рабочий день», «Allow 7–21 working days» — подставить фразу как есть
        (re.compile(rf"(—\s*|\b(?:Allow|allow|закладывайте|Ожидание посылки —)\s*){range_re}"), rf"\g<1>{terms}"),
        (
            re.compile(rf"(?:\s+(?:{_VERBS[locale]}))?(?:\s+(?:{_PREPOSITIONS[locale]}))?\s+{range_re}"),
            f": {terms}",
        ),
    ]


def replace_terms(text, supplements=False, short=False):
    """Прежние сроки доставки → новые. ``supplements`` — текст БАДа: ещё и «7–14 дней»;
    ``short`` — описание для поиска: «3–14 дней», чтобы не выйти за 200 знаков."""
    if not text:
        return text
    for locale in ("ru", "en"):
        ranges = [_MEDICINE_RANGE[locale]] + ([_SUPPLEMENT_RANGE[locale]] if supplements else [])
        for range_re in ranges:
            if short:
                text = re.sub(range_re, SHORT[locale], text)
                continue
            for pattern, replacement in _full(locale, range_re):
                text = pattern.sub(replacement, text)
    return text


BANNER_TEXTS = (
    ('7–21 рабочий день: авиа, авто или морем', 'авиа 3–7, наземная 7–14, морем 20–45 дней'),
    ('7–21 business days by air, road or sea', 'air 3–7, ground 7–14, sea 20–45 days'),
)
BANNER_MODELS = ('Banner', 'BannerTranslation', 'BannerMedia', 'BannerMediaTranslation')
BANNER_FIELDS = ('title', 'description', 'link_text')


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
