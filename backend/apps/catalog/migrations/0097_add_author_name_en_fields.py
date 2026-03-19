from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0096_add_product_name_translations_and_variant_name_en"),
    ]

    operations = [
        migrations.AddField(
            model_name="author",
            name="first_name_en",
            field=models.CharField(blank=True, max_length=100, verbose_name="Имя (англ.)"),
        ),
        migrations.AddField(
            model_name="author",
            name="last_name_en",
            field=models.CharField(blank=True, max_length=100, verbose_name="Фамилия (англ.)"),
        ),
    ]
