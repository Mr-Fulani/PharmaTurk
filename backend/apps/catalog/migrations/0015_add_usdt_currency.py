from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0014_adjust_product_currency_and_seo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="currency",
            field=models.CharField(
                choices=[
                    ("RUB", "RUB"),
                    ("USD", "USD"),
                    ("EUR", "EUR"),
                    ("TRY", "TRY"),
                    ("GBP", "GBP"),
                    ("USDT", "USDT"),
                ],
                default="RUB",
                help_text=_("Выбирается из списка расчётных валют, используемых в прайсах."),
                max_length=5,
                verbose_name=_("Валюта"),
            ),
        ),
    ]

