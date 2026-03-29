"""
Увеличиваем max_length для:
- external_id: 100 → 500 (URL-slug у ilacfiyati может быть длиннее 100 символов)
- dosage_form: 20 → 100 (турецкие названия форм выпуска бывают длинными)
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0139_remove_shoe_type"),
    ]

    operations = [
        # external_id: 100 → 500 во всех доменных моделях
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
            model_name="bookproduct",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID"),
        ),
        migrations.AlterField(
            model_name="clothingproduct",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID"),
        ),
        migrations.AlterField(
            model_name="shoeproduct",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID"),
        ),
        migrations.AlterField(
            model_name="jewelryproduct",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID"),
        ),
        migrations.AlterField(
            model_name="electronicsproduct",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID"),
        ),
        migrations.AlterField(
            model_name="furnitureproduct",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID"),
        ),
        migrations.AlterField(
            model_name="perfumeryproduct",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID"),
        ),
        migrations.AlterField(
            model_name="service",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID"),
        ),
        # dosage_form: 20 → 100 (турецкие формы выпуска типа "Flakon, İv")
        migrations.AlterField(
            model_name="medicineproduct",
            name="dosage_form",
            field=models.CharField(blank=True, max_length=100, verbose_name="Лекарственная форма"),
        ),
    ]
