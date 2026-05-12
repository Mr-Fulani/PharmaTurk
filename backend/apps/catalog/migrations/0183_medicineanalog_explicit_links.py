from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0182_serviceportfolioitem_city_en"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="medicineanalog",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="medicineanalog",
            name="analog_product",
            field=models.ForeignKey(
                blank=True,
                help_text="Заполняется, когда аналог уже найден или создан в каталоге.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="referenced_by_analog_rows",
                to="catalog.medicineproduct",
                verbose_name="Связанный товар-аналóг",
            ),
        ),
        migrations.AddField(
            model_name="medicineanalog",
            name="sgk_equivalent_code",
            field=models.CharField(blank=True, max_length=100, verbose_name="SGK Eşdeğer Kodu"),
        ),
        migrations.AddField(
            model_name="medicineanalog",
            name="source_tab",
            field=models.CharField(blank=True, max_length=100, verbose_name="Вкладка источника"),
        ),
        migrations.AddConstraint(
            model_name="medicineanalog",
            constraint=models.UniqueConstraint(
                condition=~models.Q(barcode=""),
                fields=("product", "source", "barcode"),
                name="uniq_medicine_analog_barcode_per_source",
            ),
        ),
        migrations.AddConstraint(
            model_name="medicineanalog",
            constraint=models.UniqueConstraint(
                condition=~models.Q(external_id=""),
                fields=("product", "source", "external_id"),
                name="uniq_medicine_analog_external_per_source",
            ),
        ),
    ]
