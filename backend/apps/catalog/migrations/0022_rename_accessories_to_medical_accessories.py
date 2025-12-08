from django.db import migrations, models


def migrate_accessories_to_medical_accessories(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    Product.objects.filter(product_type="accessories").update(product_type="medical_accessories")


def reverse_migrate_accessories(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    Product.objects.filter(product_type="medical_accessories").update(product_type="accessories")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0021_cleanup_base_categories"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="product_type",
            field=models.CharField(
                choices=[
                    ("medicines", "Медикаменты"),
                    ("supplements", "БАДы"),
                    ("medical_equipment", "Медтехника"),
                    ("medical_accessories", "Медицинские аксессуары"),
                    ("clothing", "Одежда"),
                    ("shoes", "Обувь"),
                    ("electronics", "Техника"),
                ],
                db_index=True,
                default="medicines",
                max_length=32,
                verbose_name="Тип товара",
            ),
        ),
        migrations.RunPython(
            migrate_accessories_to_medical_accessories,
            reverse_migrate_accessories,
        ),
    ]

