"""«Антибиотики» — только J01: LEVOTIRON 75 MCG (левотироксин, H03AA01) стоял в них с мая 2026.

24.10.2026 из 856 медикаментов «Антибиотиков» код АТХ не J01 был у одного товара
(SEO-план медикаментов, пункт 5). Переносим такие товары в категорию по коду АТХ
(``propose_medicine_category``), если код однозначен; иначе не трогаем. Категория
меняется и у теневого Product: в миграции save() доменной модели не синхронизирует.
"""

from django.db import migrations

from apps.catalog.medicine_taxonomy import propose_medicine_category


def move_non_antibiotics(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    MedicineProduct = apps.get_model("catalog", "MedicineProduct")
    Product = apps.get_model("catalog", "Product")
    antibiotics = Category.objects.filter(slug="antibiotics").first()
    if antibiotics is None:
        return
    rows = (
        MedicineProduct.objects.filter(category=antibiotics)
        .exclude(atc_code__istartswith="J01")
        .values_list("id", "atc_code", "base_product_id")
    )
    for pk, atc_code, base_product_id in rows:
        proposal = propose_medicine_category(atc_code=atc_code)
        if proposal.status != "proposed" or proposal.category_slug == "antibiotics":
            continue
        target = Category.objects.filter(slug=proposal.category_slug, is_active=True).first()
        if target is None:
            continue
        MedicineProduct.objects.filter(pk=pk).update(category=target)
        if base_product_id:
            Product.objects.filter(pk=base_product_id, category=antibiotics).update(category=target)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0225_medicine_group_texts"),
    ]

    operations = [
        migrations.RunPython(move_non_antibiotics, migrations.RunPython.noop),
    ]
