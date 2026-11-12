"""Бренд «Mc Kinley» → «McKinley» (решение владельца 12.11.2026 по пилоту Intersport).

Магазины SuperStep и Intersport подписывают бренд «Mc Kinley», производитель пишет
«McKinley». Парсер теперь отдаёт «McKinley» (``AkinonParser.BRAND_ALIASES``); без
переименования существующей записи он завёл бы второй бренд. Без сети: только строки
бренда и его переводов. Адрес бренда (slug) не меняется. Если бренд «McKinley» уже есть,
ничего не делаем — такие записи сводят вручную.
"""

from django.db import migrations

OLD, NEW = "Mc Kinley", "McKinley"


def rename(apps, schema_editor, old=OLD, new=NEW):
    Brand = apps.get_model("catalog", "Brand")
    BrandTranslation = apps.get_model("catalog", "BrandTranslation")
    if Brand.objects.filter(name__iexact=new).exists():
        return
    ids = list(Brand.objects.filter(name__iexact=old).values_list("pk", flat=True))
    Brand.objects.filter(pk__in=ids).update(name=new)
    BrandTranslation.objects.filter(brand_id__in=ids, name__iexact=old).update(name=new)


def rename_back(apps, schema_editor):
    rename(apps, schema_editor, old=NEW, new=OLD)


class Migration(migrations.Migration):

    dependencies = [
        ("scrapers", "0035_intersport_scraper_config"),
        ("catalog", "0237_product_search_index"),
    ]

    operations = [
        migrations.RunPython(rename, rename_back),
    ]
