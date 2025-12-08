from django.db import migrations, models

import apps.catalog.models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0017_currency_choices_for_other_products"),
    ]

    operations = [
        migrations.AlterField(
            model_name="electronicsproduct",
            name="currency",
            field=models.CharField(
                verbose_name="Валюта",
                max_length=5,
                choices=apps.catalog.models.CURRENCY_CHOICES,
                default="RUB",
                help_text="Выбирается из списка расчётных валют, используемых в прайсах.",
            ),
        ),
        migrations.AlterField(
            model_name="shoeproduct",
            name="currency",
            field=models.CharField(
                verbose_name="Валюта",
                max_length=5,
                choices=apps.catalog.models.CURRENCY_CHOICES,
                default="RUB",
                help_text="Выбирается из списка расчётных валют, используемых в прайсах.",
            ),
        ),
    ]

