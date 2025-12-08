from django.db import migrations, models


def migrate_product_types(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    # Перенос устаревших типов в "accessories"
    Product.objects.filter(product_type__in=["tableware", "furniture", "other"]).update(product_type="accessories")


def reverse_migrate_product_types(apps, schema_editor):
    # Обратного разнесения нет; оставляем как есть
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0019_add_clothing_electronics_images"),
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
                    ("accessories", "Аксессуары"),
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
        migrations.RunPython(migrate_product_types, reverse_migrate_product_types),
    ]

