from django.db import migrations, models


def fill_category_types(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")

    def detect(slug: str) -> str:
        s = slug or ""
        if "supplement" in s:
            return "supplements"
        if "medical-equipment" in s or "medical_equipment" in s or "equipment" in s:
            return "medical_equipment"
        if "tableware" in s:
            return "tableware"
        if "furniture" in s:
            return "furniture"
        if "jewelry" in s or "ring" in s or "necklace" in s:
            return "jewelry"
        if "accessor" in s:
            return "accessories"
        return "medicines"

    for cat in Category.objects.all():
        cat.category_type = detect(cat.slug)
        cat.save(update_fields=["category_type"])


def migrate_product_types(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    allowed = {
        "medicines",
        "supplements",
        "medical_equipment",
        "clothing",
        "shoes",
        "electronics",
        "furniture",
        "tableware",
        "accessories",
        "jewelry",
    }
    replacements = {
        "medical_accessories": "accessories",
        "medical-equipment": "medical_equipment",
        "medical_equipment": "medical_equipment",
        "tableware": "tableware",
        "furniture": "furniture",
        "accessory": "accessories",
    }
    for product in Product.objects.all():
        pt = product.product_type or "medicines"
        pt = replacements.get(pt, pt)
        if pt not in allowed:
            pt = "medicines"
        if product.product_type != pt:
            product.product_type = pt
            product.save(update_fields=["product_type"])


def noop_reverse(apps, schema_editor):
    # No reverse migration
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0022_rename_accessories_to_medical_accessories"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="category_type",
            field=models.CharField(
                choices=[
                    ("medicines", "Медицина"),
                    ("supplements", "БАДы"),
                    ("medical_equipment", "Медтехника"),
                    ("clothing", "Одежда"),
                    ("shoes", "Обувь"),
                    ("electronics", "Электроника"),
                    ("furniture", "Мебель"),
                    ("tableware", "Посуда"),
                    ("accessories", "Аксессуары"),
                    ("jewelry", "Украшения"),
                ],
                db_index=True,
                default="medicines",
                help_text="Определяет домен: медицина, БАДы, медтехника, посуда, мебель, аксессуары, украшения и т.д.",
                max_length=32,
                verbose_name="Тип категории",
            ),
        ),
        migrations.AlterField(
            model_name="product",
            name="product_type",
            field=models.CharField(
                choices=[
                    ("medicines", "Медицина"),
                    ("supplements", "БАДы"),
                    ("medical_equipment", "Медтехника"),
                    ("clothing", "Одежда"),
                    ("shoes", "Обувь"),
                    ("electronics", "Электроника"),
                    ("furniture", "Мебель"),
                    ("tableware", "Посуда"),
                    ("accessories", "Аксессуары"),
                    ("jewelry", "Украшения"),
                ],
                db_index=True,
                default="medicines",
                max_length=32,
                verbose_name="Тип товара",
            ),
        ),
        migrations.RunPython(fill_category_types, noop_reverse),
        migrations.RunPython(migrate_product_types, noop_reverse),
    ]

