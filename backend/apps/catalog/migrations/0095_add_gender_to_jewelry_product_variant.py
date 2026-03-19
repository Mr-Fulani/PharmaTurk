from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0094_alter_jewelryproduct_main_image_file_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="jewelryproduct",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("men", "Мужская"),
                    ("women", "Женская"),
                    ("unisex", "Унисекс"),
                    ("kids", "Детская"),
                ],
                help_text="Для украшений: мужская, женская, унисекс, детская",
                max_length=10,
                null=True,
                verbose_name="Пол",
            ),
        ),
        migrations.AddField(
            model_name="jewelryvariant",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("men", "Мужская"),
                    ("women", "Женская"),
                    ("unisex", "Унисекс"),
                    ("kids", "Детская"),
                ],
                help_text="Для украшений: мужская, женская, унисекс, детская",
                max_length=10,
                null=True,
                verbose_name="Пол",
            ),
        ),
    ]
