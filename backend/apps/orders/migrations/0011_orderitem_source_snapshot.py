from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0010_cartitem_source_verification"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="source_parser",
            field=models.CharField(blank=True, max_length=100, verbose_name="Парсер источника"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_domain",
            field=models.CharField(blank=True, max_length=255, verbose_name="Домен источника"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_url",
            field=models.URLField(blank=True, max_length=2000, verbose_name="URL источника"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_external_product_id",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний ID товара"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_external_sku",
            field=models.CharField(blank=True, max_length=500, verbose_name="Внешний SKU"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_variant_key",
            field=models.CharField(
                blank=True, max_length=500, verbose_name="Ключ варианта источника"
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_size_key",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="Ключ размера источника"
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_selected_options",
            field=models.JSONField(
                blank=True, default=dict, verbose_name="Выбранные опции источника"
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Цена источника при оформлении",
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_currency",
            field=models.CharField(blank=True, max_length=10, verbose_name="Валюта источника"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_availability_status",
            field=models.CharField(
                blank=True, max_length=32, verbose_name="Наличие у источника при оформлении"
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_stock_precision",
            field=models.CharField(
                blank=True, max_length=16, verbose_name="Точность остатка источника"
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_stock_quantity",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Остаток источника при оформлении"
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_checked_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Источник проверен при оформлении"
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="supplier_confirmation_required",
            field=models.BooleanField(
                default=False, verbose_name="Требуется подтверждение поставщика"
            ),
        ),
    ]
