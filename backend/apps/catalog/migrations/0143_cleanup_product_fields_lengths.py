"""
Финальное расширение всех полей.
Гарантируем max_length для external_id, external_url, og_image_url и dosage_form
во ВСЕХ доменных моделях, включая базовую Product.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0142_alter_accessoryproduct_external_id_and_more"),
    ]

    operations = [
        # 1.external_id: 100 -> 500 во всех моделях
        migrations.AlterField(
            model_name="product",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID"),
        ),
        migrations.AlterField(
            model_name="medicineproduct",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID"),
        ),
        migrations.AlterField(
            model_name="supplementproduct",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID"),
        ),
        migrations.AlterField(
            model_name="electronicsproduct",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID"),
        ),

        # 2. URL-поля: 200 -> 2000 во всех моделях
        migrations.AlterField(
            model_name="product",
            name="external_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="Внешняя ссылка"),
        ),
        migrations.AlterField(
            model_name="product",
            name="og_image_url",
            field=models.URLField(
                blank=True,
                max_length=2000,
                verbose_name="OG Image URL",
                help_text="Ссылка на изображение для OpenGraph, если оно отличается от основного.",
            ),
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

        # 3. dosage_form: 20 -> 100 во всех моделях
        migrations.AlterField(
            model_name="medicineproduct",
            name="dosage_form",
            field=models.CharField(blank=True, max_length=100, verbose_name="Лекарственная форма"),
        ),
        migrations.AlterField(
            model_name="medicineproducttranslation",
            name="dosage_form",
            field=models.CharField(blank=True, max_length=100, verbose_name="Лекарственная форма"),
        ),
        migrations.AlterField(
            model_name="supplementproduct",
            name="dosage_form",
            field=models.CharField(blank=True, max_length=100, verbose_name="Лекарственная форма"),
        ),
        migrations.AlterField(
            model_name="supplementproducttranslation",
            name="dosage_form",
            field=models.CharField(blank=True, max_length=100, verbose_name="Лекарственная форма"),
        ),
    ]
