"""
Увеличиваем max_length для URLField полей:
- external_url: дефолт URLField=200 → 2000
- og_image_url: дефолт URLField=200 → 2000

Причина: URL изображений с длинными slug-именами (например, у ilacfiyati.com)
могут превышать 200 символов.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0140_increase_external_id_and_dosage_form"),
    ]

    operations = [
        # og_image_url: 200 → 2000
        migrations.AlterField(
            model_name="product",
            name="og_image_url",
            field=models.URLField(
                blank=True,
                max_length=2000,
                verbose_name="OG Image URL",
            ),
        ),
        # external_url: 200 → 2000 во всех доменных моделях
        migrations.AlterField(
            model_name="product",
            name="external_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="Внешняя ссылка"),
        ),
        migrations.AlterField(
            model_name="medicineproduct",
            name="external_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="Внешняя ссылка"),
        ),
        migrations.AlterField(
            model_name="supplementproduct",
            name="external_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="Внешняя ссылка"),
        ),
        migrations.AlterField(
            model_name="bookproduct",
            name="external_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="Внешняя ссылка"),
        ),
        migrations.AlterField(
            model_name="clothingproduct",
            name="external_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="Внешняя ссылка"),
        ),
        migrations.AlterField(
            model_name="shoeproduct",
            name="external_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="Внешняя ссылка"),
        ),
        migrations.AlterField(
            model_name="jewelryproduct",
            name="external_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="Внешняя ссылка"),
        ),
        migrations.AlterField(
            model_name="electronicsproduct",
            name="external_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="Внешняя ссылка"),
        ),
        migrations.AlterField(
            model_name="furnitureproduct",
            name="external_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="Внешняя ссылка"),
        ),
        migrations.AlterField(
            model_name="service",
            name="external_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="Внешняя ссылка"),
        ),
        migrations.AlterField(
            model_name="perfumeryproduct",
            name="external_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="Внешняя ссылка"),
        ),
    ]
