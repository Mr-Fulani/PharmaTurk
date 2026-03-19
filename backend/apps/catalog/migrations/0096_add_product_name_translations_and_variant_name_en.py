from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0095_add_gender_to_jewelry_product_variant"),
    ]

    operations = [
        migrations.AddField(
            model_name="producttranslation",
            name="name",
            field=models.CharField(
                blank=True,
                help_text="Переведенное название товара",
                max_length=500,
                verbose_name="Название",
            ),
        ),
        migrations.AddField(
            model_name="clothingproducttranslation",
            name="name",
            field=models.CharField(
                blank=True,
                help_text="Переведенное название товара одежды",
                max_length=500,
                verbose_name="Название",
            ),
        ),
        migrations.AddField(
            model_name="shoeproducttranslation",
            name="name",
            field=models.CharField(
                blank=True,
                help_text="Переведенное название товара обуви",
                max_length=500,
                verbose_name="Название",
            ),
        ),
        migrations.AddField(
            model_name="jewelryproducttranslation",
            name="name",
            field=models.CharField(
                blank=True,
                help_text="Переведенное название товара украшений",
                max_length=500,
                verbose_name="Название",
            ),
        ),
        migrations.AddField(
            model_name="electronicsproducttranslation",
            name="name",
            field=models.CharField(
                blank=True,
                help_text="Переведенное название товара электроники",
                max_length=500,
                verbose_name="Название",
            ),
        ),
        migrations.AddField(
            model_name="furnitureproducttranslation",
            name="name",
            field=models.CharField(
                blank=True,
                help_text="Переведенное название товара мебели",
                max_length=500,
                verbose_name="Название",
            ),
        ),
        migrations.AddField(
            model_name="clothingvariant",
            name="name_en",
            field=models.CharField(
                blank=True,
                max_length=500,
                verbose_name="Название (англ.)",
            ),
        ),
        migrations.AddField(
            model_name="shoevariant",
            name="name_en",
            field=models.CharField(
                blank=True,
                max_length=500,
                verbose_name="Название (англ.)",
            ),
        ),
        migrations.AddField(
            model_name="jewelryvariant",
            name="name_en",
            field=models.CharField(
                blank=True,
                max_length=500,
                verbose_name="Название (англ.)",
            ),
        ),
        migrations.AddField(
            model_name="furniturevariant",
            name="name_en",
            field=models.CharField(
                blank=True,
                max_length=500,
                verbose_name="Название (англ.)",
            ),
        ),
        migrations.AddField(
            model_name="bookvariant",
            name="name_en",
            field=models.CharField(
                blank=True,
                max_length=500,
                verbose_name="Название (англ.)",
            ),
        ),
    ]
